from __future__ import annotations

from typing import Any, Callable

from agent.registry import get_subagent
from agent.state import AgentGraphState, AgentRunState, WorkflowStep
from agent.subagents.context_builder import extract_candidate_facts
from agent.tools.calculator_tools import run_valuation_calculation
from agent.tools.validation_tools import validate_parameter_payload
from data.cache import stock_data_cache_scope


build_company_context = get_subagent("context_builder").handler
select_model = get_subagent("model_selector").handler
plan_parameters = get_subagent("parameter_planner").handler
write_report = get_subagent("writer").handler


GRAPH_STEPS = (
	"supervisor_plan",
	"build_company_context",
	"extract_candidate_facts",
	"select_model_and_variant",
	"plan_parameters",
	"validate_parameters",
	"run_python_valuation",
	"write_report",
)


def _wrap_node(node: Callable[[AgentRunState], AgentRunState]) -> Callable[[AgentGraphState], AgentGraphState]:
	"""Adapt a dataclass-based node for LangGraph's dictionary state interface."""

	def runner(payload: AgentGraphState) -> AgentGraphState:
		state = AgentRunState.from_graph_state(payload)
		return node(state).to_graph_state()

	return runner


def _record_error(state: AgentRunState, step_name: WorkflowStep, error: Exception | str) -> AgentRunState:
	message = f"{step_name}: {error}"
	state.errors.append(message)
	state.mark_error_step(step_name)
	state.next_step = None
	return state


def supervisor_plan(state: AgentRunState) -> AgentRunState:
	"""Set the initial plan and normalize the run context."""

	from agent.llm_utils import default_model_name

	state.model_name = state.model_name or default_model_name()
	stock_info = getattr(state.stock_data, "info", state.stock_data) or {}
	company_name = stock_info.get("longName") or stock_info.get("shortName") or state.ticker
	state.company_name = str(company_name)
	state.supervisor_plan = (
		"Build a lightweight company context case file first, extract valuation-relevant facts, choose the valuation family, "
		"assemble model-ready assumptions, validate inputs, run deterministic Python math, then explain the result."
	)
	state.next_step = "build_company_context"
	return state


