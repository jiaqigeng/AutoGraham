from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from agent.subagents.context_builder import build_company_context
from agent.subagents.model_selector import select_model
from agent.subagents.parameter_planner import plan_parameters
from agent.subagents.writer import write_report


@dataclass(frozen=True)
class SubagentDefinition:
	"""Describe a callable subagent used by the orchestrator."""

	name: str
	handler: Callable[..., Any]
	description: str


_SUBAGENT_REGISTRY: dict[str, SubagentDefinition] = {
	"context_builder": SubagentDefinition(
		name="context_builder",
		handler=build_company_context,
		description="Builds the lightweight company case file before model selection.",
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
