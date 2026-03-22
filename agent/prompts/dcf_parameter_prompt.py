from __future__ import annotations

from typing import Any, Mapping

from agent.prompts._parameter_prompt_common import format_candidate_facts


def _build_fcff_driver_prompt(
	ticker: str,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None,
) -> str:
	focus = analysis_focus or "Use conservative assumptions when the evidence is incomplete."
	return f"""
You are the DCF parameter estimation specialist for AutoGraham.

Your task is to build the full input payload for the Python function
`calculate_fcff_dcf_from_drivers(...)` in `dcf.py`.

Model selection has already been completed.
Do NOT evaluate whether FCFF DCF is appropriate.
Do NOT include model-suitability discussion.
Focus only on producing a coherent year-by-year FCFF forecast.

Important working style:
- Try to look for relevant info and consensus through public and free online sources, but do not get stuck on hunting for sources or listing sources.
- Use the workflow clues below as context, then apply financial judgment.
- If evidence is incomplete, still make a conservative estimate instead of refusing.
- Keep the forecast internally consistent and economically plausible.
- Estimate only `projection_years` and the exact inputs required by the Python function. Do not introduce extra assumption fields.

What you must estimate:
1. Choose `projection_years`.
   Pay special attention to whether the company is still in a buildout, scaling, restructuring, or transition phase. If the business is still going through major changes in growth, margins, reinvestment, capital intensity, or operating model, use a longer forecast horizon. If the business is already mature and largely stable, use a shorter horizon.
2. For every year in `projection_years`, estimate:
   - revenue
   - ebit_margin
   - tax_rate
   - depreciation
   - capex
   - change_in_nwc
3. Estimate scalar discount-rate, terminal, and balance-sheet inputs:
   - wacc
   - terminal_growth
   - total_debt
   - cash
   - shares_outstanding

Do not estimate any additional model inputs beyond the fields listed above.

Revenue estimation guidance:
- Forecast revenue year by year from the latest actual revenue base.
- Keep near-term growth consistent with current momentum, but if the company is in a buildout or transition phase, allow stronger growth for longer before fading.
- As the revenue base gets larger, gradually reduce growth toward a believable mature-state level.
- Keep the path smooth, realistic, and internally consistent.
- For revenue forecasting, reason in terms of `revenue`, `growth_rates`, and a short reason, but in the final full payload return `inputs.revenue` and summarize the reasoning in `assumption_notes.revenue`. Do not add a separate `growth_rates` field.

Capex estimation guidance:
- Estimate how long the current buildout lasts.
- During the buildout, keep capex elevated.
- After the buildout ends, reduce capex by removing the temporary expansion component, but do not assume capex disappears or immediately returns to old historical levels.
- Keep enough capex for maintenance, replacement, and normal long-run growth.
- Summarize that logic briefly in `assumption_notes.capex` while returning the year-by-year values in `inputs.capex`.

FCFF-specific rule:
- Estimate `wacc` directly as one scalar discount rate applied across the explicit forecast and terminal value.

Validation rules:
- Every forecast array must have exactly `projection_years` items.
- `wacc` must be greater than `terminal_growth`.
- Keep units consistent across the full payload.
- Terminal assumptions should be mature and not more aggressive than the late explicit forecast without a clear reason.
- Do not add extra keys inside `inputs`.

Return raw JSON only in this structure:
{{
  "company": "string",
  "ticker": "string",
  "currency": "string",
  "projection_years": 0,
  "projection_rationale": "string",
  "assumption_notes": {{
    "projection_years": "string",
    "revenue": "string",
    "ebit_margin": "string",
    "tax_rate": "string",
    "depreciation": "string",
    "capex": "string",
    "change_in_nwc": "string",
    "wacc": "string",
    "terminal_growth": "string",
    "total_debt": "string",
    "cash": "string",
    "shares_outstanding": "string"
  }},
  "inputs": {{
    "revenue": [],
    "ebit_margin": [],
    "tax_rate": [],
    "depreciation": [],
    "capex": [],
    "change_in_nwc": [],
    "wacc": 0.0,
    "terminal_growth": 0.0,
    "total_debt": 0.0,
    "cash": 0.0,
    "shares_outstanding": 0.0
  }},
  "model_warnings": ["string"]
}}

Existing workflow clues:
- Additional analysis focus: {focus}
- Candidate facts:
{format_candidate_facts(candidate_facts)}

Target company:
{ticker}
""".strip()


