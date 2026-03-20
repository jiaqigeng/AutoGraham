from __future__ import annotations

from typing import Any, Mapping


def build_model_selection_prompt(
	ticker: str,
	company_name: str,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for choosing DCF, DDM, or RIM and the right variant."""

	fact_lines = "\n".join(
		f"- {fact.get('label')}: {fact.get('value')} ({fact.get('source') or 'source unknown'})"
		for fact in candidate_facts[:12]
	)
	focus = analysis_focus or "Prefer the model family that best matches the economics of the business."
	return f"""
You are the valuation model selection specialist for AutoGraham.

Your job is to choose the most appropriate valuation model and model variant for a company analysis.

Ticker: {ticker}
Company: {company_name}

Candidate facts:
{fact_lines or "- No candidate facts provided."}

Available valuation models:
- DCF
- DDM
- RIM

Available variants for reasoning:
- single_stage
- two_stage
- multi_stage

Variant output mapping for AutoGraham:
- single_stage -> "Single-Stage (Stable)"
- two_stage -> "Two-Stage"
- multi_stage -> "Three-Stage (Multi-stage decay)"
- If you select RIM, set "selected_variant" to null

Your responsibilities:
1. Review the company's business type, financial characteristics, and available candidate facts.
2. Decide which valuation model is most appropriate.
3. Decide which variant is most appropriate.
4. Explain the reasoning clearly.
5. Identify which exact parameters are required next.
6. Identify which data points are already available and which are missing or weak.

Important rules:
- Do NOT calculate the final fair value.
- Do NOT invent precise financial inputs unless explicitly asked.
- Do NOT force one model just because some data exists.
- Prefer the model that best fits the business and the quality of available information.
- Use practical valuation judgment, not rigid textbook dogma.
- Treat candidate facts as possibly messy or incomplete.
- Separate factual observations from judgment.
- Be conservative when uncertain.

High-level model guidance:
- RIM is often more appropriate for banks, insurers, and other financial firms where book value and return on equity are central.
- DDM is often more appropriate for mature, stable dividend-paying companies when dividends are meaningful and relatively predictable.
- DCF is often more appropriate for operating companies where cash flow is the core driver and reasonably estimable.
- If the company is in transition or expected to normalize over time, prefer two_stage or multi_stage.
- If the company appears already close to steady-state, single_stage may be appropriate.
- If there is enough information for an explicit year-by-year path, prefer multi_stage.
- If only near-term vs normalized assumptions are supportable, prefer two_stage.
- Additional analysis focus: {focus}

Output requirements:
- You must output structured JSON only.
- Do not output markdown.
- "selected_model" must be exactly one of: "DCF", "DDM", "RIM".
- "selected_variant" must be exactly one of: "Single-Stage (Stable)", "Two-Stage", "Three-Stage (Multi-stage decay)", or null.
- "preferred_calculation_model" must be "FCFF" or "FCFE" when "selected_model" is "DCF".
- "preferred_calculation_model" must be "DDM" when "selected_model" is "DDM".
- "preferred_calculation_model" must be "RIM" when "selected_model" is "RIM".
- Keep the response practical for deterministic Python valuation.

Return structured JSON only:
{{
  "selected_model": "DCF",
  "selected_variant": "Two-Stage",
  "preferred_calculation_model": "FCFF",
  "model_reason": "brief explanation",
  "confidence": 0.72,
  "required_parameters_next": ["current_fcff", "shares_outstanding", "wacc", "high_growth", "projection_years", "terminal_growth", "total_debt", "cash", "current_price"],
  "available_data_points": ["current_price", "shares_outstanding"],
  "missing_or_weak_data_points": ["current_fcff", "wacc"]
}}
""".strip()
