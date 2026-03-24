from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypedDict, cast


WorkflowStep = Literal[
	"supervisor_plan",
	"build_company_context",
	"extract_candidate_facts",
	"select_model_and_variant",
	"plan_parameters",
	"validate_parameters",
	"run_python_valuation",
	"write_report",
]
ValidationStatus = Literal["not_run", "valid", "invalid"]
ValuationModelCode = Literal["FCFF", "FCFE", "DDM", "RIM"]


class AgentMetadata(TypedDict, total=False):
	"""Known metadata items that flow between orchestration steps."""

	last_error_step: WorkflowStep
	research_summary: str
	model_selection: dict[str, Any]
	validated_payload: dict[str, Any]
	boundary_inputs: dict[str, Any]
	valuation_model_code: ValuationModelCode | None
	growth_stage: str | None


class AgentGraphState(TypedDict, total=False):
	"""Dictionary state shape used by LangGraph-style orchestration."""

	ticker: str
	company_name: str
	model_name: str | None
	analysis_focus: str | None
	stock_data: Any | None
	source_links: list[str]
	source_notes: list[dict[str, Any]]
	candidate_facts: list[dict[str, Any]]
	selected_model: str | None
	selected_variant: str | None
	parameter_payload: dict[str, Any]
	valuation_result: dict[str, Any]
	explanation: str
	confidence: float | None
	errors: list[str]
	research_report: str
	supervisor_plan: str
	validation_status: ValidationStatus
	validation_errors: list[str]
	validation_attempts: int
	max_validation_attempts: int
	next_step: WorkflowStep | None
	metadata: AgentMetadata


def _normalize_validation_status(value: Any) -> ValidationStatus:
	"""Clamp arbitrary values into the supported validation states."""

	text = str(value or "not_run").strip().lower()
	if text == "valid":
		return "valid"
	if text == "invalid":
		return "invalid"
	return "not_run"


def _normalize_next_step(value: Any) -> WorkflowStep | None:
	"""Clamp arbitrary values into the supported workflow hops."""

	text = str(value or "").strip()
	if text in {
		"supervisor_plan",
		"build_company_context",
		"extract_candidate_facts",
		"select_model_and_variant",
		"plan_parameters",
		"validate_parameters",
		"run_python_valuation",
		"write_report",
	}:
		return cast(WorkflowStep, text)
	return None


def _normalize_model_code(value: Any) -> ValuationModelCode | None:
	"""Clamp arbitrary values into the supported deterministic model codes."""

	text = str(value or "").strip().upper()
	if text in {"FCFF", "FCFE", "DDM", "RIM"}:
		return cast(ValuationModelCode, text)
	return None


