from __future__ import annotations

from typing import Any, Mapping

from agent.deep_agent import invoke_text_prompt
from agent.prompts.parameter_prompts import build_parameter_prompt
from agent.schemas import AssumptionReason, CandidateFact, ParameterPayload
from agent.tools.calculator_tools import build_default_fetched_facts, default_parameter_fallback
from agent.tools.finance_tools import resolve_stock_info
from agent.tools.validation_tools import extract_json_object
from valuation.common import default_valuation_inputs


DCF_DRIVER_NOTE_MAP: dict[str, dict[str, str]] = {
	"FCFF": {
		"revenue": "revenue",
		"ebit_margin": "ebit_margin",
		"tax_rate": "tax_rate",
		"depreciation": "depreciation",
		"capex": "capex",
		"change_in_nwc": "change_in_nwc",
		"wacc": "wacc",
		"terminal_growth": "terminal_assumptions",
		"total_debt": "total_debt",
		"cash": "cash",
		"shares_outstanding": "shares_outstanding",
	},
	"FCFE": {
		"revenue": "revenue",
		"ebit_margin": "ebit_margin",
		"tax_rate": "tax_rate",
		"depreciation": "depreciation",
		"capex": "capex",
		"change_in_nwc": "change_in_nwc",
		"net_borrowing": "net_borrowing",
		"cost_of_equity": "cost_of_equity",
		"terminal_growth": "terminal_assumptions",
		"shares_outstanding": "shares_outstanding",
	},
}


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


def _coerce_numeric_value(value: Any) -> float | list[float]:
	"""Coerce a scalar or homogeneous numeric list into floats."""

	if isinstance(value, list):
		return [float(item) for item in value if item not in (None, "")]
	return float(value)


