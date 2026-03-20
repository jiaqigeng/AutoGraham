from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FlexibleSchema(BaseModel):
	"""Base schema that tolerates extra fields from evolving agent outputs."""

	model_config = ConfigDict(extra="allow")


class SourceNote(FlexibleSchema):
	title: str = ""
	url: str | None = None
	snippet: str = ""
	source_type: str = "reference"
	confidence: float | None = None


class CandidateFact(FlexibleSchema):
	key: str = ""
	label: str
	value: Any = None
	numeric_value: float | None = None
	unit: str | None = None
	source: str | None = None
	citation: str | None = None
	confidence: float | None = None
	note: str = ""


FetchedFact = CandidateFact


class AssumptionReason(FlexibleSchema):
	key: str
	reason: str


class ModelRecommendation(FlexibleSchema):
	selected_model: Literal["DCF", "DDM", "RIM"]
	selected_variant: str | None = None
	model_reason: str = ""
	preferred_calculation_model: Literal["FCFF", "FCFE", "DDM", "RIM"] | None = None
	confidence: float | None = None


class ParameterPayload(FlexibleSchema):
	selected_model: Literal["DCF", "DDM", "RIM"]
	selected_variant: str | None = None
	calculation_model: Literal["FCFF", "FCFE", "DDM", "RIM"] | None = None
	parameter_reason: str = ""
	fetched_facts: list[CandidateFact] = Field(default_factory=list)
	assumptions: dict[str, Any] = Field(default_factory=dict)
	assumption_reasons: list[AssumptionReason] = Field(default_factory=list)
	confidence: float | None = None
