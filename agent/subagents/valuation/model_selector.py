from __future__ import annotations

from typing import Any, Mapping

from agent.llm_utils import build_chat_model, invoke_text_prompt
from agent.skill_prompt_loader import build_model_selection_prompt
from agent.schemas import ModelRecommendation
from agent.tools.finance_tools import (
	build_company_snapshot,
	get_cash_flow_health,
	get_income_statement,
	get_valuation_metrics,
	resolve_stock_info,
)
from agent.tools.sec_tools import get_relevant_filing_sections
from agent.tools.validation_tools import extract_json_object
from data.company_profile import is_dividend_model_candidate, is_financial_company
from valuation.common import DEFAULT_PROJECTION_YEARS, default_valuation_inputs


MODEL_SELECTION_AGENT_SYSTEM_PROMPT = """
You are the valuation model selection specialist for AutoGraham.

This stage verifies valuation fit. The upstream context builder already handled broad company research.

Behavioral rules:
- Prefer the supplied candidate facts, company snapshot, and deterministic defaults first.
- Use tools only when model fit is still ambiguous.
- Do not repeat broad company research already done by the context builder.
- Use tools to resolve narrow questions like dividend durability, cash-flow usability, leverage, or structural changes.
- The AI workflow uses driver-based valuation paths only.
- Always choose projection_years directly in this stage and never choose more than 10 years.
- For the current AI workflow, choose only 5 years or 10 years when an explicit forecast horizon is required.
- Choose projection_years based on the company's current stage; allow longer horizons for buildout, scaling, restructuring, or other transition periods, and shorter horizons for mature steady-state businesses.
- Also consider normalization length, business visibility, cyclicality, capital intensity, and whether the thesis depends on a multi-year turnaround, deleveraging, or margin recovery.
- Keep tool use light and deliberate.
- Return JSON only.
""".strip()


def _build_agent_executor(model_name: str | None):
	try:
		from langchain.agents import AgentExecutor, create_tool_calling_agent
		from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
	except ImportError:
		return None

	llm = build_chat_model(model_name, temperature=0.0)
	if llm is None:
		return None

	tools = [
		get_valuation_metrics,
		get_income_statement,
		get_cash_flow_health,
		get_relevant_filing_sections,
	]
	prompt = ChatPromptTemplate.from_messages(
		[
			("system", MODEL_SELECTION_AGENT_SYSTEM_PROMPT),
			("human", "{input}"),
			MessagesPlaceholder("agent_scratchpad"),
		]
	)
	agent = create_tool_calling_agent(llm, tools, prompt)
	return AgentExecutor(
		agent=agent,
		tools=tools,
		verbose=False,
		handle_parsing_errors=True,
		max_iterations=3,
	)


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

	if financial_company and book_value_usable and not dividend_candidate:
		return ModelRecommendation(
			selected_model="RIM",
			selected_variant="Drivers",
			selected_submodel="RIM",
			projection_years=int(defaults.get("projection_years") or DEFAULT_PROJECTION_YEARS),
			projection_years_reason="Fallback to a standard 5-year driver horizon because the model selector could not verify a better explicit forecast length.",
			preferred_calculation_model="RIM",
			model_reason="The business looks financial in nature and book value plus ROE appear more informative than direct cash-flow forecasting.",
			confidence=0.78,
		).model_dump()

	if dividend_candidate and defaults["dividend_per_share"] > 0:
		return ModelRecommendation(
			selected_model="DDM",
			selected_variant="Drivers",
			selected_submodel="DDM",
			projection_years=int(defaults.get("projection_years") or DEFAULT_PROJECTION_YEARS),
			projection_years_reason="Fallback to a standard 5-year driver horizon because the model selector could not verify a better explicit forecast length.",
			preferred_calculation_model="DDM",
			model_reason="Dividends appear meaningful enough that a dividend-led valuation is plausible.",
			confidence=0.72,
		).model_dump()

	preferred_model = "FCFF" if defaults["starting_fcff"] >= defaults["starting_fcfe"] else "FCFE"
	return ModelRecommendation(
		selected_model="DCF",
		selected_variant="Drivers",
		selected_submodel=preferred_model,
		projection_years=int(defaults.get("projection_years") or DEFAULT_PROJECTION_YEARS),
		projection_years_reason="Fallback to a standard 5-year driver horizon because the model selector could not verify a better explicit forecast length.",
		preferred_calculation_model=preferred_model,
		model_reason="An operating-company cash-flow framework appears to be the most practical base case.",
		confidence=0.68,
	).model_dump()


def _choice_is_plausible(choice: Mapping[str, Any], defaults: Mapping[str, float]) -> bool:
	"""Reject obviously invalid LLM selections and fall back to rules."""

	selected_model = str(choice.get("selected_model") or "").upper()
	selected_variant = choice.get("selected_variant")
	projection_years = choice.get("projection_years")
	if selected_model == "DDM" and defaults["dividend_per_share"] <= 0:
		return False
	if selected_model == "RIM" and defaults["book_value_per_share"] <= 0:
		return False
	if selected_model == "DCF" and max(defaults["starting_fcff"], defaults["starting_fcfe"]) <= 0:
		return False
	if selected_variant != "Drivers":
		return False
	if selected_model == "DCF" and str(choice.get("preferred_calculation_model") or "").upper() not in {"FCFF", "FCFE"}:
		return False
	if selected_model == "DDM" and str(choice.get("preferred_calculation_model") or "").upper() != "DDM":
		return False
	if selected_model == "RIM" and str(choice.get("preferred_calculation_model") or "").upper() != "RIM":
		return False
	if not isinstance(projection_years, (int, float)) or int(projection_years) != float(projection_years):
		return False
	if int(projection_years) not in {5, 10}:
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
	prompt_text = build_model_selection_prompt(
		ticker=ticker,
		company_name=str(snapshot.get("company_name") or ticker),
		candidate_facts=candidate_facts,
		analysis_focus=analysis_focus,
	)

	llm_text: str | None = None
	executor = _build_agent_executor(model_name)
	if executor is not None:
		try:
			result = executor.invoke({"input": prompt_text})
			llm_text = str(result.get("output") or "").strip() or None
		except Exception:
			llm_text = None

	if not llm_text:
		llm_text = invoke_text_prompt(
			system_prompt="Return JSON only.",
			user_prompt=prompt_text,
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
	choice["projection_years"] = int(choice["projection_years"])
	if not choice.get("preferred_calculation_model") and choice.get("selected_model") == "DCF":
		choice["preferred_calculation_model"] = fallback.get("preferred_calculation_model") or "FCFF"
	if not choice.get("selected_submodel"):
		choice["selected_submodel"] = choice.get("preferred_calculation_model")
	return choice