def _build_fcfe_driver_prompt(
	ticker: str,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None,
) -> str:
	focus = analysis_focus or "Use conservative assumptions when the evidence is incomplete."
	return f"""
You are the DCF parameter estimation specialist for AutoGraham.

Your task is to build the full input payload for the Python function
`calculate_fcfe_dcf_from_drivers(...)` in `dcf.py`.

Model selection has already been completed.
Do NOT evaluate whether FCFE DCF is appropriate.
Do NOT include model-suitability discussion.
Focus only on producing a coherent year-by-year FCFE forecast.

Important working style:
- Try to look for relevant info and consensus through public and free online sources, but do not get stuck on hunting for sources or listing sources.
- Use the workflow clues below as context, then apply financial judgment.
- If evidence is incomplete, still make a conservative estimate instead of refusing.
- Keep the forecast internally consistent and economically plausible.
- Estimate only `projection_years` and the exact inputs required by the Python function. Do not introduce extra assumption fields.

What you must estimate:
1. Choose `projection_years`.
   Pay special attention to whether the company is still in a buildout, scaling, restructuring, or transition phase. If the business is still going through major changes in growth, margins, reinvestment, capital intensity, or operating model, use a longer forecast horizon. If the business is already mature and largely stable, use a shorter horizon.
2. For every year in `projection_years`, estimate:
   - revenue
   - ebit_margin
   - tax_rate
   - depreciation
   - capex
   - change_in_nwc
   - net_borrowing
3. Estimate scalar discount-rate and terminal inputs:
   - cost_of_equity
   - terminal_growth
   - shares_outstanding

Do not estimate any additional model inputs beyond the fields listed above.

Revenue estimation guidance:
- Forecast revenue year by year from the latest actual revenue base.
- Keep near-term growth consistent with current momentum, but if the company is in a buildout or transition phase, allow stronger growth for longer before fading.
- As the revenue base gets larger, gradually reduce growth toward a believable mature-state level.
- Keep the path smooth, realistic, and internally consistent.
- For revenue forecasting, reason in terms of `revenue`, `growth_rates`, and a short reason, but in the final full payload return `inputs.revenue` and summarize the reasoning in `assumption_notes.revenue`. Do not add a separate `growth_rates` field.

Capex estimation guidance:
- Estimate how long the current buildout lasts.
- During the buildout, keep capex elevated.
- After the buildout ends, reduce capex by removing the temporary expansion component, but do not assume capex disappears or immediately returns to old historical levels.
- Keep enough capex for maintenance, replacement, and normal long-run growth.
- Summarize that logic briefly in `assumption_notes.capex` while returning the year-by-year values in `inputs.capex`.

Important modeling definitions:
- FCFE = EBIT * (1 - tax_rate) + Depreciation - Capex - Change in NWC + Net Borrowing
- net_borrowing must reflect debt issued minus debt repaid, not a plug.
- cost_of_equity is a scalar discount rate applied across the explicit forecast and terminal value.

Validation rules:
- Every forecast array must have exactly `projection_years` items.
- `cost_of_equity` must be greater than `terminal_growth`.
- Keep units consistent across the full payload.
- Terminal assumptions should be mature and not more aggressive than the late explicit forecast without a clear reason.
- Do not add extra keys inside `inputs`.

Return raw JSON only in this structure:
{{
  "company": "string",
  "ticker": "string",
  "currency": "string",
  "projection_years": 0,
  "projection_rationale": "string",
  "assumption_notes": {{
    "projection_years": "string",
    "revenue": "string",
    "ebit_margin": "string",
    "tax_rate": "string",
    "depreciation": "string",
    "capex": "string",
    "change_in_nwc": "string",
    "net_borrowing": "string",
    "cost_of_equity": "string",
    "terminal_growth": "string",
    "shares_outstanding": "string"
  }},
  "inputs": {{
    "revenue": [],
    "ebit_margin": [],
    "tax_rate": [],
    "depreciation": [],
    "capex": [],
    "change_in_nwc": [],
    "net_borrowing": [],
    "cost_of_equity": 0.0,
    "terminal_growth": 0.0,
    "shares_outstanding": 0.0
  }},
  "model_warnings": ["string"]
}}

Existing workflow clues:
- Additional analysis focus: {focus}
- Candidate facts:
{format_candidate_facts(candidate_facts)}

Target company:
{ticker}
""".strip()


def build_dcf_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	calculation_model: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for DCF parameter assembly."""

	chosen_path = (calculation_model or "FCFF").upper()
	if chosen_path == "FCFF":
		return _build_fcff_driver_prompt(
			ticker=ticker,
			candidate_facts=candidate_facts,
			analysis_focus=analysis_focus,
		)
	if chosen_path == "FCFE":
		return _build_fcfe_driver_prompt(
			ticker=ticker,
			candidate_facts=candidate_facts,
			analysis_focus=analysis_focus,
		)
	return f"""
You are the DCF parameter estimation specialist for AutoGraham.

The requested DCF calculation path is unsupported: {chosen_path}

Return raw JSON only:
{{
  "error": "unsupported_dcf_path",
  "calculation_model": "{chosen_path}"
}}
""".strip()
