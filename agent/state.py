from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict


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
	validation_status: str
	validation_errors: list[str]
	validation_attempts: int
	max_validation_attempts: int
	next_step: str | None
	metadata: dict[str, Any]


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
	validation_status: str = "not_run"
	validation_errors: list[str] = field(default_factory=list)
	validation_attempts: int = 0
	max_validation_attempts: int = 2
	next_step: str | None = None
	metadata: dict[str, Any] = field(default_factory=dict)

	@property
	def fetched_facts(self) -> list[dict[str, Any]]:
		"""Compatibility alias for earlier workflow code."""

		return self.candidate_facts

	@property
	def assumptions(self) -> dict[str, Any]:
		"""Return the estimated assumptions block from the parameter payload."""

		return dict(self.parameter_payload.get("assumptions") or {})

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
			validation_status=str(payload.get("validation_status") or "not_run"),
			validation_errors=list(payload.get("validation_errors") or []),
			validation_attempts=int(payload.get("validation_attempts") or 0),
			max_validation_attempts=int(payload.get("max_validation_attempts") or 2),
			next_step=payload.get("next_step"),
			metadata=dict(payload.get("metadata") or {}),
		)
