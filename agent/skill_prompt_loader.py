from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


VALUATION_AGENT_SYSTEM_PROMPT = """
You are AutoGraham, an equity valuation research agent for a Python + Streamlit app.

Operating rules:
- Research broadly before narrowing to model-ready inputs.
- Keep fetched facts separate from estimated assumptions.
- Never freestyle the final fair value when deterministic Python valuation functions are available.
- Be transparent about uncertainty, missing data, and source quality.
- Prefer conservative assumptions when the evidence is incomplete.
- Cite source links and source notes when explaining conclusions.
""".strip()


def _skills_dir() -> Path:
	return Path(__file__).resolve().parent / "skills"


@lru_cache(maxsize=None)
def _load_skill_template(filename: str) -> str:
	return (_skills_dir() / filename).read_text(encoding="utf-8")


def _render_template(template: str, values: Mapping[str, str]) -> str:
	rendered = template
	for key, value in values.items():
		rendered = rendered.replace(f"{{{{{key}}}}}", value)
	return rendered


def _format_candidate_facts(candidate_facts: list[Mapping[str, Any]]) -> str:
	return "\n".join(
		f"- {fact.get('label')}: {fact.get('value')} ({fact.get('note') or fact.get('source') or 'context unknown'})"
		for fact in candidate_facts[:16]
	) or "- No candidate facts provided."


def _format_source_links(source_links: list[str]) -> str:
	return "\n".join(f"- {link}" for link in source_links[:8]) or "- No source links available."


def _json_text(payload: Mapping[str, Any]) -> str:
	return json.dumps(dict(payload), indent=2, default=str, sort_keys=True)


def build_context_request(
	target_ticker: str,
	company_name: str | None = None,
) -> str:
	"""Request for the lightweight first-pass context case file."""

	identity = company_name or target_ticker
	return f"""
Context target:
- company_name_hint: {identity}
- ticker: {target_ticker}

Execution reminder:
- confirm the company name and ticker if the source material supports it
- build only the minimal case file needed before model selection
- use tools lightly and only when needed
- keep the output concise and decision-useful
""".strip()


def build_context_system_prompt(target_ticker: str, company_name: str | None = None) -> str:
	"""Prompt for the lightweight context-builder stage."""

	return _render_template(
		_load_skill_template("context_builder.md"),
		{
			"company_name_hint": company_name or target_ticker,
			"ticker": target_ticker,
		},
	).strip()


