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
{build_role_system_prompt("Valuation explainer", "Explain the workflow clearly and cite which facts and sources shaped the output.")}

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

Write markdown with:
- why this model was chosen
- fetched facts
- estimated assumptions
- fair value vs current market price
- main risks
- source citations
""".strip()
