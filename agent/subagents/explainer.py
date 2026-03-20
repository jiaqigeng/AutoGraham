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

	fact_lines = "\n".join(
		f"- {fact.get('label')}: {fact.get('value')} ({fact.get('source') or 'source unknown'})"
		for fact in (parameter_payload.get("fetched_facts") or [])[:6]
	)
	assumption_lines = "\n".join(
		f"- {item.get('key')}: {item.get('value')} ({item.get('reason')})"
		for item in (valuation_result.get("assumptions") or [])[:6]
	)
	return f"""
## Why This Model Fits
The workflow chose **{model_selection.get('selected_model') or valuation_result.get('selected_model') or 'a valuation model'}** for {company_name or ticker} because it best matched the business profile identified during broad research. Variant: **{model_selection.get('selected_variant') or valuation_result.get('growth_stage') or 'None'}**.

## Fetched Facts
{fact_lines or "- No fetched facts were retained in the final payload."}

## Estimated Assumptions
{assumption_lines or "- No assumptions were recorded because the valuation did not complete successfully."}

## Fair Value Vs Market Price
Fair value per share: **{valuation_result.get('fair_value_per_share', 'N/A')}**
Current market price: **{valuation_result.get('current_price', 'N/A')}**
Margin of safety: **{valuation_result.get('margin_of_safety', 'N/A')}**
Confidence: **{confidence if confidence is not None else 'unknown'}**

## Main Risks
- Business quality or industry economics may have been misread during the broad research pass.
- Missing or stale financial data can weaken fetched facts and downstream assumptions.
- Long-term growth and discount-rate assumptions remain the most sensitive drivers.

## Sources
{_format_citations(source_links, source_notes)}
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
