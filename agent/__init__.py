from __future__ import annotations

from importlib import import_module
from typing import Any


def __getattr__(name: str) -> Any:
	if name == "run_agent_graph":
		orchestrator = import_module("agent.orchestrator")
		return orchestrator.run_agent_graph
	if name == "AgentRunState":
		return import_module("agent.state").AgentRunState
	raise AttributeError(f"module 'agent' has no attribute {name!r}")

__all__ = [
	"AgentRunState",
	"run_agent_graph",
]
