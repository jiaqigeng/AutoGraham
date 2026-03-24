from __future__ import annotations

import re
from typing import Any, Mapping

from agent.llm_utils import build_chat_model, invoke_text_prompt
from agent.schemas import CandidateFact
from agent.skill_prompt_loader import build_context_request, build_context_system_prompt, build_extraction_prompt
from agent.tools.finance_tools import (
	build_company_snapshot,
	build_source_links,
	get_cash_flow_health,
	get_company_profile_text,
	get_income_statement,
)
from agent.tools.sec_tools import build_source_hints, get_filing_source_hints, get_relevant_filing_section_notes, get_relevant_filing_sections
from agent.tools.validation_tools import extract_json_array
from agent.tools.web_search import search_company_market_context, search_company_market_context_results
from data.company_profile import is_financial_company
from valuation.common import default_valuation_inputs, safe_number


def _build_agent_executor(target_ticker: str, company_name: str, model_name: str | None):
	try:
		from langchain.agents import AgentExecutor, create_tool_calling_agent
		from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
	except ImportError:
		return None

	llm = build_chat_model(model_name, temperature=0.0)
	if llm is None:
		return None

	tools = [
		get_company_profile_text,
		get_income_statement,
		get_cash_flow_health,
		get_filing_source_hints,
		get_relevant_filing_sections,
		search_company_market_context,
	]
	prompt = ChatPromptTemplate.from_messages(
		[
			("system", build_context_system_prompt(target_ticker, company_name)),
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
		max_iterations=4,
	)


def _company_type(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> str:
	sector = str(snapshot.get("sector") or "Unknown sector")
	industry = str(snapshot.get("industry") or "Unknown industry")
	if is_financial_company(info):
		return f"Financial company in {sector} / {industry}"
	return f"Operating company in {sector} / {industry}"


def _strategic_phase(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> str:
	revenue_growth = safe_number(info.get("revenueGrowth"))
	profit_margin = safe_number(info.get("profitMargins"))
	dividend_yield = safe_number(info.get("dividendYield"))

	if revenue_growth >= 0.15:
		return "High-growth / scaling"
	if revenue_growth < 0 and profit_margin <= 0:
		return "Turnaround / under pressure"
	if dividend_yield > 0.02 and profit_margin > 0:
		return "Mature / capital-return oriented"
	if is_financial_company(info):
		return "Balance-sheet driven / mature financial"
	return "Maturing operator"


def _special_flags(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> list[str]:
	flags: list[str] = []
	if is_financial_company(info):
		flags.append("Financial business: book value and returns on equity may matter more than conventional operating cash-flow framing.")
	if safe_number(snapshot.get("dividend_per_share")) > 0:
		flags.append("Meaningful dividend history is present, so capital return may matter for later model selection.")
	if safe_number(snapshot.get("starting_fcff")) <= 0 and safe_number(snapshot.get("starting_fcfe")) <= 0:
		flags.append("Cash-flow anchors look weak or negative, which may complicate a clean DCF setup.")
	if safe_number(info.get("profitMargins")) <= 0:
		flags.append("Current profitability appears weak or negative.")
	if safe_number(info.get("totalDebt")) > safe_number(info.get("totalCash")) * 2 and safe_number(info.get("totalDebt")) > 0:
		flags.append("Leverage looks elevated relative to cash.")
	if not flags:
		flags.append("No obvious special situation stands out from the lightweight context pass.")
	return flags[:4]


def _supporting_evidence(snapshot: Mapping[str, Any], info: Mapping[str, Any], search_results: list[Mapping[str, str]]) -> list[str]:
	evidence = [
		f"Sector / industry: {snapshot.get('sector')} / {snapshot.get('industry')}.",
		f"Current price anchor: {snapshot.get('current_price')}; market cap: {snapshot.get('market_cap')}.",
		f"Dividend per share: {snapshot.get('dividend_per_share')}; observed ROE anchor: {snapshot.get('return_on_equity')}.",
	]
	revenue_growth = info.get("revenueGrowth")
	if revenue_growth is not None:
		evidence.append(f"Reported revenue growth signal: {safe_number(revenue_growth):.2%}.")
	profit_margin = info.get("profitMargins")
	if profit_margin is not None:
		evidence.append(f"Reported profit margin signal: {safe_number(profit_margin):.2%}.")
	if search_results:
		top_result = search_results[0]
		evidence.append(
			f"Light web context: {top_result.get('title') or 'Untitled result'}"
			f" ({top_result.get('source_domain') or 'unknown source'})."
		)
	return evidence[:4]


def _should_pull_web_context(snapshot: Mapping[str, Any]) -> bool:
	if str(snapshot.get("sector") or "N/A") == "N/A":
		return True
	if safe_number(snapshot.get("starting_fcff")) <= 0 and safe_number(snapshot.get("starting_fcfe")) <= 0:
		return True
	return False


def _fallback_case_file(
	ticker: str,
	snapshot: Mapping[str, Any],
	info: Mapping[str, Any],
	search_results: list[Mapping[str, str]],
) -> str:
	company_name = snapshot.get("company_name") or ticker
	flags = _special_flags(snapshot, info)
	evidence = _supporting_evidence(snapshot, info, search_results)
	flag_lines = "\n".join(f"- {item}" for item in flags)
	evidence_lines = "\n".join(f"- {item}" for item in evidence)
	return f"""
## Minimal Case File

### Company Type
- {company_name}: {_company_type(snapshot, info)}

### Strategic Phase
- {_strategic_phase(snapshot, info)}

### Special Flags
{flag_lines}

### Brief Supporting Evidence
{evidence_lines}
""".strip()


def build_company_context(
	target_ticker: str,
	stock_data: Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	"""Build the lightweight pre-selection context case file."""

	_ = analysis_focus
	snapshot = build_company_snapshot(target_ticker, stock_data)
	info = getattr(stock_data, "info", stock_data) or {}
	company_name = str(snapshot.get("company_name") or target_ticker)
	source_links = build_source_links(target_ticker, stock_data)
	source_notes = build_source_hints(target_ticker, info)
	for note in get_relevant_filing_section_notes(target_ticker, max_sections=3):
		source_notes.append(note)
		if note.get("url"):
			source_links.append(str(note["url"]))
	search_results: list[Mapping[str, str]] = []
	if _should_pull_web_context(snapshot):
		search_results = search_company_market_context_results(target_ticker, max_results=2)
		for result in search_results:
			if result.get("url"):
				source_links.append(str(result["url"]))
			source_notes.append(
				{
					"title": result.get("title") or "Web result",
					"url": result.get("url"),
					"snippet": result.get("snippet") or "",
					"source_type": "web_search",
					"confidence": 0.4,
				}
			)

	executor = _build_agent_executor(target_ticker, company_name, model_name)
	if executor is not None:
		try:
			result = executor.invoke({"input": build_context_request(target_ticker, company_name)})
			case_file = str(result.get("output") or "").strip()
			if case_file:
				return {
					"summary": f"Lightweight context case file completed for {company_name}.",
					"report_markdown": case_file,
					"source_links": list(dict.fromkeys(link for link in source_links if link)),
					"source_notes": source_notes,
					"confidence": 0.7,
				}
		except Exception:
			pass

	case_file = _fallback_case_file(
		target_ticker,
		snapshot,
		info,
		search_results,
	)
	return {
		"summary": f"Lightweight fallback context case file completed for {company_name}.",
		"report_markdown": case_file,
		"source_links": list(dict.fromkeys(link for link in source_links if link)),
		"source_notes": source_notes,
		"confidence": 0.56,
	}


def _base_candidate_facts(stock_data: Any) -> list[dict[str, Any]]:
	"""Create deterministic candidate facts from the available market-data bundle."""

	info = getattr(stock_data, "info", stock_data) or {}
	defaults = default_valuation_inputs(
		info,
		annual_cashflow=getattr(stock_data, "annual_cashflow", None),
		annual_balance_sheet=getattr(stock_data, "annual_balance_sheet", None),
		annual_income_stmt=getattr(stock_data, "annual_income_stmt", None),
	)
	facts = [
		CandidateFact(key="sector", label="Sector", value=str(info.get("sector") or "N/A"), source="Yahoo Finance", confidence=0.9),
		CandidateFact(key="industry", label="Industry", value=str(info.get("industry") or "N/A"), source="Yahoo Finance", confidence=0.9),
		CandidateFact(key="current_price", label="Current Price", value=defaults["current_price"], numeric_value=defaults["current_price"], source="Yahoo Finance", confidence=0.95),
		CandidateFact(key="shares_outstanding", label="Shares Outstanding", value=defaults["shares_outstanding"], numeric_value=defaults["shares_outstanding"], source="Derived from market data", confidence=0.8),
		CandidateFact(key="starting_fcff", label="Starting FCFF", value=defaults["starting_fcff"], numeric_value=defaults["starting_fcff"], source="Derived from financial statements", confidence=0.8),
		CandidateFact(key="starting_fcfe", label="Starting FCFE", value=defaults["starting_fcfe"], numeric_value=defaults["starting_fcfe"], source="Derived from financial statements", confidence=0.8),
		CandidateFact(key="dividend_per_share", label="Dividend Per Share", value=defaults["dividend_per_share"], numeric_value=defaults["dividend_per_share"], source="Yahoo Finance", confidence=0.9),
		CandidateFact(key="book_value_per_share", label="Book Value Per Share", value=defaults["book_value_per_share"], numeric_value=defaults["book_value_per_share"], source="Yahoo Finance / balance sheet", confidence=0.85),
		CandidateFact(key="return_on_equity", label="Observed ROE", value=defaults["return_on_equity"], numeric_value=defaults["return_on_equity"], source="Yahoo Finance / derived", confidence=0.8),
		CandidateFact(key="payout_ratio", label="Observed Payout Ratio", value=defaults["payout_ratio"], numeric_value=defaults["payout_ratio"], source="Yahoo Finance / derived", confidence=0.8),
	]
	return [fact.model_dump() for fact in facts]


def _extract_target_mentions(research_report: str) -> list[dict[str, Any]]:
	"""Capture loose management-target clues from free-form research text."""

	facts: list[dict[str, Any]] = []
	for match in re.finditer(r"(?P<context>.{0,40})(?P<value>\d+(?:\.\d+)?)%(?P<trailing>.{0,40})", research_report, flags=re.IGNORECASE):
		context = f"{match.group('context')}{match.group('value')}%{match.group('trailing')}".strip()
		facts.append(
			CandidateFact(
				key="management_target_hint",
				label="Management Target Mention",
				value=context,
				source="Research memo",
				citation=context[:160],
				confidence=0.35,
				note="Loose percentage mention extracted from messy text; treat as directional context only.",
			).model_dump()
		)
		if len(facts) >= 3:
			break
	return facts


def _merge_candidate_facts(*fact_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Merge fact lists by key while preserving the highest-confidence entries."""

	merged: dict[str, dict[str, Any]] = {}
	for group in fact_groups:
		for fact in group:
			key = str(fact.get("key") or fact.get("label") or "").strip()
			if not key:
				continue
			current = merged.get(key)
			if current is None or float(fact.get("confidence") or 0) >= float(current.get("confidence") or 0):
				merged[key] = fact
	return list(merged.values())


def extract_candidate_facts(
	ticker: str,
	stock_data: Any,
	research_report: str,
	source_notes: list[Mapping[str, Any]],
	model_name: str | None = None,
) -> list[dict[str, Any]]:
	"""Turn messy source text into candidate facts that tolerate uncertainty."""

	base_facts = _base_candidate_facts(stock_data)
	narrative_facts = _extract_target_mentions(research_report)
	llm_facts: list[dict[str, Any]] = []

	llm_text = invoke_text_prompt(
		system_prompt="Return JSON only.",
		user_prompt=build_extraction_prompt(ticker, research_report, source_notes),
		model_name=model_name,
		temperature=0.0,
	)
	if llm_text:
		try:
			llm_facts = [
				CandidateFact.model_validate(item).model_dump()
				for item in extract_json_array(llm_text)
			]
		except Exception:
			llm_facts = []

	return _merge_candidate_facts(base_facts, narrative_facts, llm_facts)


__all__ = ["build_company_context", "extract_candidate_facts"]