@dataclass
class AgentRunState:
	"""Short-term workflow state for one AI valuation run.

	This object is intentionally ephemeral. It tracks what one AI workflow gathered,
	decided, validated, and produced during a single user-triggered run.
	"""

	ticker: str
	company_name: str = ""
	model_name: str | None = None
	analysis_focus: str | None = None
	stock_data: Any | None = None
	source_links: list[str] = field(default_factory=list)
	source_notes: list[dict[str, Any]] = field(default_factory=list)
	candidate_facts: list[dict[str, Any]] = field(default_factory=list)
	selected_model: str | None = None
	selected_variant: str | None = None
	parameter_payload: dict[str, Any] = field(default_factory=dict)
	valuation_result: dict[str, Any] = field(default_factory=dict)
	explanation: str = ""
	confidence: float | None = None
	errors: list[str] = field(default_factory=list)
	research_report: str = ""
	supervisor_plan: str = ""
	validation_status: ValidationStatus = "not_run"
	validation_errors: list[str] = field(default_factory=list)
	validation_attempts: int = 0
	max_validation_attempts: int = 2
	next_step: WorkflowStep | None = None
	metadata: AgentMetadata = field(default_factory=dict)

	@property
	def fetched_facts(self) -> list[dict[str, Any]]:
		"""Compatibility alias for earlier workflow code."""

		return self.candidate_facts

	@property
	def assumptions(self) -> dict[str, Any]:
		"""Return the estimated assumptions block from the parameter payload."""

		return dict(self.parameter_payload.get("assumptions") or {})

	@property
	def model_selection(self) -> dict[str, Any]:
		"""Return the selected valuation family details recorded by the orchestrator."""

		return dict(self.metadata.get("model_selection") or {})

	@property
	def validated_payload(self) -> dict[str, Any]:
		"""Return the normalized payload produced at the validation boundary."""

		return dict(self.metadata.get("validated_payload") or {})

	@property
	def boundary_inputs(self) -> dict[str, Any]:
		"""Return the normalized deterministic calculator inputs."""

		return dict(self.metadata.get("boundary_inputs") or {})

	@property
	def valuation_model_code(self) -> ValuationModelCode | None:
		"""Return the validated deterministic model code if available."""

		return _normalize_model_code(self.metadata.get("valuation_model_code"))

	def set_model_selection(self, selection: Mapping[str, Any]) -> None:
		"""Persist the model-selection artifact in one place."""

		self.metadata["model_selection"] = dict(selection)

	def set_validation_artifacts(self, validation: Mapping[str, Any]) -> None:
		"""Persist the normalized payload and calculator-bound inputs."""

		self.metadata["validated_payload"] = dict(validation.get("normalized_payload") or {})
		self.metadata["boundary_inputs"] = dict(validation.get("normalized_inputs") or {})
		self.metadata["valuation_model_code"] = _normalize_model_code(validation.get("valuation_model_code"))
		growth_stage = validation.get("growth_stage")
		self.metadata["growth_stage"] = str(growth_stage) if growth_stage not in (None, "") else None

	def mark_error_step(self, step_name: WorkflowStep) -> None:
		"""Record the workflow step that most recently failed."""

		self.metadata["last_error_step"] = step_name

	def to_graph_state(self) -> AgentGraphState:
		"""Convert the dataclass into a serializable graph-friendly dictionary."""

		return {
			"ticker": self.ticker,
			"company_name": self.company_name,
			"model_name": self.model_name,
			"analysis_focus": self.analysis_focus,
			"stock_data": self.stock_data,
			"source_links": list(self.source_links),
			"source_notes": list(self.source_notes),
			"candidate_facts": list(self.candidate_facts),
			"selected_model": self.selected_model,
			"selected_variant": self.selected_variant,
			"parameter_payload": dict(self.parameter_payload),
			"valuation_result": dict(self.valuation_result),
			"explanation": self.explanation,
			"confidence": self.confidence,
			"errors": list(self.errors),
			"research_report": self.research_report,
			"supervisor_plan": self.supervisor_plan,
			"validation_status": self.validation_status,
			"validation_errors": list(self.validation_errors),
			"validation_attempts": self.validation_attempts,
			"max_validation_attempts": self.max_validation_attempts,
			"next_step": self.next_step,
			"metadata": dict(self.metadata),
		}

	@classmethod
	def from_graph_state(cls, payload: "AgentGraphState | AgentRunState") -> "AgentRunState":
		"""Normalize either a dict payload or an existing state instance."""

		if isinstance(payload, cls):
			return payload
		return cls(
			ticker=str(payload.get("ticker") or "").strip().upper(),
			company_name=str(payload.get("company_name") or "").strip(),
			model_name=payload.get("model_name"),
			analysis_focus=payload.get("analysis_focus"),
			stock_data=payload.get("stock_data"),
			source_links=list(payload.get("source_links") or []),
			source_notes=list(payload.get("source_notes") or []),
			candidate_facts=list(payload.get("candidate_facts") or []),
			selected_model=payload.get("selected_model"),
			selected_variant=payload.get("selected_variant"),
			parameter_payload=dict(payload.get("parameter_payload") or {}),
			valuation_result=dict(payload.get("valuation_result") or {}),
			explanation=str(payload.get("explanation") or ""),
			confidence=payload.get("confidence"),
			errors=list(payload.get("errors") or []),
			research_report=str(payload.get("research_report") or ""),
			supervisor_plan=str(payload.get("supervisor_plan") or ""),
			validation_status=_normalize_validation_status(payload.get("validation_status")),
			validation_errors=list(payload.get("validation_errors") or []),
			validation_attempts=int(payload.get("validation_attempts") or 0),
			max_validation_attempts=int(payload.get("max_validation_attempts") or 2),
			next_step=_normalize_next_step(payload.get("next_step")),
			metadata=cast(AgentMetadata, dict(payload.get("metadata") or {})),
		)
