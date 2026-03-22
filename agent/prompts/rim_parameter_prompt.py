from __future__ import annotations

from typing import Any, Mapping

from agent.prompts._parameter_prompt_common import (
	build_base_parameter_prompt_intro,
	build_parameter_json_output_contract,
)


def build_rim_parameter_prompt(
	ticker: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	analysis_focus: str | None = None,
) -> str:
	"""Prompt for RIM parameter assembly."""

	return f"""
{build_base_parameter_prompt_intro(ticker, "RIM", selected_variant, candidate_facts, analysis_focus)}

AutoGraham supports only these valuation models:
- DCF
- DDM
- RIM

For this workflow:
- RIM may use a null variant because the deterministic Python path uses a single residual-income implementation.
- Driver-version parameter prompting is planned later, but RIM does not yet have a driver-version valuation path.

RIM guidance:
- RIM is often suitable for banks, insurers, and financial firms where book value and returns matter.
- Book value per share should usually come from the latest reported value.
- Tangible book value may be relevant context, but only use it as the main input if the workflow explicitly calls for that.
- Payout ratio should reflect a reasonable definition of retained earnings behavior for the model.
- ROE assumptions should be grounded in recent returns, management targets, normalization logic, and business context.
- Terminal ROE thinking may inform your judgment, but the current deterministic AutoGraham RIM path expects a single return_on_equity plus payout_ratio, projection_years, cost_of_equity, and terminal_growth.
- Terminal growth must be less than cost_of_equity.

Required assumption keys by current AutoGraham workflow:
- RIM: return_on_equity, cost_of_equity, payout_ratio, projection_years, terminal_growth

{build_parameter_json_output_contract()}
""".strip()
