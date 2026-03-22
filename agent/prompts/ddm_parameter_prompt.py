from __future__ import annotations

from typing import Any, Mapping

from agent.prompts._parameter_prompt_common import (
	build_base_parameter_prompt_intro,
	build_parameter_json_output_contract,
)


def build_ddm_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for DDM parameter assembly."""

	return f"""
{build_base_parameter_prompt_intro(ticker, "DDM", selected_variant, candidate_facts, analysis_focus)}

AutoGraham supports only these valuation models:
- DCF
- DDM
- RIM

For this workflow:
- DDM still uses stage-based variants.
- Driver-version parameter prompting is planned later, but DDM does not yet have a driver-version valuation path.

DDM guidance:
- DDM is suitable only when dividends are meaningful and reasonably predictable.
- Current dividend should reflect the annualized dividend base relevant to the model.
- Dividend growth assumptions should be conservative and tied to business maturity and payout sustainability.
- Cost of equity / required return should be reasonable and explainable.
- Terminal dividend growth should not be aggressive.

Required assumption keys by current AutoGraham workflow:
- DDM + "Single-Stage (Stable)": required_return, stable_growth
- DDM + "Two-Stage": required_return, high_growth, projection_years, terminal_growth
- DDM + "Three-Stage (Multi-stage decay)": required_return, high_growth, high_growth_years, transition_years, terminal_growth

{build_parameter_json_output_contract()}
""".strip()
