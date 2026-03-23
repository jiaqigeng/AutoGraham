from __future__ import annotations

from typing import Any, Mapping

from agent.prompts._parameter_prompt_common import (
	build_base_parameter_prompt_intro,
	build_parameter_json_output_contract,
	format_candidate_facts,
)


def _build_ddm_driver_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None,
) -> str:
	focus = analysis_focus or "Use conservative assumptions when the evidence is incomplete."
	return f"""
You are the DDM parameter estimation specialist for AutoGraham.

Your task is to build the full input payload for the Python function
`calculate_ddm_from_drivers(...)` in `ddm.py`.

Model selection has already been completed.
Do NOT evaluate whether DDM is appropriate.
Do NOT include model-suitability discussion.
Focus only on producing a coherent year-by-year dividend forecast.

Important working style:
- Try to look for relevant info and consensus through public and free online sources, but do not get stuck on hunting for sources or listing sources.
- Use the workflow clues below as context, then apply financial judgment.
- If evidence is incomplete, still make a conservative estimate instead of refusing.
- Keep the forecast internally consistent and economically plausible.
- Estimate only `projection_years` and the exact inputs required by the Python function. Do not introduce extra assumption fields.

What you must estimate:
1. Choose `projection_years`.
   Use a longer horizon when earnings normalization, payout policy, or capital allocation are still changing. Use a shorter horizon when the business and payout policy already look mature and stable.
2. For every year in `projection_years`, estimate:
   - earnings_per_share
   - payout_ratio
3. Estimate scalar discount-rate, terminal, and equity inputs:
   - required_return
   - terminal_growth
   - shares_outstanding

Do not estimate any additional model inputs beyond the fields listed above.

DDM driver guidance:
- The model converts dividends as `dividend_per_share = earnings_per_share * payout_ratio`.
- `payout_ratio` must stay between 0% and 100%.
- Earnings should fade toward a believable mature-state path over time rather than staying permanently elevated without explanation.
- Payout policy should reflect business maturity, reinvestment needs, and management capital-return posture.
- `required_return` must be greater than `terminal_growth`.

Validation rules:
- `earnings_per_share` and `payout_ratio` must each have exactly `projection_years` items.
- `required_return` must be greater than `terminal_growth`.
- Keep units consistent across the full payload.
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
    "earnings_per_share": "string",
    "payout_ratio": "string",
    "required_return": "string",
    "terminal_growth": "string",
    "shares_outstanding": "string"
  }},
  "inputs": {{
    "earnings_per_share": [],
    "payout_ratio": [],
    "required_return": 0.0,
    "terminal_growth": 0.0,
    "shares_outstanding": 0.0
  }},
  "model_warnings": ["string"]
}}

Existing workflow clues:
- Chosen variant: {selected_variant or "None"}
- Additional analysis focus: {focus}
- Candidate facts:
{format_candidate_facts(candidate_facts)}

Target company:
{ticker}
""".strip()


def build_ddm_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for DDM parameter assembly."""

	if selected_variant == "Drivers":
		return _build_ddm_driver_prompt(
			ticker=ticker,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			analysis_focus=analysis_focus,
		)

	return f"""
{build_base_parameter_prompt_intro(ticker, "DDM", selected_variant, candidate_facts, analysis_focus)}

AutoGraham supports only these valuation models:
- DCF
- DDM
- RIM

For this workflow:
- DDM supports both stage-based variants and the driver-based `Drivers` path.
- This prompt is for the stage-based DDM variants, not the driver-based path.

DDM guidance:
- DDM is suitable only when dividends are meaningful and reasonably predictable.
- Current dividend should reflect the annualized dividend base relevant to the model.
- Dividend growth assumptions should be conservative and tied to business maturity and payout sustainability.
- Cost of equity / required return should be reasonable and explainable.
- Terminal dividend growth should not be aggressive.

Required assumption keys by current AutoGraham workflow:
- DDM + "Drivers": earnings_per_share, payout_ratio, required_return, terminal_growth, shares_outstanding
- DDM + "Single-Stage (Stable)": required_return, stable_growth
- DDM + "Two-Stage": required_return, high_growth, projection_years, terminal_growth
- DDM + "Three-Stage (Multi-stage decay)": required_return, high_growth, high_growth_years, transition_years, terminal_growth

{build_parameter_json_output_contract()}
""".strip()
