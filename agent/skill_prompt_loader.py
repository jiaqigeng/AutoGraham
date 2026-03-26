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


def _research_skills_dir() -> Path:
	return Path(__file__).resolve().parent / "subagents" / "research" / "skills"


@lru_cache(maxsize=None)
def _load_template(path: str) -> str:
	return Path(path).read_text(encoding="utf-8")


def _load_skill_template(filename: str) -> str:
	return _load_template(str(_skills_dir() / filename))


def _load_research_skill(skill_name: str) -> str:
	return _load_template(str(_research_skills_dir() / skill_name / "SKILL.md"))


def _render_template(template: str, values: Mapping[str, str]) -> str:
	rendered = template
	for key, value in values.items():
		rendered = rendered.replace(f"{{{{{key}}}}}", value)
	return rendered


def _split_skill_prompt_sections(template: str) -> tuple[str, str]:
	_, marker, remainder = template.partition("## System Prompt")
	if not marker:
		raise ValueError("Skill markdown is missing a '## System Prompt' section.")
	system_prompt, user_marker, user_prompt = remainder.partition("## User Prompt Template")
	if not user_marker:
		raise ValueError("Skill markdown is missing a '## User Prompt Template' section.")
	return system_prompt.strip(), user_prompt.strip()


def _render_research_skill_prompts(skill_name: str, values: Mapping[str, str]) -> tuple[str, str]:
	system_template, user_template = _split_skill_prompt_sections(_load_research_skill(skill_name))
	return _render_template(system_template, values).strip(), _render_template(user_template, values).strip()


def _format_candidate_facts(candidate_facts: list[Mapping[str, Any]]) -> str:
	return "\n".join(
		f"- {fact.get('label')}: {fact.get('value')} ({fact.get('note') or fact.get('source') or 'context unknown'})"
		for fact in candidate_facts[:16]
	) or "- No candidate facts provided."


def _format_source_links(source_links: list[str]) -> str:
	return "\n".join(f"- {link}" for link in source_links[:8]) or "- No source links available."


def _json_text(payload: Mapping[str, Any]) -> str:
	return json.dumps(dict(payload), indent=2, default=str, sort_keys=True)


def _format_lines(lines: list[str], empty_message: str) -> str:
	return "\n".join(line for line in lines if str(line or "").strip()) or empty_message


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


def build_macro_analysis_prompts(
	ticker: str,
	company_name: str,
	sector: str,
	industry: str,
	competitors: list[str],
	macro_lines: list[str],
	company_news_lines: list[str],
	market_news_lines: list[str],
	tailwind_lines: list[str],
	headwind_lines: list[str],
	analysis_focus: str | None = None,
) -> tuple[str, str]:
	"""Prompt pair for the research macro analysis agent."""

	return _render_research_skill_prompts(
		"macro_agent",
		{
			"ticker": ticker.upper(),
			"company_name": company_name,
			"sector": sector,
			"industry": industry,
			"analysis_focus": analysis_focus or "Assess the environment the company operates in over the next 3-5 years.",
			"competitors": ", ".join(competitors) if competitors else "Not confidently inferred from the cached packet.",
			"macro_lines": _format_lines(macro_lines, "- No FRED macro series available."),
			"company_news_lines": _format_lines(company_news_lines, "- No cached company news available."),
			"market_news_lines": _format_lines(market_news_lines, "- No cached market news available."),
			"tailwind_lines": _format_lines(tailwind_lines, "- None confidently extracted."),
			"headwind_lines": _format_lines(headwind_lines, "- None confidently extracted."),
		},
	)


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


def build_qualitative_analysis_prompts(
	ticker: str,
	company_summary: str,
	revenue_driver_lines: list[str],
	moat_lines: list[str],
	risk_lines: list[str],
	analysis_focus: str | None = None,
) -> tuple[str, str]:
	"""Prompt pair for the research qualitative analysis agent."""

	return _render_research_skill_prompts(
		"qualitative_agent",
		{
			"ticker": ticker.upper(),
			"company_summary": company_summary or "No company summary available.",
			"analysis_focus": analysis_focus or "Assess durability, primary revenue drivers, and management risk tone.",
			"revenue_driver_lines": _format_lines(revenue_driver_lines, "- No clear excerpts."),
			"moat_lines": _format_lines(moat_lines, "- No clear excerpts."),
			"risk_lines": _format_lines(risk_lines, "- No clear excerpts."),
		},
	)


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
) -> tuple[str, str]:
	"""Prompt pair for extracting tolerant structured facts from messy notes."""

	note_lines = "\n".join(
		f"- {note.get('title') or note.get('url') or 'Source'}: {note.get('snippet') or ''}".strip()
		for note in source_notes[:8]
	)
	return _render_research_skill_prompts(
		"source_extractor",
		{
			"valuation_agent_system_prompt": VALUATION_AGENT_SYSTEM_PROMPT,
			"ticker": ticker,
			"research_report": research_report or "No research report provided.",
			"source_notes": note_lines or "- No source notes available.",
		},
	)


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
	"build_macro_analysis_prompts",
	"build_dcf_parameter_prompt",
	"build_ddm_parameter_prompt",
	"build_explanation_prompt",
	"build_extraction_prompt",
	"build_model_selection_prompt",
	"build_parameter_prompt",
	"build_qualitative_analysis_prompts",
	"build_rim_parameter_prompt",
]
