from __future__ import annotations

from typing import Any, Mapping

from agent.deep_agent import invoke_text_prompt
from agent.prompts.parameter_prompts import build_parameter_prompt
from agent.schemas import AssumptionReason, CandidateFact, ParameterPayload
from agent.tools.calculator_tools import build_default_fetched_facts, default_parameter_fallback
from agent.tools.finance_tools import resolve_stock_info
from agent.tools.validation_tools import extract_json_object
from valuation.common import default_valuation_inputs


def _resolve_calculation_model(model_selection: Mapping[str, Any], defaults: Mapping[str, float]) -> str:
	"""Choose the deterministic calculator code for the selected family."""

	selected_model = str(model_selection.get("selected_model") or "").upper()
	preferred = str(model_selection.get("preferred_calculation_model") or "").upper()
	if selected_model == "DCF":
		if preferred in {"FCFF", "FCFE"}:
			return preferred
		return "FCFF" if defaults["starting_fcff"] >= defaults["starting_fcfe"] else "FCFE"
	if selected_model == "DDM":
		return "DDM"
	return "RIM"


def _merge_fetched_facts(candidate_facts: list[Mapping[str, Any]], defaults: Mapping[str, float]) -> list[dict[str, Any]]:
	"""Merge heuristic candidate facts with deterministic baseline facts."""

	merged: dict[str, dict[str, Any]] = {
		item["key"]: item for item in build_default_fetched_facts(defaults) if item.get("key")
	}
	for item in candidate_facts:
		key = str(item.get("key") or "").strip()
		if not key:
			continue
		merged[key] = CandidateFact.model_validate(item).model_dump()
	return list(merged.values())


def _merge_assumption_reasons(
	fallback_reasons: list[Mapping[str, Any]],
	llm_reasons: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
	"""Merge assumption reason rows by key."""

	merged: dict[str, dict[str, Any]] = {}
	for item in fallback_reasons:
		key = str(item.get("key") or "").strip()
		if key:
			merged[key] = AssumptionReason.model_validate(item).model_dump()
	for item in llm_reasons:
		key = str(item.get("key") or "").strip()
		if key:
			merged[key] = AssumptionReason.model_validate(item).model_dump()
	return list(merged.values())


def estimate_parameters(
	ticker: str,
	stock_info: Mapping[str, Any] | Any,
	candidate_facts: list[Mapping[str, Any]],
	model_selection: Mapping[str, Any],
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	"""Assemble a structured parameter payload after model selection."""

	info = resolve_stock_info(stock_info)
	annual_cashflow = getattr(stock_info, "annual_cashflow", None)
	annual_balance_sheet = getattr(stock_info, "annual_balance_sheet", None)
	annual_income_stmt = getattr(stock_info, "annual_income_stmt", None)
	defaults = default_valuation_inputs(
		info,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)
	selected_model = str(model_selection.get("selected_model") or "").upper()
	selected_variant = model_selection.get("selected_variant")
	calculation_model = _resolve_calculation_model(model_selection, defaults)
	fallback = default_parameter_fallback(selected_model, selected_variant, defaults, calculation_model=calculation_model)
	assumptions = dict(fallback.get("assumptions") or {})
	assumption_reasons = list(fallback.get("assumption_reasons") or [])

	llm_text = invoke_text_prompt(
		system_prompt="Return JSON only.",
		user_prompt=build_parameter_prompt(
			ticker=ticker,
			selected_model=selected_model,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			analysis_focus=analysis_focus,
		),
		model_name=model_name,
		temperature=0.0,
	)
	if llm_text:
		try:
			llm_payload = extract_json_object(llm_text)
			for key, value in dict(llm_payload.get("assumptions") or {}).items():
				if value is None or value == "":
					continue
				assumptions[key] = float(value)
			assumption_reasons = _merge_assumption_reasons(
				assumption_reasons,
				list(llm_payload.get("assumption_reasons") or []),
			)
			parameter_reason = str(llm_payload.get("parameter_reason") or fallback.get("parameter_reason") or "").strip()
			confidence = 0.7
		except Exception:
			parameter_reason = str(fallback.get("parameter_reason") or "").strip()
			confidence = 0.6
	else:
		parameter_reason = str(fallback.get("parameter_reason") or "").strip()
		confidence = 0.6

	payload = ParameterPayload(
		selected_model=selected_model,
		selected_variant=selected_variant,
		calculation_model=calculation_model,
		parameter_reason=parameter_reason,
		fetched_facts=_merge_fetched_facts(candidate_facts, defaults),
		assumptions=assumptions,
		assumption_reasons=assumption_reasons,
		confidence=confidence,
	)
	return payload.model_dump()
