from __future__ import annotations

from dataclasses import dataclass

from valuation.ddm.schemas import DDMAssumptions, DDMOutput
from valuation.dcf.schemas import DCFAssumptions, DCFOutput
from valuation.rim.schemas import RIMAssumptions, RIMOutput


@dataclass(slots=True)
class AgentInput:
    """Minimal input used to trigger the agent workflow."""

    ticker: str


@dataclass(slots=True)
class AgentOutput:
    """Final structured output returned by the agent."""

    ticker: str
    macro_industry_analysis: str | None = None
    qualitative_analysis: str | None = None
    quantitative_analysis: str | None = None
    selected_model: str | None = None
    model_selection_reason: str | None = None
    estimated_dcf_assumptions: DCFAssumptions | None = None
    estimated_ddm_assumptions: DDMAssumptions | None = None
    estimated_rim_assumptions: RIMAssumptions | None = None
    valuation_analysis: str | None = None
    notes: str | None = None
    dcf_output: DCFOutput | None = None
    ddm_output: DDMOutput | None = None
    rim_output: RIMOutput | None = None
