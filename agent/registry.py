from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from agent.subagents.research.macro_agent import run_macro_analysis
from agent.subagents.research.qualitative_agent import run_qualitative_analysis
from agent.subagents.research.quantitative_agent import run_quantitative_analysis
from agent.subagents.valuation.model_selector import select_model
from agent.subagents.valuation.parameter_planner import plan_parameters
from agent.subagents.writer import write_report


@dataclass(frozen=True)
class SubagentDefinition:
	"""Describe a callable subagent used by the orchestrator."""

	name: str
	handler: Callable[..., Any]
	description: str


_SUBAGENT_REGISTRY: dict[str, SubagentDefinition] = {
	"macro_agent": SubagentDefinition(
		name="macro_agent",
		handler=run_macro_analysis,
		description="Builds the macro and market-context read for the parallel analysis.",
	),
	"qualitative_agent": SubagentDefinition(
		name="qualitative_agent",
		handler=run_qualitative_analysis,
		description="Builds the business-quality and filing-driven read for the parallel analysis.",
	),
	"quantitative_agent": SubagentDefinition(
		name="quantitative_agent",
		handler=run_quantitative_analysis,
		description="Builds the quantitative company snapshot for the parallel analysis.",
	),
	"model_selector": SubagentDefinition(
		name="model_selector",
		handler=select_model,
		description="Chooses the valuation family and variant that best fits the business.",
	),
	"parameter_planner": SubagentDefinition(
		name="parameter_planner",
		handler=plan_parameters,
		description="Turns candidate facts into model-ready valuation parameters.",
	),
	"writer": SubagentDefinition(
		name="writer",
		handler=write_report,
		description="Writes the final investment explanation from workflow artifacts.",
	),
}


def get_subagent(name: str) -> SubagentDefinition:
	"""Return a registered subagent definition."""

	try:
		return _SUBAGENT_REGISTRY[name]
	except KeyError as exc:
		raise KeyError(f"Unknown subagent: {name}") from exc


__all__ = ["SubagentDefinition", "get_subagent"]
