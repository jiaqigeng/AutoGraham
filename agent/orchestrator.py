from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from agent.registry import get_subagent
from agent.state import AgentGraphState, AgentRunState, WorkflowStep
from agent.subagents.research.common import merge_candidate_facts
from agent.tools.calculator_tools import run_valuation_calculation
from agent.tools.validation_tools import validate_parameter_payload
from data.cache import stock_data_cache_scope


run_macro_analysis = get_subagent("macro_agent").handler
run_qualitative_analysis = get_subagent("qualitative_agent").handler
run_quantitative_analysis = get_subagent("quantitative_agent").handler
select_model = get_subagent("model_selector").handler
plan_parameters = get_subagent("parameter_planner").handler
write_report = get_subagent("writer").handler


GRAPH_STEPS = (
	"supervisor_plan",
	"parallel_analysis_start",
	"run_macro_analysis",
	"run_qualitative_analysis",
	"run_quantitative_analysis",
	"merge_parallel_analysis",
	"select_model_and_variant",
	"plan_parameters",
	"validate_parameters",
	"run_python_valuation",
	"write_report",
)


def _wrap_node(node: Callable[[AgentRunState], AgentRunState]) -> Callable[[AgentGraphState], AgentGraphState]:
	"""Adapt a dataclass node and emit only changed state keys for graph merging."""

	def runner(payload: AgentGraphState) -> AgentGraphState:
		state = AgentRunState.from_graph_state(payload)
		before = state.to_graph_state()
		after = node(state).to_graph_state()
		return {key: value for key, value in after.items() if before.get(key) != value}

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
		"Run the Macro, Qualitative, and Quantitative agents in parallel, merge the parallel-analysis research packet, choose the valuation family, "
		"assemble model-ready assumptions, validate inputs, run deterministic Python math, then synthesize the result."
	)
	state.next_step = "parallel_analysis_start"
	return state


def parallel_analysis_start_node(state: AgentRunState) -> AgentRunState:
	"""Reset the parallel-analysis slots before the three-agent fan-out."""

	state.macro_analysis = {}
	state.qualitative_analysis = {}
	state.quantitative_analysis = {}
	state.research_report = ""
	state.source_links = []
	state.source_notes = []
	state.candidate_facts = []
	state.next_step = None
	return state


def _parallel_analysis_error_artifact(agent_name: str, error: Exception | str) -> dict[str, Any]:
	return {
		"analysis_agent": agent_name,
		"summary": "",
		"report_markdown": "",
		"source_links": [],
		"source_notes": [],
		"candidate_facts": [],
		"confidence": 0.0,
		"error": str(error),
	}


