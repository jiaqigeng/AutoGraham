from __future__ import annotations

from typing import Any, Mapping

from agent.prompts.dcf_parameter_prompt import build_dcf_parameter_prompt
from agent.prompts.ddm_parameter_prompt import build_ddm_parameter_prompt
from agent.prompts.rim_parameter_prompt import build_rim_parameter_prompt


def build_parameter_prompt(
	ticker: str,
	selected_model: str,
	selected_variant: str | None,
	candidate_facts: list[Mapping[str, Any]],
	calculation_model: str | None = None,
	analysis_focus: str | None = None,
) -> str:
	"""Dispatch to the model-specific parameter prompt builder."""

	model_code = selected_model.upper()
	if model_code == "DCF":
		return build_dcf_parameter_prompt(
			ticker=ticker,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			calculation_model=calculation_model,
			analysis_focus=analysis_focus,
		)
	if model_code == "DDM":
		return build_ddm_parameter_prompt(
			ticker=ticker,
			selected_variant=selected_variant,
			candidate_facts=candidate_facts,
			analysis_focus=analysis_focus,
		)
	return build_rim_parameter_prompt(
		ticker=ticker,
		selected_variant=selected_variant,
		candidate_facts=candidate_facts,
		analysis_focus=analysis_focus,
	)