def build_model_selection_prompt(
	ticker: str,
	company_name: str,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for choosing DCF, DDM, or RIM and the right variant."""

	return _render_template(
		_load_skill_template("model_selection.md"),
		{
			"ticker": ticker,
			"company_name": company_name,
			"candidate_facts": _format_candidate_facts(candidate_facts),
			"analysis_focus": analysis_focus or "Prefer the model family that best matches the economics of the business.",
		},
	).strip()


def build_dcf_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	calculation_model: str | None = None,
	selected_projection_years: int | None = None,
	projection_years_reason: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for DCF parameter assembly."""

	_ = selected_variant
	return _render_template(
		_load_skill_template("dcf_parameter_research.md"),
		{
			"ticker": ticker,
			"calculation_model": (calculation_model or "FCFF").upper(),
			"selected_projection_years": str(selected_projection_years or "Not provided"),
			"projection_years_reason": projection_years_reason or "No model-selection horizon rationale was provided.",
			"candidate_facts": _format_candidate_facts(candidate_facts),
			"analysis_focus": analysis_focus or "Use conservative assumptions when the evidence is incomplete.",
		},
	).strip()


def build_ddm_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	selected_projection_years: int | None = None,
	projection_years_reason: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for DDM parameter assembly."""

	return _render_template(
		_load_skill_template("ddm_parameter_research.md"),
		{
			"ticker": ticker,
			"selected_variant": selected_variant or "None",
			"selected_projection_years": str(selected_projection_years or "Not provided"),
			"projection_years_reason": projection_years_reason or "No model-selection horizon rationale was provided.",
			"candidate_facts": _format_candidate_facts(candidate_facts),
			"analysis_focus": analysis_focus or "Use conservative assumptions when the evidence is incomplete.",
		},
	).strip()


def build_rim_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	selected_projection_years: int | None = None,
	projection_years_reason: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for RIM parameter assembly."""

	return _render_template(
		_load_skill_template("rim_parameter_research.md"),
		{
			"ticker": ticker,
			"selected_variant": selected_variant or "None",
			"selected_projection_years": str(selected_projection_years or "Not provided"),
			"projection_years_reason": projection_years_reason or "No model-selection horizon rationale was provided.",
			"candidate_facts": _format_candidate_facts(candidate_facts),
			"analysis_focus": analysis_focus or "Use conservative assumptions when the evidence is incomplete.",
		},
	).strip()


def build_parameter_prompt(
	ticker: str,
	selected_model: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	calculation_model: str | None = None,
	selected_projection_years: int | None = None,
	projection_years_reason: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	"""Dispatch to the model-specific parameter prompt builder."""

	selected = str(selected_model or "").upper()
	if selected == "DCF":
		return build_dcf_parameter_prompt(
			ticker=ticker,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			calculation_model=calculation_model,
			selected_projection_years=selected_projection_years,
			projection_years_reason=projection_years_reason,
			analysis_focus=analysis_focus,
		)
	if selected == "DDM":
		return build_ddm_parameter_prompt(
			ticker=ticker,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			selected_projection_years=selected_projection_years,
			projection_years_reason=projection_years_reason,
			analysis_focus=analysis_focus,
		)
	return build_rim_parameter_prompt(
		ticker=ticker,
		selected_variant=selected_variant,
		candidate_facts=candidate_facts,
		selected_projection_years=selected_projection_years,
		projection_years_reason=projection_years_reason,
		analysis_focus=analysis_focus,
	)


def build_extraction_prompt(
	ticker: str,
	research_report: str,
	source_notes: list[Mapping[str, Any]],
) -> str:
	"""Prompt for extracting tolerant structured facts from messy notes."""

	note_lines = "\n".join(
		f"- {note.get('title') or note.get('url') or 'Source'}: {note.get('snippet') or ''}".strip()
		for note in source_notes[:8]
	)
	return f"""
{VALUATION_AGENT_SYSTEM_PROMPT}

Specialized role: Source extractor.
Extract candidate facts from messy notes without pretending all data is certain.

Ticker: {ticker}

Research report:
{research_report or "No research report provided."}

Source notes:
{note_lines or "- No source notes available."}

Return JSON only with this shape:
[
  {{
    "key": "current_price",
    "label": "Current Price",
    "value": 123.45,
    "numeric_value": 123.45,
    "source": "Yahoo Finance",
    "citation": "brief citation",
    "confidence": 0.75,
    "note": "optional context"
  }}
]
""".strip()


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

	return _render_template(
		_load_skill_template("investment_writeup.md"),
		{
			"ticker": ticker,
			"company_name": company_name,
			"confidence": str(confidence if confidence is not None else "unknown"),
			"research_report": research_report or "No research report available.",
			"model_selection": _json_text(model_selection),
			"parameter_payload": _json_text(parameter_payload),
			"valuation_result": _json_text(valuation_result),
			"source_links": _format_source_links(source_links),
		},
	).strip()


__all__ = [
	"VALUATION_AGENT_SYSTEM_PROMPT",
	"build_context_request",
	"build_context_system_prompt",
	"build_dcf_parameter_prompt",
	"build_ddm_parameter_prompt",
	"build_explanation_prompt",
	"build_extraction_prompt",
	"build_model_selection_prompt",
	"build_parameter_prompt",
	"build_rim_parameter_prompt",
]
