from __future__ import annotations

from typing import Any

from agent.deep_agent import default_model_name
from agent.state import AgentRunState
from agent.subagents import (
	estimate_parameters,
	explain_valuation,
	extract_candidate_facts,
	research_company,
	select_model,
)
from agent.tools.calculator_tools import run_valuation_calculation
from agent.tools.validation_tools import validate_parameter_payload


def _record_error(state: AgentRunState, step_name: str, error: Exception | str) -> AgentRunState:
	message = f"{step_name}: {error}"
	state.errors.append(message)
	state.metadata["last_error_step"] = step_name
	state.next_step = None
	return state


def supervisor_plan(state: AgentRunState) -> AgentRunState:
	"""Set the initial plan and normalize the run context."""

	state.model_name = state.model_name or default_model_name()
	stock_info = getattr(state.stock_data, "info", state.stock_data) or {}
	company_name = stock_info.get("longName") or stock_info.get("shortName") or state.ticker
	state.company_name = str(company_name)
	state.supervisor_plan = (
		"Research broadly first, extract valuation-relevant facts, choose the valuation family, "
		"assemble model-ready assumptions, validate inputs, run deterministic Python math, then explain the result."
	)
	state.next_step = "research_sources"
	return state


def research_sources(state: AgentRunState) -> AgentRunState:
	"""Run the broad research pass before narrowing to model-ready parameters."""

	try:
		research = research_company(
			state.ticker,
			state.stock_data,
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		return _record_error(state, "research_sources", exc)

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
	state.metadata["model_selection"] = recommendation
	state.next_step = "estimate_parameters"
	return state


def estimate_parameters_node(state: AgentRunState) -> AgentRunState:
	"""Assemble a model-ready parameter payload from candidate facts."""

	try:
		state.parameter_payload = estimate_parameters(
			state.ticker,
			state.stock_data,
			state.candidate_facts,
			{
				"selected_model": state.selected_model,
				"selected_variant": state.selected_variant,
				**dict(state.metadata.get("model_selection") or {}),
			},
			model_name=state.model_name,
			analysis_focus=state.analysis_focus,
		)
	except Exception as exc:
		return _record_error(state, "estimate_parameters", exc)

	state.validation_attempts += 1
	state.next_step = "validate_parameters"
	return state


def validate_parameters_node(state: AgentRunState) -> AgentRunState:
	"""Validate at the model-input boundary instead of over-constraining upstream research."""

	validation = validate_parameter_payload(state.parameter_payload)
	state.validation_status = "valid" if validation["is_valid"] else "invalid"
	state.validation_errors = list(validation.get("errors") or [])
	state.metadata["validated_payload"] = validation.get("normalized_payload") or {}
	state.metadata["boundary_inputs"] = validation.get("normalized_inputs") or {}
	state.metadata["valuation_model_code"] = validation.get("valuation_model_code")
	state.metadata["growth_stage"] = validation.get("growth_stage")
	state.next_step = should_retry_parameter_estimation(state)
	return state


def should_retry_parameter_estimation(state: AgentRunState) -> str:
	"""Choose the next workflow hop after parameter validation."""

	if state.validation_status == "valid":
		return "run_python_valuation"
	if state.validation_attempts <= state.max_validation_attempts:
		return "estimate_parameters"
	return "write_explanation"


def run_python_valuation_node(state: AgentRunState) -> AgentRunState:
	"""Call deterministic Python valuation logic outside the agent package."""

	try:
		state.valuation_result = run_valuation_calculation(state.parameter_payload)
	except Exception as exc:
		return _record_error(state, "run_python_valuation", exc)

	state.confidence = state.valuation_result.get("confidence", state.confidence)
	state.next_step = "write_explanation"
	return state


def write_explanation_node(state: AgentRunState) -> AgentRunState:
	"""Write the user-facing explanation from the validated workflow artifacts."""

	try:
		state.explanation = explain_valuation(
			ticker=state.ticker,
			company_name=state.company_name,
			research_report=state.research_report,
			source_links=state.source_links,
			source_notes=state.source_notes,
			candidate_facts=state.candidate_facts,
			model_selection=dict(state.metadata.get("model_selection") or {}),
			parameter_payload=state.parameter_payload,
			valuation_result=state.valuation_result,
			confidence=state.confidence,
			model_name=state.model_name,
		)
	except Exception as exc:
		return _record_error(state, "write_explanation", exc)

	state.next_step = None
	return state


def run_supervisor(state: AgentRunState) -> AgentRunState:
	"""Sequential fallback runner used when LangGraph is unavailable."""

	state = supervisor_plan(state)
	state = research_sources(state)
	state = extract_candidate_facts_node(state)
	state = select_model_and_variant(state)
	while True:
		state = estimate_parameters_node(state)
		state = validate_parameters_node(state)
		decision = should_retry_parameter_estimation(state)
		if decision != "estimate_parameters":
			break
	if state.validation_status == "valid":
		state = run_python_valuation_node(state)
	state = write_explanation_node(state)
	return state
