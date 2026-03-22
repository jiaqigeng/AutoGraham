from __future__ import annotations

from typing import Any, Mapping

from agent.deep_agent import invoke_text_prompt
from agent.prompts.explanation_prompts import build_explanation_prompt


def _format_citations(source_links: list[str], source_notes: list[Mapping[str, Any]]) -> str:
	"""Format a short source section for the fallback explanation."""

	note_lines = []
	for note in source_notes[:5]:
		title = note.get("title") or note.get("url") or "Source"
		url = note.get("url")
		if url:
			note_lines.append(f"- [{title}]({url})")
		else:
			note_lines.append(f"- {title}")
	for link in source_links[:5]:
		if not any(link == note.get("url") for note in source_notes):
			note_lines.append(f"- {link}")
	return "\n".join(note_lines) or "- No external sources were captured."


def _fallback_explanation(
	ticker: str,
	company_name: str,
	source_links: list[str],
	source_notes: list[Mapping[str, Any]],
	model_selection: Mapping[str, Any],
	parameter_payload: Mapping[str, Any],
	valuation_result: Mapping[str, Any],
	confidence: float | None,
) -> str:
	"""Deterministic explanation used when the final explainer LLM is unavailable."""

	selected_model = model_selection.get("selected_model") or valuation_result.get("selected_model") or "the selected valuation model"
	model_reason = model_selection.get("model_reason") or parameter_payload.get("parameter_reason") or "the chosen framework best matches the company's cash-flow profile and capital intensity."
	fair_value = valuation_result.get("fair_value_per_share", "N/A")
	current_price = valuation_result.get("current_price", "N/A")
	margin = valuation_result.get("margin_of_safety", "N/A")
	assumption_rows = "\n".join(
		f"| **{item.get('label') or item.get('key')}** | {item.get('value')} | {item.get('reason')} |"
		for item in (valuation_result.get("assumptions") or [])[:6]
	)
	financial_rows = []
	for fact in (parameter_payload.get("fetched_facts") or [])[:8]:
		label = fact.get("label") or fact.get("key")
		value = fact.get("value")
		source = fact.get("source") or "Workflow anchor"
		if label in {"Total Debt", "Cash", "Shares Outstanding", "Starting FCFF", "Starting FCFE", "Book Value per Share", "Current Price"}:
			financial_rows.append(f"| **{label}** | {value} | {source} |")
	financial_table = "\n".join(financial_rows)
	return f"""
# {company_name or ticker} Investment Research Report

## 1. Investment Thesis & Snapshot
{company_name or ticker} is being evaluated as a mature operating business with a large installed base, established market position, and valuation driven more by durability and cash generation than by early-stage expansion. The current workflow combines broad company research with a deterministic valuation model to frame whether the market price is justified by long-run fundamentals.

The overarching thesis is that investors should focus on the resilience of the business model, the company's ability to convert scale into free cash flow, and whether the current market price already embeds those strengths. The valuation work here uses **{selected_model}**, with the workflow concluding that this framework best fits the economics of the business. Confidence is **{confidence if confidence is not None else 'unknown'}**.

## 2. Economic Moat Assessment
**Moat Rating:** Narrow  
**Moat Trend:** Stable

The company appears to benefit from a mix of intangible assets, switching costs, and scale advantages, although the exact moat width still depends on industry structure and execution. This fallback view is intentionally conservative because it is based on the workflow artifacts rather than a fresh analyst rewrite from full source review.

## 3. Valuation & Fair Value Drivers
The primary fair value drivers are the explicit forecast assumptions, discount rate, terminal growth, and reinvestment intensity. The workflow chose **{selected_model}** because {model_reason}

| Metric | Value |
| --- | --- |
| **Model** | {selected_model} |
| **Fair Value / Share** | {fair_value} |
| **Current Price** | {current_price} |
| **Margin of Safety** | {margin} |
| **Confidence** | {confidence if confidence is not None else 'unknown'} |

Key assumptions retained by the workflow:

| Assumption | Value | Reason |
| --- | --- | --- |
{assumption_rows or "| **No assumptions recorded** | N/A | The valuation did not complete successfully. |"}

On that basis, the shares appear qualitatively aligned with whether the market price sits below, near, or above the modeled fair value.

## 4. Risk & Uncertainty
**Uncertainty Rating:** Medium

The main risks are that business quality or industry economics may have been misread during the broad research pass, missing or stale financial data may weaken the fetched facts and downstream assumptions, and long-term growth, margins, capex, and discount-rate judgments remain the most sensitive drivers in the valuation.

## 5. Capital Allocation & Management Stewardship
**Capital Allocation Rating:** Standard

Management quality should be judged by how consistently capital is deployed into reinvestment, shareholder returns, and balance sheet discipline. The current workflow does not independently audit management, so this fallback rating stays neutral rather than overstating conviction.

## 6. Bulls Say / Bears Say
### Bulls Say
The bullish case is that the company can sustain stronger cash generation and returns on capital than the market expects, that scale and competitive positioning can support more durable growth and margins, and that steady execution could make the current valuation understate long-run intrinsic value.

### Bears Say
The bearish case is that competitive pressure, regulation, or weaker demand could compress growth and profitability, reinvestment needs could stay higher than expected and weigh on free cash flow conversion, and the market may already be pricing in assumptions that leave little room for error.

## 7. Financial Health
The company should be judged on balance sheet flexibility, liquidity, leverage tolerance, and free cash flow generation. The deterministic workflow is designed to anchor that assessment through observed facts and model-ready assumptions, but this fallback summary should still be treated as a directional overview rather than a full credit memo.

| Metric | Value | Source |
| --- | --- | --- |
{financial_table or "| **Current Price** | " + str(current_price) + " | Workflow anchor |"}
""".strip()


def explain_valuation(
	*,
	ticker: str,
	company_name: str,
	research_report: str,
	source_links: list[str],
	source_notes: list[Mapping[str, Any]],
	candidate_facts: list[Mapping[str, Any]],
	model_selection: Mapping[str, Any],
	parameter_payload: Mapping[str, Any],
	valuation_result: Mapping[str, Any],
	confidence: float | None,
	model_name: str | None,
) -> str:
	"""Explain the deterministic valuation output and cite what shaped it."""

	llm_text = invoke_text_prompt(
		system_prompt="Write markdown only.",
		user_prompt=build_explanation_prompt(
			ticker=ticker,
			company_name=company_name,
			research_report=research_report,
			source_links=source_links,
			model_selection=model_selection,
			parameter_payload=parameter_payload,
			valuation_result=valuation_result,
			confidence=confidence,
		),
		model_name=model_name,
		temperature=0.2,
	)
	if llm_text:
		return llm_text
	return _fallback_explanation(
		ticker=ticker,
		company_name=company_name,
		source_links=source_links,
		source_notes=source_notes,
		model_selection=model_selection,
		parameter_payload=parameter_payload,
		valuation_result=valuation_result,
		confidence=confidence,
	)
