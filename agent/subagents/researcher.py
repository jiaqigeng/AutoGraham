from __future__ import annotations

from typing import Any, Mapping

from agent.deep_agent import build_chat_model, response_text
from agent.prompts.research_prompts import build_research_request, build_research_system_prompt
from agent.tools.finance_tools import (
	build_company_snapshot,
	build_source_links,
	get_cash_flow_health,
	get_company_profile_text,
	get_income_statement,
	get_valuation_metrics,
)
from agent.tools.sec_tools import build_source_hints, get_filing_source_hints
from agent.tools.web_search import search_market_context, search_market_context_results


def _build_agent_executor(target_ticker: str, company_name: str, model_name: str | None):
	try:
		from langchain.agents import AgentExecutor, create_tool_calling_agent
		from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
	except ImportError:
		return None

	llm = build_chat_model(model_name, temperature=0.1)
	if llm is None:
		return None

	tools = [
		get_company_profile_text,
		get_valuation_metrics,
		get_income_statement,
		get_cash_flow_health,
		get_filing_source_hints,
		search_market_context,
	]
	prompt = ChatPromptTemplate.from_messages(
		[
			("system", build_research_system_prompt(target_ticker, company_name)),
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
		max_iterations=8,
	)


def _fallback_research_report(
	ticker: str,
	snapshot: Mapping[str, Any],
	analysis_focus: str | None,
	search_results: list[Mapping[str, str]],
) -> str:
	"""Deterministic broad research summary used when the live agent cannot run."""

	search_lines = "\n".join(
		f"- {item.get('title')}: {item.get('snippet') or item.get('url')}"
		for item in search_results[:3]
	)
	return f"""
## Business Profile
{snapshot.get('company_name')} operates in {snapshot.get('sector')} / {snapshot.get('industry')}. The broad research pass is collecting model-fit clues before estimating final valuation parameters.

## Initial Valuation Read
- Current price anchor: {snapshot.get('current_price')}
- Dividend per share anchor: {snapshot.get('dividend_per_share')}
- Book value per share anchor: {snapshot.get('book_value_per_share')}
- Starting FCFF anchor: {snapshot.get('starting_fcff')}
- Starting FCFE anchor: {snapshot.get('starting_fcfe')}
- Observed ROE anchor: {snapshot.get('return_on_equity')}

## Candidate Model Fit
- DCF is plausible when cash-flow anchors are usable and the business is best framed as an operating company.
- DDM is plausible when dividends are meaningful and central to shareholder returns.
- RIM is plausible when book value and ROE are more informative than direct cash-flow forecasts.

## What Still Needs Narrowing
- Which valuation family best matches the economics of the business
- Which observed facts can be trusted as fetched facts
- Which growth and discount-rate assumptions should be conservative estimates

## Market Context
{search_lines or "- No live web-search context was available during this run."}

## User Focus
{analysis_focus or "No extra user focus was provided."}
""".strip()


def research_company(
	target_ticker: str,
	stock_data: Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	"""Run the broad first-pass valuation research step."""

	snapshot = build_company_snapshot(target_ticker, stock_data)
	company_name = str(snapshot.get("company_name") or target_ticker)
	source_links = build_source_links(target_ticker, stock_data)
	source_notes = build_source_hints(target_ticker, getattr(stock_data, "info", stock_data) or {})
	search_results = search_market_context_results(f"{target_ticker} valuation business risks competitors", max_results=3)
	for result in search_results:
		if result.get("url"):
			source_links.append(str(result["url"]))
		source_notes.append(
			{
				"title": result.get("title") or "Web result",
				"url": result.get("url"),
				"snippet": result.get("snippet") or "",
				"source_type": "web_search",
				"confidence": 0.45,
			}
		)

	executor = _build_agent_executor(target_ticker, company_name, model_name)
	if executor is not None:
		try:
			result = executor.invoke({"input": build_research_request(target_ticker, company_name, analysis_focus)})
			report_markdown = str(result.get("output") or "").strip()
			if report_markdown:
				return {
					"summary": f"Broad research completed for {company_name}.",
					"report_markdown": report_markdown,
					"source_links": list(dict.fromkeys(link for link in source_links if link)),
					"source_notes": source_notes,
					"confidence": 0.72,
				}
		except Exception:
			pass

	report_markdown = _fallback_research_report(
		target_ticker,
		snapshot,
		analysis_focus,
		search_results,
	)
	return {
		"summary": f"Broad research fallback completed for {company_name}.",
		"report_markdown": report_markdown,
		"source_links": list(dict.fromkeys(link for link in source_links if link)),
		"source_notes": source_notes,
		"confidence": 0.58,
	}