def build_company_context_node(state: AgentRunState) -> AgentRunState:
	"""Build the lightweight pre-selection company context case file."""

	try:
		research = build_company_context(
			state.ticker,
			state.stock_data,
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		return _record_error(state, "build_company_context", exc)

	state.research_report = str(research.get("report_markdown") or "")
	state.source_links = list(research.get("source_links") or [])
	state.source_notes = list(research.get("source_notes") or [])
	state.confidence = research.get("confidence", state.confidence)
	state.metadata["research_summary"] = research.get("summary") or ""
	state.next_step = "extract_candidate_facts"
	return state


def extract_candidate_facts_node(state: AgentRunState) -> AgentRunState:
	"""Convert messy research into source-aware candidate facts."""

	try:
		state.candidate_facts = extract_candidate_facts(
			state.ticker,
			state.stock_data,
			state.research_report,
			state.source_notes,
			model_name=state.model_name,
		)
	except Exception as exc:
		return _record_error(state, "extract_candidate_facts", exc)

	state.next_step = "select_model_and_variant"
	return state


def select_model_and_variant(state: AgentRunState) -> AgentRunState:
	"""Choose DCF, DDM, or RIM plus the appropriate model variant."""

	try:
		recommendation = select_model(
			state.ticker,
			state.stock_data,
			state.candidate_facts,
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		return _record_error(state, "select_model_and_variant", exc)

	state.selected_model = recommendation.get("selected_model")
	state.selected_variant = recommendation.get("selected_variant")
	state.confidence = recommendation.get("confidence", state.confidence)
	state.set_model_selection(recommendation)
	state.next_step = "plan_parameters"
	return state


def plan_parameters_node(state: AgentRunState) -> AgentRunState:
	"""Assemble a model-ready parameter payload from candidate facts."""

	try:
		state.parameter_payload = plan_parameters(
			state.ticker,
			state.stock_data,
			state.candidate_facts,
			{
				"selected_model": state.selected_model,
				"selected_variant": state.selected_variant,
				**state.model_selection,
			},
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		return _record_error(state, "plan_parameters", exc)

	state.validation_attempts += 1
	state.next_step = "validate_parameters"
	return state


def validate_parameters_node(state: AgentRunState) -> AgentRunState:
	"""Validate at the model-input boundary instead of over-constraining upstream research."""

	validation = validate_parameter_payload(state.parameter_payload)
	state.validation_status = "valid" if validation["is_valid"] else "invalid"
	state.validation_errors = list(validation.get("errors") or [])
	state.set_validation_artifacts(validation)
	state.next_step = should_retry_parameter_planning(state)
	return state


def should_retry_parameter_planning(state: AgentRunState) -> WorkflowStep:
	"""Choose the next workflow hop after parameter validation."""

	if state.validation_status == "valid":
		return "run_python_valuation"
	if state.validation_attempts <= state.max_validation_attempts:
		return "plan_parameters"
	return "write_report"


def run_python_valuation_node(state: AgentRunState) -> AgentRunState:
	"""Call deterministic Python valuation logic outside the agent package."""

	try:
		state.valuation_result = run_valuation_calculation(state.parameter_payload)
	except Exception as exc:
		return _record_error(state, "run_python_valuation", exc)

	state.confidence = state.valuation_result.get("confidence", state.confidence)
	state.next_step = "write_report"
	return state


def write_report_node(state: AgentRunState) -> AgentRunState:
	"""Write the user-facing explanation from the validated workflow artifacts."""

	try:
		state.explanation = write_report(
			ticker=state.ticker,
			company_name=state.company_name,
			research_report=state.research_report,
			source_links=state.source_links,
			source_notes=state.source_notes,
			candidate_facts=state.candidate_facts,
			model_selection=state.model_selection,
			parameter_payload=state.parameter_payload,
			valuation_result=state.valuation_result,
			confidence=state.confidence,
			model_name=state.model_name,
		)
	except Exception as exc:
		return _record_error(state, "write_report", exc)

	state.next_step = None
	return state


class _FallbackCompiledGraph:
	"""Small runner that mimics `CompiledStateGraph.invoke` for local fallback use."""

	def invoke(self, payload: AgentGraphState | AgentRunState) -> AgentGraphState:
		state = AgentRunState.from_graph_state(payload)
		return run_orchestration(state).to_graph_state()


def build_agent_graph() -> Any:
	"""Build the LangGraph workflow when available, else return a sequential fallback."""

	try:
		from langgraph.graph import END, START, StateGraph
	except ImportError:
		return _FallbackCompiledGraph()

	graph = StateGraph(AgentGraphState)
	graph.add_node("supervisor_plan", _wrap_node(supervisor_plan))
	graph.add_node("build_company_context", _wrap_node(build_company_context_node))
	graph.add_node("extract_candidate_facts", _wrap_node(extract_candidate_facts_node))
	graph.add_node("select_model_and_variant", _wrap_node(select_model_and_variant))
	graph.add_node("plan_parameters", _wrap_node(plan_parameters_node))
	graph.add_node("validate_parameters", _wrap_node(validate_parameters_node))
	graph.add_node("run_python_valuation", _wrap_node(run_python_valuation_node))
	graph.add_node("write_report", _wrap_node(write_report_node))

	graph.add_edge(START, "supervisor_plan")
	graph.add_edge("supervisor_plan", "build_company_context")
	graph.add_edge("build_company_context", "extract_candidate_facts")
	graph.add_edge("extract_candidate_facts", "select_model_and_variant")
	graph.add_edge("select_model_and_variant", "plan_parameters")
	graph.add_edge("plan_parameters", "validate_parameters")
	graph.add_conditional_edges(
		"validate_parameters",
		lambda payload: should_retry_parameter_planning(AgentRunState.from_graph_state(payload)),
		{
			"plan_parameters": "plan_parameters",
			"run_python_valuation": "run_python_valuation",
			"write_report": "write_report",
		},
	)
	graph.add_edge("run_python_valuation", "write_report")
	graph.add_edge("write_report", END)
	return graph.compile()


def run_agent_graph(state: AgentRunState) -> AgentRunState:
	"""Run the orchestrated workflow through LangGraph or the local fallback."""

	with stock_data_cache_scope():
		graph = build_agent_graph()
		result = graph.invoke(state.to_graph_state())
		return AgentRunState.from_graph_state(result)


def run_orchestration(state: AgentRunState) -> AgentRunState:
	"""Sequential fallback runner used when LangGraph is unavailable."""

	with stock_data_cache_scope():
		state = supervisor_plan(state)
		state = build_company_context_node(state)
		state = extract_candidate_facts_node(state)
		state = select_model_and_variant(state)
		while True:
			state = plan_parameters_node(state)
			state = validate_parameters_node(state)
			decision = should_retry_parameter_planning(state)
			if decision != "plan_parameters":
				break
		if state.validation_status == "valid":
			state = run_python_valuation_node(state)
		state = write_report_node(state)
		return state


__all__ = [
	"GRAPH_STEPS",
	"build_agent_graph",
	"build_company_context",
	"build_company_context_node",
	"extract_candidate_facts",
	"extract_candidate_facts_node",
	"plan_parameters",
	"plan_parameters_node",
	"run_agent_graph",
	"run_orchestration",
	"run_python_valuation_node",
	"select_model",
	"select_model_and_variant",
	"should_retry_parameter_planning",
	"supervisor_plan",
	"validate_parameter_payload",
	"validate_parameters_node",
	"write_report",
	"write_report_node",
]
