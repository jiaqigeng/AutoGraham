from __future__ import annotations

from typing import Any, Mapping

from agent.deep_agent import invoke_text_prompt
from agent.prompts.model_selection_prompts import build_model_selection_prompt
from agent.schemas import ModelRecommendation
from agent.tools.finance_tools import build_company_snapshot, resolve_stock_info
from agent.tools.validation_tools import extract_json_object
from data.company_profile import is_dividend_model_candidate, is_financial_company
from valuation.common import default_valuation_inputs


def _rule_based_selection(
	info: Mapping[str, Any],
	defaults: Mapping[str, float],
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	"""Choose a practical valuation family using business-shape heuristics."""

	focus_text = (analysis_focus or "").lower()
	financial_company = is_financial_company(info)
	dividend_candidate = is_dividend_model_candidate(info, defaults, focus_text)
	book_value_usable = defaults["book_value_per_share"] > 0 and defaults["return_on_equity"] > 0
	high_growth = defaults["high_growth"]

	if financial_company and book_value_usable and not dividend_candidate:
		return ModelRecommendation(
			selected_model="RIM",
			selected_variant=None,
			preferred_calculation_model="RIM",
			model_reason="The business looks financial in nature and book value plus ROE appear more informative than direct cash-flow forecasting.",
			confidence=0.78,
		).model_dump()

	if dividend_candidate and defaults["dividend_per_share"] > 0:
		variant = "H-Model" if high_growth - defaults["stable_growth"] >= 0.03 else "Single-Stage (Stable)"
		if variant == "Single-Stage (Stable)" and high_growth > 0.05:
			variant = "Two-Stage"
		return ModelRecommendation(
			selected_model="DDM",
			selected_variant=variant,
			preferred_calculation_model="DDM",
			model_reason="Dividends appear meaningful enough that a dividend-led valuation is plausible.",
			confidence=0.72,
		).model_dump()

	variant = "Three-Stage (Multi-stage decay)" if high_growth >= 0.12 else "Two-Stage" if high_growth >= 0.05 else "Single-Stage (Stable)"
	preferred_model = "FCFF" if defaults["starting_fcff"] >= defaults["starting_fcfe"] else "FCFE"
	return ModelRecommendation(
		selected_model="DCF",
		selected_variant=variant,
		preferred_calculation_model=preferred_model,
		model_reason="An operating-company cash-flow framework appears to be the most practical base case.",
		confidence=0.68,
	).model_dump()


def _choice_is_plausible(choice: Mapping[str, Any], defaults: Mapping[str, float]) -> bool:
	"""Reject obviously invalid LLM selections and fall back to rules."""

	selected_model = str(choice.get("selected_model") or "").upper()
	selected_variant = choice.get("selected_variant")
	if selected_model == "DDM" and defaults["dividend_per_share"] <= 0:
		return False
	if selected_model == "RIM" and defaults["book_value_per_share"] <= 0:
		return False
	if selected_model == "DCF" and max(defaults["starting_fcff"], defaults["starting_fcfe"]) <= 0:
		return False
	if selected_model != "DDM" and selected_variant == "H-Model":
		return False
	return selected_model in {"DCF", "DDM", "RIM"}


def select_model(
	ticker: str,
	stock_info: Mapping[str, Any] | Any,
	candidate_facts: list[Mapping[str, Any]],
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	"""Choose among DCF, DDM, and RIM using rules first and LLM refinement second."""

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
	snapshot = build_company_snapshot(ticker, stock_info)
	fallback = _rule_based_selection(info, defaults, analysis_focus)

	llm_text = invoke_text_prompt(
		system_prompt="Return JSON only.",
		user_prompt=build_model_selection_prompt(
			ticker=ticker,
			company_name=str(snapshot.get("company_name") or ticker),
			candidate_facts=candidate_facts,
			analysis_focus=analysis_focus,
		),
		model_name=model_name,
		temperature=0.0,
	)
	if not llm_text:
		return fallback

	try:
		choice = ModelRecommendation.model_validate(extract_json_object(llm_text)).model_dump()
	except Exception:
		return fallback

	if not _choice_is_plausible(choice, defaults):
		return fallback
	if not choice.get("preferred_calculation_model") and choice.get("selected_model") == "DCF":
		choice["preferred_calculation_model"] = fallback.get("preferred_calculation_model") or "FCFF"
	return choice