def _translate_dcf_driver_payload(
	llm_payload: Mapping[str, Any],
	calculation_model: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], str, list[str]]:
	"""Normalize FCFF/FCFE yearly-forecast JSON into the internal parameter payload shape."""

	inputs = llm_payload.get("inputs")
	if not isinstance(inputs, Mapping):
		raise ValueError("DCF driver payload must contain an inputs object.")
	assumption_notes = llm_payload.get("assumption_notes")
	assumption_notes_lookup = assumption_notes if isinstance(assumption_notes, Mapping) else {}
	balance_sheet_inputs = llm_payload.get("balance_sheet_inputs")
	balance_sheet_lookup = balance_sheet_inputs if isinstance(balance_sheet_inputs, Mapping) else {}
	equity_inputs = llm_payload.get("equity_inputs")
	equity_input_lookup = equity_inputs if isinstance(equity_inputs, Mapping) else {}

	assumptions: dict[str, Any] = {}
	for key, value in inputs.items():
		if value in (None, "", []):
			continue
		assumptions[str(key)] = _coerce_numeric_value(value)
	for key in ("total_debt", "cash", "shares_outstanding"):
		if key in assumptions:
			continue
		payload = balance_sheet_lookup.get(key)
		if not isinstance(payload, Mapping):
			continue
		value = payload.get("value")
		if value in (None, "", []):
			continue
		assumptions[key] = _coerce_numeric_value(value)
	for key in ("shares_outstanding",):
		if key in assumptions:
			continue
		payload = equity_input_lookup.get(key)
		if not isinstance(payload, Mapping):
			continue
		value = payload.get("value")
		if value in (None, "", []):
			continue
		assumptions[key] = _coerce_numeric_value(value)

	parameter_research = llm_payload.get("parameter_research")
	parameter_research_lookup = parameter_research if isinstance(parameter_research, Mapping) else {}
	terminal_research = llm_payload.get("terminal_research")
	terminal_research_lookup = terminal_research if isinstance(terminal_research, Mapping) else {}
	reason_map = DCF_DRIVER_NOTE_MAP.get(calculation_model, {})
	assumption_reasons: list[dict[str, Any]] = []
	for key, note_key in reason_map.items():
		if key not in assumptions:
			continue
		note = str(assumption_notes_lookup.get(key) or assumption_notes_lookup.get(note_key) or "").strip()
		if not note and note_key in terminal_research_lookup and isinstance(terminal_research_lookup.get(note_key), Mapping):
			note = str(terminal_research_lookup[note_key].get("logic") or "").strip()
		elif not note and note_key in balance_sheet_lookup and isinstance(balance_sheet_lookup.get(note_key), Mapping):
			note = str(balance_sheet_lookup[note_key].get("source") or "").strip()
		elif not note and note_key in equity_input_lookup and isinstance(equity_input_lookup.get(note_key), Mapping):
			note = str(equity_input_lookup[note_key].get("source") or "").strip()
		elif not note and note_key in parameter_research_lookup and isinstance(parameter_research_lookup.get(note_key), Mapping):
			research_item = parameter_research_lookup[note_key]
			note = str(research_item.get("forecast_logic") or "").strip()
		if not note:
			note = "Estimated for year-by-year DCF input generation."
		assumption_reasons.append({"key": key, "reason": note})

	forecast_horizon = llm_payload.get("projection_years", llm_payload.get("forecast_horizon"))
	forecast_reason = str(llm_payload.get("projection_rationale") or assumption_notes_lookup.get("projection_years") or "").strip()
	if not forecast_reason and isinstance(llm_payload.get("parameter_research"), Mapping):
		for research_item in parameter_research_lookup.values():
			if isinstance(research_item, Mapping):
				candidate_reason = str(research_item.get("forecast_logic") or "").strip()
				if candidate_reason:
					forecast_reason = candidate_reason
					break
	model_warnings = [str(item).strip() for item in list(llm_payload.get("model_warnings") or llm_payload.get("research_warnings") or []) if str(item).strip()]
	horizon_text = f"{int(forecast_horizon)}-year" if isinstance(forecast_horizon, (int, float)) else "yearly-forecast"
	parameter_reason = f"{calculation_model} {horizon_text} DCF forecast."
	if forecast_reason:
		parameter_reason = f"{parameter_reason} {forecast_reason}"
	return assumptions, assumption_reasons, parameter_reason, model_warnings


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
	use_driver_dcf = selected_model == "DCF" and calculation_model in {"FCFF", "FCFE"}
	fallback = default_parameter_fallback(selected_model, selected_variant, defaults, calculation_model=calculation_model)
	if use_driver_dcf:
		assumptions: dict[str, Any] = {}
		assumption_reasons: list[dict[str, Any]] = []
		fallback["weak_or_uncertain_inputs"] = []
	else:
		assumptions = dict(fallback.get("assumptions") or {})
		assumption_reasons = list(fallback.get("assumption_reasons") or [])

	llm_text = invoke_text_prompt(
		system_prompt="Return JSON only.",
		user_prompt=build_parameter_prompt(
			ticker=ticker,
			selected_model=selected_model,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			calculation_model=calculation_model,
			analysis_focus=analysis_focus,
		),
		model_name=model_name,
		temperature=0.0,
	)
	if llm_text:
		try:
			llm_payload = extract_json_object(llm_text)
			if use_driver_dcf and isinstance(llm_payload.get("inputs"), Mapping):
				driver_assumptions, driver_reasons, driver_parameter_reason, model_warnings = _translate_dcf_driver_payload(
					llm_payload,
					calculation_model=calculation_model,
				)
				assumptions.update(driver_assumptions)
				assumption_reasons = _merge_assumption_reasons(assumption_reasons, driver_reasons)
				parameter_reason = driver_parameter_reason or str(fallback.get("parameter_reason") or "").strip()
				if model_warnings:
					existing_warnings = [str(item).strip() for item in list(fallback.get("weak_or_uncertain_inputs") or []) if str(item).strip()]
					fallback["weak_or_uncertain_inputs"] = existing_warnings + model_warnings
			elif use_driver_dcf:
				parameter_reason = (
					f"{calculation_model} DCF inputs unresolved. "
					"No simple DCF fallback was applied because this path requires structured yearly forecasts."
				)
				fallback["weak_or_uncertain_inputs"] = [
					"The DCF parameter payload did not include the required yearly-forecast `inputs` object."
				]
			else:
				for key, value in dict(llm_payload.get("assumptions") or {}).items():
					if value is None or value == "":
						continue
					assumptions[key] = float(value)
				assumption_reasons = _merge_assumption_reasons(
					assumption_reasons,
					list(llm_payload.get("assumption_reasons") or []),
				)
				parameter_reason = str(llm_payload.get("parameter_reason") or fallback.get("parameter_reason") or "").strip()
			confidence = 0.35 if use_driver_dcf and not assumptions else 0.7
		except Exception:
			if use_driver_dcf:
				parameter_reason = (
					f"{calculation_model} DCF inputs unresolved. "
					"No simple DCF fallback was applied because the yearly-forecast payload could not be parsed."
				)
				fallback["weak_or_uncertain_inputs"] = [
					"The DCF yearly-forecast payload could not be parsed into validated inputs."
				]
				confidence = 0.2
			else:
				parameter_reason = str(fallback.get("parameter_reason") or "").strip()
				confidence = 0.6
	else:
		if use_driver_dcf:
			parameter_reason = (
				f"{calculation_model} DCF inputs unresolved. "
				"No simple DCF fallback was applied because no yearly-forecast payload was returned."
			)
			fallback["weak_or_uncertain_inputs"] = [
				"No DCF yearly-forecast payload was returned by the parameter estimator."
			]
			confidence = 0.2
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
		weak_or_uncertain_inputs=list(fallback.get("weak_or_uncertain_inputs") or []),
	)
	return payload.model_dump()
