from __future__ import annotations

from typing import Any, Callable

from agent.state import AgentGraphState, AgentRunState
from agent.supervisor import (
	estimate_parameters_node,
	extract_candidate_facts_node,
	research_sources,
	run_python_valuation_node,
	run_supervisor,
	select_model_and_variant,
	should_retry_parameter_estimation,
	supervisor_plan,
	validate_parameters_node,
	write_explanation_node,
)


GRAPH_STEPS = (
	"supervisor_plan",
	"research_sources",
	"extract_candidate_facts",
	"select_model_and_variant",
	"estimate_parameters",
	"validate_parameters",
	"run_python_valuation",
	"write_explanation",
)


def _wrap_node(node: Callable[[AgentRunState], AgentRunState]) -> Callable[[AgentGraphState], AgentGraphState]:
	"""Adapt a dataclass-based node for LangGraph's dictionary state interface."""

	def runner(payload: AgentGraphState) -> AgentGraphState:
		state = AgentRunState.from_graph_state(payload)
		return node(state).to_graph_state()

	return runner


class _FallbackCompiledGraph:
	"""Small runner that mimics `CompiledStateGraph.invoke` for local fallback use."""

	def invoke(self, payload: AgentGraphState | AgentRunState) -> AgentGraphState:
		state = AgentRunState.from_graph_state(payload)
		return run_supervisor(state).to_graph_state()


def build_agent_graph() -> Any:
	"""Build the LangGraph workflow when available, else return a sequential fallback.

	The intended path is:
	START -> supervisor_plan -> research_sources -> extract_candidate_facts
	-> select_model_and_variant -> estimate_parameters -> validate_parameters
	-> (estimate_parameters | run_python_valuation | write_explanation)
	-> write_explanation -> END
	"""

	try:
		from langgraph.graph import END, START, StateGraph
	except ImportError:
		return _FallbackCompiledGraph()

	graph = StateGraph(AgentGraphState)
	graph.add_node("supervisor_plan", _wrap_node(supervisor_plan))
	graph.add_node("research_sources", _wrap_node(research_sources))
	graph.add_node("extract_candidate_facts", _wrap_node(extract_candidate_facts_node))
	graph.add_node("select_model_and_variant", _wrap_node(select_model_and_variant))
	graph.add_node("estimate_parameters", _wrap_node(estimate_parameters_node))
	graph.add_node("validate_parameters", _wrap_node(validate_parameters_node))
	graph.add_node("run_python_valuation", _wrap_node(run_python_valuation_node))
	graph.add_node("write_explanation", _wrap_node(write_explanation_node))

	graph.add_edge(START, "supervisor_plan")
	graph.add_edge("supervisor_plan", "research_sources")
	graph.add_edge("research_sources", "extract_candidate_facts")
	graph.add_edge("extract_candidate_facts", "select_model_and_variant")
	graph.add_edge("select_model_and_variant", "estimate_parameters")
	graph.add_edge("estimate_parameters", "validate_parameters")
	graph.add_conditional_edges(
		"validate_parameters",
		lambda payload: should_retry_parameter_estimation(AgentRunState.from_graph_state(payload)),
		{
			"estimate_parameters": "estimate_parameters",
			"run_python_valuation": "run_python_valuation",
			"write_explanation": "write_explanation",
		},
	)
	graph.add_edge("run_python_valuation", "write_explanation")
	graph.add_edge("write_explanation", END)
	return graph.compile()


def run_agent_graph(state: AgentRunState) -> AgentRunState:
	"""Run the supervisor-led workflow through LangGraph or the local fallback."""

	graph = build_agent_graph()
	result = graph.invoke(state.to_graph_state())
	return AgentRunState.from_graph_state(result)
