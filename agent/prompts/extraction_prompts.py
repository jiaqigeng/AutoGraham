from __future__ import annotations

from typing import Any, Mapping

from agent.prompts.system_prompts import build_role_system_prompt


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
{build_role_system_prompt("Source extractor", "Extract candidate facts from messy notes without pretending all data is certain.")}

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