def run_macro_analysis_node(state: AgentRunState) -> AgentRunState:
	"""Execute the macro branch of the parallel analysis."""

	try:
		state.macro_analysis = run_macro_analysis(
			state.ticker,
			state.stock_data,
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		state.macro_analysis = _parallel_analysis_error_artifact("macro", exc)
	return state


def run_qualitative_analysis_node(state: AgentRunState) -> AgentRunState:
	"""Execute the qualitative branch of the parallel analysis."""

	try:
		state.qualitative_analysis = run_qualitative_analysis(
			state.ticker,
			state.stock_data,
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		state.qualitative_analysis = _parallel_analysis_error_artifact("qualitative", exc)
	return state


def run_quantitative_analysis_node(state: AgentRunState) -> AgentRunState:
	"""Execute the quantitative branch of the parallel analysis."""

	try:
		state.quantitative_analysis = run_quantitative_analysis(
			state.ticker,
			state.stock_data,
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		state.quantitative_analysis = _parallel_analysis_error_artifact("quantitative", exc)
	return state


def _dedupe_source_notes(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
	seen: set[tuple[str, str, str, str]] = set()
	deduped: list[dict[str, Any]] = []
	for note in notes:
		key = (
			str(note.get("analysis_agent") or "").strip(),
			str(note.get("title") or "").strip(),
			str(note.get("url") or "").strip(),
			str(note.get("snippet") or "").strip(),
		)
		if key in seen:
			continue
		seen.add(key)
		deduped.append(note)
	return deduped


def _build_parallel_analysis_report_section(title: str, artifact: dict[str, Any]) -> str:
	body = str(artifact.get("report_markdown") or "").strip()
	error = str(artifact.get("error") or "").strip()
	if not body and error:
		body = f"- This branch did not complete successfully: {error}"
	if not body:
		body = "- No research output was generated for this branch."
	return f"## {title}\n\n{body}"


def merge_parallel_analysis_node(state: AgentRunState) -> AgentRunState:
	"""Join the parallel analysis outputs into one downstream research packet."""

	artifacts = [
		dict(state.macro_analysis or {}),
		dict(state.qualitative_analysis or {}),
		dict(state.quantitative_analysis or {}),
	]
	for artifact in artifacts:
		error = str(artifact.get("error") or "").strip()
		agent_name = str(artifact.get("analysis_agent") or "parallel_analysis")
		if error:
			state.errors.append(f"{agent_name}: {error}")

	state.research_report = "\n\n".join(
		[
			_build_parallel_analysis_report_section("Macro Analysis", artifacts[0]),
			_build_parallel_analysis_report_section("Qualitative Analysis", artifacts[1]),
			_build_parallel_analysis_report_section("Quantitative Analysis", artifacts[2]),
		]
	).strip()
	state.source_links = list(
		dict.fromkeys(
			link.strip()
			for artifact in artifacts
			for link in list(artifact.get("source_links") or [])
			if isinstance(link, str) and link.strip()
		)
	)
	state.source_notes = _dedupe_source_notes(
		[
			dict(note)
			for artifact in artifacts
			for note in list(artifact.get("source_notes") or [])
			if isinstance(note, dict)
		]
	)
	state.candidate_facts = merge_candidate_facts(
		*[list(artifact.get("candidate_facts") or []) for artifact in artifacts]
	)
	confidence_values = [
		float(value)
		for value in (artifact.get("confidence") for artifact in artifacts)
		if isinstance(value, (int, float)) and float(value) > 0
	]
	if confidence_values:
		state.confidence = sum(confidence_values) / len(confidence_values)
	state.metadata["research_summary"] = " | ".join(
		str(artifact.get("summary") or "").strip()
		for artifact in artifacts
		if str(artifact.get("summary") or "").strip()
	)
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
	graph.add_node("parallel_analysis_start", _wrap_node(parallel_analysis_start_node))
	graph.add_node("run_macro_analysis", _wrap_node(run_macro_analysis_node))
	graph.add_node("run_qualitative_analysis", _wrap_node(run_qualitative_analysis_node))
	graph.add_node("run_quantitative_analysis", _wrap_node(run_quantitative_analysis_node))
	graph.add_node("merge_parallel_analysis", _wrap_node(merge_parallel_analysis_node))
	graph.add_node("select_model_and_variant", _wrap_node(select_model_and_variant))
	graph.add_node("plan_parameters", _wrap_node(plan_parameters_node))
	graph.add_node("validate_parameters", _wrap_node(validate_parameters_node))
	graph.add_node("run_python_valuation", _wrap_node(run_python_valuation_node))
	graph.add_node("write_report", _wrap_node(write_report_node))

	graph.add_edge(START, "supervisor_plan")
	graph.add_edge("supervisor_plan", "parallel_analysis_start")
	graph.add_edge("parallel_analysis_start", "run_macro_analysis")
	graph.add_edge("parallel_analysis_start", "run_qualitative_analysis")
	graph.add_edge("parallel_analysis_start", "run_quantitative_analysis")
	graph.add_edge("run_macro_analysis", "merge_parallel_analysis")
	graph.add_edge("run_qualitative_analysis", "merge_parallel_analysis")
	graph.add_edge("run_quantitative_analysis", "merge_parallel_analysis")
	graph.add_edge("merge_parallel_analysis", "select_model_and_variant")
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
		state = parallel_analysis_start_node(state)
		parallel_analysis_nodes = (
			("macro_analysis", run_macro_analysis_node),
			("qualitative_analysis", run_qualitative_analysis_node),
			("quantitative_analysis", run_quantitative_analysis_node),
		)
		with ThreadPoolExecutor(max_workers=3) as executor:
			futures = {
				executor.submit(node, AgentRunState.from_graph_state(state.to_graph_state())): field_name
				for field_name, node in parallel_analysis_nodes
			}
			for future, field_name in ((future, futures[future]) for future in futures):
				try:
					branch_state = future.result()
					setattr(state, field_name, dict(getattr(branch_state, field_name) or {}))
				except Exception as exc:
					setattr(state, field_name, _parallel_analysis_error_artifact(field_name.replace("_analysis", ""), exc))
		state = merge_parallel_analysis_node(state)
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
	"merge_parallel_analysis_node",
	"plan_parameters",
	"plan_parameters_node",
	"parallel_analysis_start_node",
	"run_macro_analysis",
	"run_macro_analysis_node",
	"run_agent_graph",
	"run_orchestration",
	"run_qualitative_analysis",
	"run_qualitative_analysis_node",
	"run_quantitative_analysis",
	"run_quantitative_analysis_node",
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
