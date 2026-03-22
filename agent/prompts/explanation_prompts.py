from __future__ import annotations

from typing import Any, Mapping

from agent.prompts.system_prompts import build_role_system_prompt


def build_explanation_prompt(
	ticker: str,
	company_name: str,
	research_report: str,
	source_links: list[str],
	model_selection: Mapping[str, Any],
	parameter_payload: Mapping[str, Any],
	valuation_result: Mapping[str, Any],
	confidence: float | None,
) -> str:
	"""Prompt for the final explanation writer."""

	link_lines = "\n".join(f"- {link}" for link in source_links[:8])
	return f"""
{build_role_system_prompt("Senior fundamental equity analyst", "Write a comprehensive investment research report in the style of a traditional Morningstar equity research note, grounded in the supplied research, assumptions, valuation output, and sources.")}

Ticker: {ticker}
Company: {company_name}
Confidence: {confidence if confidence is not None else "unknown"}

Research summary:
{research_report or "No research report available."}

Model selection:
{dict(model_selection)}

Parameter payload:
{dict(parameter_payload)}

Valuation result:
{dict(valuation_result)}

Source links:
{link_lines or "- No source links available."}

Act as a senior fundamental equity analyst. Generate a comprehensive investment research report for {company_name or ticker} using the analytical framework and structure of a traditional Morningstar equity research report.

Please base your analysis on the most recent financial data and strategic developments available in the provided materials, and structure the output exactly as follows:

# {company_name or ticker} Investment Research Report

## 1. Investment Thesis & Snapshot
Provide a concise 2-3 paragraph summary of the company's core business model, current market position, and overarching investment thesis.

## 2. Economic Moat Assessment
Analyze the company's competitive advantage. Explicitly state a Moat Rating (Wide, Narrow, or None) and a Moat Trend (Positive, Stable, or Negative). Justify this by analyzing which of the five moat sources apply: Network Effect, Intangible Assets, Cost Advantage, Switching Costs, or Efficient Scale.

## 3. Valuation & Fair Value Drivers
Discuss the primary drivers that dictate intrinsic value, including long-term revenue growth assumptions, terminal operating margins where relevant, cost of capital, and capex needs. Conclude with a qualitative assessment of whether the stock appears undervalued, fairly valued, or overvalued relative to the current market price.

## 4. Risk & Uncertainty
Assess the primary risks threatening the business model. Assign an Uncertainty Rating (Low, Medium, High, or Very High) and explain the reasoning.

## 5. Capital Allocation & Management Stewardship
Evaluate management's track record regarding shareholder value creation. Discuss balance sheet management, dividend policy, share buybacks, and M&A history. Rate Capital Allocation as Exemplary, Standard, or Poor, and justify the rating.

## 6. Bulls Say / Bears Say
### Bulls Say
Provide a short paragraph summarizing the best-case scenario and bullish arguments.
### Bears Say
Provide a short paragraph summarizing the worst-case scenario and bearish arguments.

## 7. Financial Health
Provide a brief overview of balance sheet strength, leverage, liquidity, and free cash flow generation.

Formatting rules:
- Use exactly one H1 (`#`) for the main report title.
- Use H2 (`##`) for all primary sections.
- Use H3 (`###`) only for specific subsections such as Bulls Say and Bears Say.
- Do not use H4 or below.
- Use Markdown tables for any quantitative data, key financial metrics, valuation ratios, or competitor-style comparisons.
- Do not bury important numbers inside long paragraphs when a table would be clearer.
- Use bolding only for key terms, specific metrics, or company names.
- Ensure clear blank lines between headings, paragraphs, lists, and tables.
- Keep the tone crisp, objective, and structurally consistent.
- Prefer paragraphs over bullet lists throughout the report. Only use a list if a paragraph would clearly reduce readability.

Important:
- Write markdown only.
- Follow the section order exactly.
- Use the provided deterministic valuation result when discussing fair value.
- Do not invent data that is not reasonably supported by the supplied materials.
""".strip()
