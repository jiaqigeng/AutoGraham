from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Literal

from dotenv import load_dotenv
from openai import OpenAI

from agent.schemas import AgentInput, AgentOutput
from agent.tools import (
    load_annual_financials,
    load_company_info,
    load_context_source_data,
    load_dcf_market_seed,
    load_ddm_market_seed,
    load_market_snapshot,
    load_quarterly_financials,
    load_rim_market_seed,
    list_available_valuation_models,
    load_valuation_context,
    run_dcf_valuation_tool,
    run_dcf_tool,
    run_ddm_tool,
    run_ddm_valuation_tool,
    run_rim_tool,
    run_rim_valuation_tool,
)
from data.market.schemas import CompanyInfo, FinancialPeriod, MarketSnapshot
from valuation.ddm.schemas import DDMAssumptions, DDMInput, DDMMarketData, DDMOutput
from valuation.dcf.schemas import DCFAssumptions, DCFInput, DCFMarketData, DCFOutput
from valuation.rim.schemas import RIMAssumptions, RIMInput, RIMMarketData, RIMOutput

try:
    from deepagents import create_deep_agent
except ImportError:  # pragma: no cover - optional dependency
    create_deep_agent = None

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - optional dependency
    BaseModel = None
    Field = None


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


SKILLS_DIR = Path(__file__).resolve().parent / "skills"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
DCF_ASSUMPTION_SKILL_NAME = "dcf_analysis"
DDM_ASSUMPTION_SKILL_NAME = "ddm_analysis"
RIM_ASSUMPTION_SKILL_NAME = "rim_analysis"
VALUATION_MODEL_IDS = ("dcf", "ddm", "rim")
CORE_ANALYSIS_KEYS = [
    "macro_industry_analysis",
    "qualitative_analysis",
    "quantitative_analysis",
]
FINAL_REPORT_KEYS = [
    "valuation_analysis",
    "notes",
]
SKILL_NAMES = [
    "macro_industry_analysis",
    "qualitative_analysis",
    "quantitative_analysis",
    "valuation_analysis",
    "conclusion",
]


if BaseModel is not None and Field is not None:

    class DeepAgentContextResponse(BaseModel):
        """Structured context bundle produced by the context-building agent."""

        ticker: str = Field(description="Ticker used for the analysis.")
        company_info: dict[str, Any] = Field(
            description="Normalized company metadata relevant to the analysis."
        )
        market_snapshot: dict[str, Any] = Field(
            description="Normalized market snapshot relevant to the analysis."
        )
        recent_annual_financials: list[dict[str, Any]] = Field(
            description="Recent annual financial periods relevant to the analysis."
        )
        recent_quarterly_financials: list[dict[str, Any]] = Field(
            description="Recent quarterly financial periods relevant to the analysis."
        )
        trend_summary: dict[str, Any] = Field(
            description="Normalized trend summary built from the financial history."
        )
        context_summary: str = Field(
            description="Concise synthesis of the operating and valuation-relevant context."
        )
        key_observations: list[str] = Field(
            description="Short, high-signal observations distilled from the raw context."
        )
        missing_data_notes: list[str] = Field(
            description="Explicit limitations, missing data, and context gaps."
        )


    class DeepAgentValuationWorkflowResponse(BaseModel):
        """Structured output returned by the valuation agent."""

        selected_model: Literal["dcf", "ddm", "rim"] = Field(
            description="The valuation model selected by the agent."
        )
        model_selection_reason: str = Field(
            description="Why the selected model was chosen from the available models."
        )
        assumptions: dict[str, Any] = Field(
            description="The exact model-specific assumptions used for the selected valuation model."
        )
        valuation_result: dict[str, Any] = Field(
            description="The serialized valuation result returned by the selected valuation tool."
        )
        valuation_summary: str = Field(
            description="Concise explanation of what the valuation output implies."
        )
        valuation_notes: str = Field(
            description="Concise caveats about the valuation result and assumptions."
        )

    class DeepAgentValuationResponse(BaseModel):
        """Structured output returned by the LangChain deep-agent supervisor."""

        macro_industry_analysis: str = Field(
            description="Macro and industry analysis grounded only in collected evidence."
        )
        qualitative_analysis: str = Field(
            description="Company-specific qualitative analysis grounded only in collected evidence."
        )
        quantitative_analysis: str = Field(
            description="Quantitative analysis grounded only in collected evidence."
        )
        selected_model: Literal["dcf", "ddm", "rim"] = Field(
            description="The valuation model selected by the agent."
        )
        model_selection_reason: str = Field(
            description="Why the selected model was chosen from the currently available models."
        )
        assumptions: dict[str, Any] = Field(
            description="The exact model-specific assumptions used for the selected valuation model."
        )
        valuation_result: dict[str, Any] = Field(
            description="The serialized valuation result returned by the selected valuation tool."
        )
        valuation_analysis: str = Field(
            description="Concise valuation commentary that explains the key drivers of the selected model."
        )
        notes: str = Field(
            description="Any caveats, missing-data notes, or limitations for the analysis."
        )


    class DeepAgentReportResponse(BaseModel):
        """Structured output returned by the writer agent for the final AI report."""

        macro_industry_analysis: str = Field(
            description="Final AI-report-ready macro and industry analysis."
        )
        qualitative_analysis: str = Field(
            description="Final AI-report-ready qualitative analysis."
        )
        quantitative_analysis: str = Field(
            description="Final AI-report-ready quantitative analysis."
        )
        valuation_analysis: str = Field(
            description="Final AI-report-ready valuation discussion using the computed valuation result."
        )
        notes: str = Field(
            description="Final AI-report-ready notes and caveats."
        )


    class DeepAgentWriterDraftResponse(BaseModel):
        """First-pass narrative sections produced before valuation is available."""

        macro_industry_analysis: str = Field(
            description="Professional macro and industry section."
        )
        qualitative_analysis: str = Field(
            description="Professional qualitative section."
        )
        quantitative_analysis: str = Field(
            description="Professional quantitative section."
        )


    class DeepAgentWriterFinalizeResponse(BaseModel):
        """Final report sections produced after valuation results are available."""

        valuation_analysis: str = Field(
            description="Professional valuation section that interprets the valuation result without rendering raw tables."
        )
        notes: str = Field(
            description="Professional limitations, caveats, and next-step notes."
        )
        valuation_table_intro: str = Field(
            description="One or two concise sentences introducing the valuation tables and telling the reader what matters most."
        )

else:
    DeepAgentContextResponse = None
    DeepAgentValuationWorkflowResponse = None
    DeepAgentValuationResponse = None
    DeepAgentReportResponse = None
    DeepAgentWriterDraftResponse = None
    DeepAgentWriterFinalizeResponse = None


def load_skill(name: str) -> str:
    """Load a markdown skill file from the local skills directory."""
    skill_path = SKILLS_DIR / f"{name}.md"
    try:
        return skill_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the project .env file or environment."
        )
    return OpenAI(api_key=api_key)


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _safe_tool_call(
    tool_func: Callable[..., Any],
    *args: Any,
    default: Any,
    errors: list[str],
    label: str,
) -> Any:
    try:
        result = tool_func(*args)
    except Exception as exc:
        errors.append(f"{label} failed: {exc}")
        return default
    return result if result is not None else default


def _sort_periods(periods: list[FinancialPeriod]) -> list[FinancialPeriod]:
    return sorted(periods, key=lambda period: period.period_end)


def _latest_period(periods: list[FinancialPeriod]) -> FinancialPeriod | None:
    if not periods:
        return None
    return _sort_periods(periods)[-1]


def _format_number(value: float | None) -> str | None:
    if value is None:
        return None

    absolute_value = abs(value)
    if absolute_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if absolute_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if absolute_value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:,.2f}"


def _format_percent(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value * 100:.1f}%"


def _growth_rate(current_value: float | None, prior_value: float | None) -> float | None:
    if current_value is None or prior_value in (None, 0):
        return None
    return (current_value - prior_value) / abs(prior_value)


def _build_dcf_market_data_seed(
    annual_financials: list[FinancialPeriod],
    market_snapshot: MarketSnapshot | None,
) -> dict[str, float | None] | None:
    latest = _latest_period(annual_financials)
    if latest is None:
        return None

    current_revenue = latest.revenue
    current_ebit = latest.ebit if latest.ebit is not None else latest.operating_income
    shares_outstanding = (
        latest.shares_outstanding
        if latest.shares_outstanding is not None
        else (market_snapshot.shares_outstanding if market_snapshot else None)
    )

    cash = latest.cash
    total_debt = latest.total_debt

    if (
        current_revenue in (None, 0)
        or current_ebit is None
        or shares_outstanding in (None, 0)
        or cash is None
        or total_debt is None
    ):
        return None

    return {
        "current_revenue": float(current_revenue),
        "current_ebit": float(current_ebit),
        "cash": float(cash),
        "total_debt": float(total_debt),
        "shares_outstanding": float(shares_outstanding),
        "current_price": market_snapshot.current_price if market_snapshot else None,
    }


def _build_dcf_estimation_context(
    market_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ticker": market_context.get("ticker"),
        "company_info": market_context.get("company_info", {}),
        "market_snapshot": market_context.get("market_snapshot", {}),
        "recent_annual_financials": market_context.get("recent_annual_financials", []),
        "recent_quarterly_financials": market_context.get(
            "recent_quarterly_financials", []
        ),
        "trend_summary": market_context.get("trend_summary", {}),
        "missing_data_notes": market_context.get("missing_data_notes", []),
    }


def _build_dcf_assumption_instruction_block(dcf_skill_text: str) -> str:
    sections = [
        "You are estimating explicit DCF assumptions for a single company.",
        "Use only the provided context.",
        "Do not use generic defaults, canned placeholders, or hidden fallback assumptions.",
        "Estimate every returned field from the company-specific evidence in the context.",
        "Return decimal values, not percentages. For example, return 0.08 for 8%.",
        "Return exactly one value per projected year for revenue_growth_rates, ebit_margins, tax_rates, da_as_pct_revenue, capex_as_pct_revenue, and nwc_as_pct_revenue.",
        "Choose a projection_years value that matches every returned array length.",
        "Do not return markdown.",
    ]

    dcf_guidance = dcf_skill_text.strip()
    if dcf_guidance:
        sections.append(f"{DCF_ASSUMPTION_SKILL_NAME} guidance:\n{dcf_guidance}")

    return "\n\n".join(sections)


def _build_dcf_assumption_prompt(ticker: str, context: dict[str, Any]) -> str:
    prompt_payload = {
        "task": "Estimate company-specific DCF assumptions from the provided context.",
        "ticker": ticker,
        "context": context,
    }
    return json.dumps(prompt_payload, indent=2)


def _build_ddm_assumption_instruction_block(ddm_skill_text: str) -> str:
    sections = [
        "You are estimating explicit DDM assumptions for a single company.",
        "Use only the provided context.",
        "Do not use generic defaults, canned placeholders, or hidden fallback assumptions.",
        "Estimate every returned field from the company-specific evidence in the context.",
        "Use DDM only when the company has a meaningful recurring dividend policy and the business appears stable enough for a dividend-based model.",
        "Return decimal values, not percentages. For example, return 0.08 for 8%.",
        "Return exactly one dividend_growth_rates value per projected year.",
        "Choose a projection_years value that matches the returned array length.",
        "Do not return markdown.",
    ]

    ddm_guidance = ddm_skill_text.strip()
    if ddm_guidance:
        sections.append(f"{DDM_ASSUMPTION_SKILL_NAME} guidance:\n{ddm_guidance}")

    return "\n\n".join(sections)


def _build_ddm_assumption_prompt(ticker: str, context: dict[str, Any]) -> str:
    prompt_payload = {
        "task": "Estimate company-specific DDM assumptions from the provided context.",
        "ticker": ticker,
        "context": context,
    }
    return json.dumps(prompt_payload, indent=2)


def _build_rim_assumption_instruction_block(rim_skill_text: str) -> str:
    sections = [
        "You are estimating explicit RIM assumptions for a single company.",
        "Use only the provided context.",
        "Do not use generic defaults, canned placeholders, or hidden fallback assumptions.",
        "Estimate every returned field from the company-specific evidence in the context.",
        "Use RIM only when book value and ROE are meaningful anchors for the business.",
        "Return decimal values, not percentages. For example, return 0.08 for 8%.",
        "Return exactly one value per projected year for return_on_equity and payout_ratios.",
        "Choose a projection_years value that matches every returned array length.",
        "Do not return markdown.",
    ]

    rim_guidance = rim_skill_text.strip()
    if rim_guidance:
        sections.append(f"{RIM_ASSUMPTION_SKILL_NAME} guidance:\n{rim_guidance}")

    return "\n\n".join(sections)


def _build_rim_assumption_prompt(ticker: str, context: dict[str, Any]) -> str:
    prompt_payload = {
        "task": "Estimate company-specific RIM assumptions from the provided context.",
        "ticker": ticker,
        "context": context,
    }
    return json.dumps(prompt_payload, indent=2)


def _build_model_selection_instruction_block(
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> str:
    sections = [
        "You are selecting the best valuation model for a single company.",
        "Use only the provided context and model-availability information.",
        "Select exactly one model from: dcf, ddm, rim.",
        "Prefer the model that best matches the business and has usable local input data.",
        "DCF fits businesses where operating cash flow and reinvestment economics are the key valuation driver.",
        "DDM fits mature, dividend-paying companies with a meaningful recurring dividend policy.",
        "RIM fits businesses where book value and ROE are economically meaningful, often including financials.",
        "Return JSON only.",
    ]

    if dcf_skill_text.strip():
        sections.append(f"{DCF_ASSUMPTION_SKILL_NAME} guidance:\n{dcf_skill_text.strip()}")
    if ddm_skill_text.strip():
        sections.append(f"{DDM_ASSUMPTION_SKILL_NAME} guidance:\n{ddm_skill_text.strip()}")
    if rim_skill_text.strip():
        sections.append(f"{RIM_ASSUMPTION_SKILL_NAME} guidance:\n{rim_skill_text.strip()}")

    return "\n\n".join(sections)


def _build_model_selection_prompt(
    ticker: str,
    context: dict[str, Any],
    available_models: dict[str, Any],
) -> str:
    prompt_payload = {
        "task": "Choose the best valuation model for this company.",
        "ticker": ticker,
        "available_models": available_models,
        "context": context,
    }
    return json.dumps(prompt_payload, indent=2)


def _build_core_analysis_instruction_block(skills: dict[str, str]) -> str:
    sections = [
        "You are a fundamental analysis assistant.",
        "Use only the provided context.",
        "Do not invent facts, news, transcript content, SEC details, competitors, or macro claims not supported by the context.",
        "For macro_industry_analysis, qualitative_analysis, and quantitative_analysis, analyze using the available context and do not explicitly call out missing data inside those sections.",
        "Write concise but useful analysis for each section.",
        "Do not use markdown formatting such as asterisks, bold, italics, bullets, headers, or code fences.",
        "Return plain text sentences inside each JSON value.",
        "Return JSON only with exactly these keys: macro_industry_analysis, qualitative_analysis, quantitative_analysis.",
        "Each value must be a string.",
    ]

    for skill_name in CORE_ANALYSIS_KEYS:
        skill_text = skills.get(skill_name, "").strip()
        if skill_text:
            sections.append(f"{skill_name} guidance:\n{skill_text}")

    return "\n\n".join(sections)


def _build_core_analysis_prompt(ticker: str, context: dict[str, Any]) -> str:
    prompt_payload = {
        "task": "Generate the macro, qualitative, and quantitative analysis sections for the given ticker.",
        "ticker": ticker,
        "context": context,
    }
    return json.dumps(prompt_payload, indent=2)


def _core_analysis_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "macro_industry_analysis": {"type": "string"},
            "qualitative_analysis": {"type": "string"},
            "quantitative_analysis": {"type": "string"},
        },
        "required": CORE_ANALYSIS_KEYS,
        "additionalProperties": False,
    }


def _dcf_assumptions_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "projection_years": {"type": "integer"},
            "revenue_growth_rates": {
                "type": "array",
                "items": {"type": "number"},
            },
            "ebit_margins": {
                "type": "array",
                "items": {"type": "number"},
            },
            "tax_rates": {
                "type": "array",
                "items": {"type": "number"},
            },
            "da_as_pct_revenue": {
                "type": "array",
                "items": {"type": "number"},
            },
            "capex_as_pct_revenue": {
                "type": "array",
                "items": {"type": "number"},
            },
            "nwc_as_pct_revenue": {
                "type": "array",
                "items": {"type": "number"},
            },
            "wacc": {"type": "number"},
            "exit_multiple": {"type": "number"},
        },
        "required": [
            "projection_years",
            "revenue_growth_rates",
            "ebit_margins",
            "tax_rates",
            "da_as_pct_revenue",
            "capex_as_pct_revenue",
            "nwc_as_pct_revenue",
            "wacc",
            "exit_multiple",
        ],
        "additionalProperties": False,
    }


def _ddm_assumptions_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "projection_years": {"type": "integer"},
            "dividend_growth_rates": {
                "type": "array",
                "items": {"type": "number"},
            },
            "cost_of_equity": {"type": "number"},
            "terminal_growth_rate": {"type": "number"},
        },
        "required": [
            "projection_years",
            "dividend_growth_rates",
            "cost_of_equity",
            "terminal_growth_rate",
        ],
        "additionalProperties": False,
    }


def _rim_assumptions_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "projection_years": {"type": "integer"},
            "return_on_equity": {
                "type": "array",
                "items": {"type": "number"},
            },
            "payout_ratios": {
                "type": "array",
                "items": {"type": "number"},
            },
            "cost_of_equity": {"type": "number"},
            "terminal_return_on_equity": {"type": "number"},
            "terminal_growth_rate": {"type": "number"},
        },
        "required": [
            "projection_years",
            "return_on_equity",
            "payout_ratios",
            "cost_of_equity",
            "terminal_return_on_equity",
            "terminal_growth_rate",
        ],
        "additionalProperties": False,
    }


def _valuation_model_selection_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "selected_model": {
                "type": "string",
                "enum": list(VALUATION_MODEL_IDS),
            },
            "model_selection_reason": {"type": "string"},
        },
        "required": ["selected_model", "model_selection_reason"],
        "additionalProperties": False,
    }


def _coerce_float_list(value: Any, field_name: str) -> list[float]:
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"{field_name} must be a non-empty list.")
    return [float(item) for item in value]


def _validate_series(
    values: list[float],
    field_name: str,
    projection_years: int,
    minimum: float | None = None,
    maximum: float | None = None,
) -> None:
    if len(values) != projection_years:
        raise RuntimeError(f"{field_name} must contain {projection_years} values.")

    for value in values:
        if minimum is not None and value < minimum:
            raise RuntimeError(f"{field_name} values must be >= {minimum}.")
        if maximum is not None and value > maximum:
            raise RuntimeError(f"{field_name} values must be <= {maximum}.")


def _coerce_object_payload(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} output was not a JSON object.")
    return payload


def _parse_dcf_assumptions_payload(payload: dict[str, Any]) -> DCFAssumptions:
    projection_years = int(payload["projection_years"])
    if projection_years <= 0:
        raise RuntimeError("projection_years must be greater than 0.")

    revenue_growth_rates = _coerce_float_list(
        payload["revenue_growth_rates"], "revenue_growth_rates"
    )
    ebit_margins = _coerce_float_list(payload["ebit_margins"], "ebit_margins")
    tax_rates = _coerce_float_list(payload["tax_rates"], "tax_rates")
    da_as_pct_revenue = _coerce_float_list(
        payload["da_as_pct_revenue"], "da_as_pct_revenue"
    )
    capex_as_pct_revenue = _coerce_float_list(
        payload["capex_as_pct_revenue"], "capex_as_pct_revenue"
    )
    nwc_as_pct_revenue = _coerce_float_list(
        payload["nwc_as_pct_revenue"], "nwc_as_pct_revenue"
    )
    wacc = float(payload["wacc"])
    exit_multiple = float(payload["exit_multiple"])

    _validate_series(
        revenue_growth_rates,
        "revenue_growth_rates",
        projection_years,
        minimum=-0.99,
    )
    _validate_series(
        ebit_margins,
        "ebit_margins",
        projection_years,
        minimum=-1.0,
        maximum=1.0,
    )
    _validate_series(
        tax_rates,
        "tax_rates",
        projection_years,
        minimum=0.0,
        maximum=1.0,
    )
    _validate_series(
        da_as_pct_revenue,
        "da_as_pct_revenue",
        projection_years,
        minimum=0.0,
        maximum=1.0,
    )
    _validate_series(
        capex_as_pct_revenue,
        "capex_as_pct_revenue",
        projection_years,
        minimum=0.0,
        maximum=1.0,
    )
    _validate_series(
        nwc_as_pct_revenue,
        "nwc_as_pct_revenue",
        projection_years,
        minimum=-1.0,
        maximum=1.0,
    )

    if wacc <= -1.0:
        raise RuntimeError("wacc must be greater than -1.0.")
    if exit_multiple < 0.0:
        raise RuntimeError("exit_multiple must be non-negative.")

    return DCFAssumptions(
        projection_years=projection_years,
        revenue_growth_rates=revenue_growth_rates,
        ebit_margins=ebit_margins,
        tax_rates=tax_rates,
        da_as_pct_revenue=da_as_pct_revenue,
        capex_as_pct_revenue=capex_as_pct_revenue,
        nwc_as_pct_revenue=nwc_as_pct_revenue,
        wacc=wacc,
        exit_multiple=exit_multiple,
    )


def _parse_ddm_assumptions_payload(payload: dict[str, Any]) -> DDMAssumptions:
    projection_years = int(payload["projection_years"])
    if projection_years <= 0:
        raise RuntimeError("projection_years must be greater than 0.")

    dividend_growth_rates = _coerce_float_list(
        payload["dividend_growth_rates"], "dividend_growth_rates"
    )
    _validate_series(
        dividend_growth_rates,
        "dividend_growth_rates",
        projection_years,
        minimum=-0.99,
    )

    cost_of_equity = float(payload["cost_of_equity"])
    terminal_growth_rate = float(payload["terminal_growth_rate"])
    if cost_of_equity <= -1.0:
        raise RuntimeError("cost_of_equity must be greater than -1.0.")
    if terminal_growth_rate <= -1.0:
        raise RuntimeError("terminal_growth_rate must be greater than -1.0.")
    if terminal_growth_rate >= cost_of_equity:
        raise RuntimeError("terminal_growth_rate must be less than cost_of_equity.")

    return DDMAssumptions(
        projection_years=projection_years,
        dividend_growth_rates=dividend_growth_rates,
        cost_of_equity=cost_of_equity,
        terminal_growth_rate=terminal_growth_rate,
    )


def _parse_rim_assumptions_payload(payload: dict[str, Any]) -> RIMAssumptions:
    projection_years = int(payload["projection_years"])
    if projection_years <= 0:
        raise RuntimeError("projection_years must be greater than 0.")

    return_on_equity = _coerce_float_list(
        payload["return_on_equity"], "return_on_equity"
    )
    payout_ratios = _coerce_float_list(payload["payout_ratios"], "payout_ratios")

    _validate_series(
        return_on_equity,
        "return_on_equity",
        projection_years,
        minimum=-5.0,
        maximum=5.0,
    )
    _validate_series(
        payout_ratios,
        "payout_ratios",
        projection_years,
        minimum=0.0,
        maximum=1.5,
    )

    cost_of_equity = float(payload["cost_of_equity"])
    terminal_return_on_equity = float(payload["terminal_return_on_equity"])
    terminal_growth_rate = float(payload["terminal_growth_rate"])
    if cost_of_equity <= -1.0:
        raise RuntimeError("cost_of_equity must be greater than -1.0.")
    if terminal_growth_rate <= -1.0:
        raise RuntimeError("terminal_growth_rate must be greater than -1.0.")
    if terminal_growth_rate >= cost_of_equity:
        raise RuntimeError("terminal_growth_rate must be less than cost_of_equity.")

    return RIMAssumptions(
        projection_years=projection_years,
        return_on_equity=return_on_equity,
        payout_ratios=payout_ratios,
        cost_of_equity=cost_of_equity,
        terminal_return_on_equity=terminal_return_on_equity,
        terminal_growth_rate=terminal_growth_rate,
    )


def _parse_dcf_assumptions(raw_json: str) -> DCFAssumptions:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse DCF assumptions JSON output: {exc}") from exc

    return _parse_dcf_assumptions_payload(_coerce_object_payload(payload, "DCF assumptions"))


def _parse_ddm_assumptions(raw_json: str) -> DDMAssumptions:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse DDM assumptions JSON output: {exc}") from exc

    return _parse_ddm_assumptions_payload(_coerce_object_payload(payload, "DDM assumptions"))


def _parse_rim_assumptions(raw_json: str) -> RIMAssumptions:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse RIM assumptions JSON output: {exc}") from exc

    return _parse_rim_assumptions_payload(_coerce_object_payload(payload, "RIM assumptions"))


def _parse_model_selection_output(raw_json: str) -> dict[str, str]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse valuation model selection JSON output: {exc}"
        ) from exc

    parsed = _coerce_object_payload(payload, "valuation model selection")
    selected_model = str(parsed.get("selected_model") or "").strip().lower()
    if selected_model not in VALUATION_MODEL_IDS:
        raise RuntimeError(
            f"selected_model must be one of: {', '.join(VALUATION_MODEL_IDS)}."
        )

    return {
        "selected_model": selected_model,
        "model_selection_reason": str(parsed.get("model_selection_reason") or ""),
    }


def _parse_core_analysis_output(raw_json: str) -> dict[str, str]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse core analysis JSON output: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Core analysis output was not a JSON object.")

    missing_keys = [key for key in CORE_ANALYSIS_KEYS if key not in payload]
    if missing_keys:
        raise RuntimeError(
            f"Core analysis JSON is missing required keys: {', '.join(sorted(missing_keys))}."
        )

    return {
        "macro_industry_analysis": str(payload.get("macro_industry_analysis") or ""),
        "qualitative_analysis": str(payload.get("qualitative_analysis") or ""),
        "quantitative_analysis": str(payload.get("quantitative_analysis") or ""),
    }


def _generate_core_analysis(
    client: OpenAI,
    model: str,
    ticker: str,
    context: dict[str, Any],
    skills: dict[str, str],
) -> dict[str, str]:
    raw_json = _call_model(
        client=client,
        model=model,
        instructions=_build_core_analysis_instruction_block(skills),
        user_prompt=_build_core_analysis_prompt(ticker, context),
        schema_name="core_analysis",
        schema=_core_analysis_json_schema(),
    )
    return _parse_core_analysis_output(raw_json)


def _estimate_dcf_assumptions(
    client: OpenAI,
    model: str,
    ticker: str,
    market_context: dict[str, Any],
    dcf_skill_text: str,
) -> DCFAssumptions:
    instructions = _build_dcf_assumption_instruction_block(dcf_skill_text)
    user_prompt = _build_dcf_assumption_prompt(
        ticker=ticker,
        context=_build_dcf_estimation_context(market_context),
    )
    raw_json = _call_model(
        client=client,
        model=model,
        instructions=instructions,
        user_prompt=user_prompt,
        schema_name="dcf_assumptions",
        schema=_dcf_assumptions_json_schema(),
    )
    return _parse_dcf_assumptions(raw_json)


def _estimate_ddm_assumptions(
    client: OpenAI,
    model: str,
    ticker: str,
    market_context: dict[str, Any],
    ddm_skill_text: str,
) -> DDMAssumptions:
    raw_json = _call_model(
        client=client,
        model=model,
        instructions=_build_ddm_assumption_instruction_block(ddm_skill_text),
        user_prompt=_build_ddm_assumption_prompt(
            ticker=ticker,
            context=_build_dcf_estimation_context(market_context),
        ),
        schema_name="ddm_assumptions",
        schema=_ddm_assumptions_json_schema(),
    )
    return _parse_ddm_assumptions(raw_json)


def _estimate_rim_assumptions(
    client: OpenAI,
    model: str,
    ticker: str,
    market_context: dict[str, Any],
    rim_skill_text: str,
) -> RIMAssumptions:
    raw_json = _call_model(
        client=client,
        model=model,
        instructions=_build_rim_assumption_instruction_block(rim_skill_text),
        user_prompt=_build_rim_assumption_prompt(
            ticker=ticker,
            context=_build_dcf_estimation_context(market_context),
        ),
        schema_name="rim_assumptions",
        schema=_rim_assumptions_json_schema(),
    )
    return _parse_rim_assumptions(raw_json)


def _select_valuation_model(
    client: OpenAI,
    model: str,
    ticker: str,
    market_context: dict[str, Any],
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> dict[str, str]:
    available_models = list_available_valuation_models(ticker=ticker)
    raw_json = _call_model(
        client=client,
        model=model,
        instructions=_build_model_selection_instruction_block(
            dcf_skill_text=dcf_skill_text,
            ddm_skill_text=ddm_skill_text,
            rim_skill_text=rim_skill_text,
        ),
        user_prompt=_build_model_selection_prompt(
            ticker=ticker,
            context=market_context,
            available_models=available_models,
        ),
        schema_name="valuation_model_selection",
        schema=_valuation_model_selection_json_schema(),
    )
    return _parse_model_selection_output(raw_json)


def _build_dcf_input(
    market_data_seed: dict[str, float | None],
    assumptions: DCFAssumptions,
) -> DCFInput:
    current_revenue = float(market_data_seed["current_revenue"])
    tax_rates = assumptions.tax_rates
    da_rates = assumptions.da_as_pct_revenue
    capex_rates = assumptions.capex_as_pct_revenue
    nwc_rates = assumptions.nwc_as_pct_revenue

    return DCFInput(
        market_data=DCFMarketData(
            current_revenue=current_revenue,
            current_ebit=float(market_data_seed["current_ebit"]),
            tax_rate=float(tax_rates[0]),
            depreciation_amortization=current_revenue * float(da_rates[0]),
            capex=current_revenue * float(capex_rates[0]),
            change_in_nwc=current_revenue * float(nwc_rates[0]),
            cash=float(market_data_seed["cash"]),
            total_debt=float(market_data_seed["total_debt"]),
            shares_outstanding=float(market_data_seed["shares_outstanding"]),
            current_price=(
                float(market_data_seed["current_price"])
                if market_data_seed["current_price"] is not None
                else None
            ),
        ),
        assumptions=assumptions,
    )


def _build_ddm_input(
    market_data_seed: dict[str, float | None],
    assumptions: DDMAssumptions,
) -> DDMInput:
    return DDMInput(
        market_data=DDMMarketData(
            current_dividend_per_share=float(market_data_seed["current_dividend_per_share"]),
            shares_outstanding=float(market_data_seed["shares_outstanding"]),
            current_price=(
                float(market_data_seed["current_price"])
                if market_data_seed["current_price"] is not None
                else None
            ),
        ),
        assumptions=assumptions,
    )


def _build_rim_input(
    market_data_seed: dict[str, float | None],
    assumptions: RIMAssumptions,
) -> RIMInput:
    return RIMInput(
        market_data=RIMMarketData(
            current_book_value_per_share=float(
                market_data_seed["current_book_value_per_share"]
            ),
            shares_outstanding=float(market_data_seed["shares_outstanding"]),
            current_price=(
                float(market_data_seed["current_price"])
                if market_data_seed["current_price"] is not None
                else None
            ),
        ),
        assumptions=assumptions,
    )


def _run_dcf_if_possible(
    client: OpenAI,
    model: str,
    ticker: str,
    market_context: dict[str, Any],
    market_snapshot: MarketSnapshot | None,
    annual_financials: list[FinancialPeriod],
    dcf_skill_text: str,
    errors: list[str],
) -> DCFOutput | None:
    market_data_seed = _build_dcf_market_data_seed(annual_financials, market_snapshot)
    if market_data_seed is None:
        errors.append(
            "DCF valuation skipped because required source fields were missing from the latest annual data."
        )
        return None

    try:
        assumptions = _estimate_dcf_assumptions(
            client=client,
            model=model,
            ticker=ticker,
            market_context=market_context,
            dcf_skill_text=dcf_skill_text,
        )
        dcf_input = _build_dcf_input(market_data_seed, assumptions)
        return run_dcf_tool(dcf_input)
    except Exception as exc:
        errors.append(f"DCF valuation failed: {exc}")
        return None


def _assumptions_from_payload(
    selected_model: str,
    payload: dict[str, Any],
) -> DCFAssumptions | DDMAssumptions | RIMAssumptions:
    if selected_model == "dcf":
        return _parse_dcf_assumptions_payload(payload)
    if selected_model == "ddm":
        return _parse_ddm_assumptions_payload(payload)
    if selected_model == "rim":
        return _parse_rim_assumptions_payload(payload)
    raise RuntimeError(f"Unsupported valuation model: {selected_model}")


def _valuation_from_deep_agent_response(
    response: Any,
) -> tuple[
    str,
    DCFAssumptions | DDMAssumptions | RIMAssumptions,
]:
    selected_model = str(response.selected_model).strip().lower()
    if selected_model not in VALUATION_MODEL_IDS:
        raise RuntimeError(
            f"selected_model must be one of: {', '.join(VALUATION_MODEL_IDS)}."
        )

    assumptions_payload = _coerce_object_payload(
        response.assumptions,
        "valuation assumptions",
    )
    return selected_model, _assumptions_from_payload(selected_model, assumptions_payload)


def _run_selected_valuation(
    ticker: str,
    selected_model: str,
    assumptions: DCFAssumptions | DDMAssumptions | RIMAssumptions,
) -> DCFOutput | DDMOutput | RIMOutput:
    if selected_model == "dcf":
        market_data_seed = load_dcf_market_seed(ticker=ticker)
        if not market_data_seed:
            raise RuntimeError(
                "DCF valuation could not be reconstructed because required source fields were missing from the latest annual data."
            )
        if not isinstance(assumptions, DCFAssumptions):
            raise RuntimeError("DCF assumptions were required for the DCF model.")
        return run_dcf_tool(_build_dcf_input(market_data_seed, assumptions))

    if selected_model == "ddm":
        market_data_seed = load_ddm_market_seed(ticker=ticker)
        if not market_data_seed:
            raise RuntimeError(
                "DDM valuation could not be reconstructed because required source fields were missing from the latest annual data."
            )
        if not isinstance(assumptions, DDMAssumptions):
            raise RuntimeError("DDM assumptions were required for the DDM model.")
        return run_ddm_tool(_build_ddm_input(market_data_seed, assumptions))

    if selected_model == "rim":
        market_data_seed = load_rim_market_seed(ticker=ticker)
        if not market_data_seed:
            raise RuntimeError(
                "RIM valuation could not be reconstructed because required source fields were missing from the latest annual data."
            )
        if not isinstance(assumptions, RIMAssumptions):
            raise RuntimeError("RIM assumptions were required for the RIM model.")
        return run_rim_tool(_build_rim_input(market_data_seed, assumptions))

    raise RuntimeError(f"Unsupported valuation model: {selected_model}")


def _serialize_company_info(company_info: CompanyInfo | None) -> dict[str, Any]:
    if company_info is None:
        return {}

    return {
        "ticker": company_info.ticker,
        "company_name": company_info.company_name,
        "sector": company_info.sector,
        "industry": company_info.industry,
        "exchange": company_info.exchange,
        "currency": company_info.currency,
    }


def _serialize_market_snapshot(snapshot: MarketSnapshot | None) -> dict[str, Any]:
    if snapshot is None:
        return {}

    return {
        "current_price": snapshot.current_price,
        "market_cap": snapshot.market_cap,
        "enterprise_value": snapshot.enterprise_value,
        "shares_outstanding": snapshot.shares_outstanding,
        "beta": snapshot.beta,
        "pe_ratio": snapshot.pe_ratio,
        "pb_ratio": snapshot.pb_ratio,
        "ps_ratio": snapshot.ps_ratio,
        "dividend_yield": snapshot.dividend_yield,
        "fifty_two_week_high": snapshot.fifty_two_week_high,
        "fifty_two_week_low": snapshot.fifty_two_week_low,
    }


def _serialize_financial_period(period: FinancialPeriod) -> dict[str, Any]:
    return {
        "period_end": period.period_end.isoformat(),
        "period_type": period.period_type,
        "fiscal_year": period.fiscal_year,
        "fiscal_quarter": period.fiscal_quarter,
        "revenue": period.revenue,
        "gross_profit": period.gross_profit,
        "ebit": period.ebit,
        "operating_income": period.operating_income,
        "net_income": period.net_income,
        "depreciation_amortization": period.depreciation_amortization,
        "interest_expense": period.interest_expense,
        "income_tax_expense": period.income_tax_expense,
        "dividends_paid": period.dividends_paid,
        "capex": period.capex,
        "change_in_nwc": period.change_in_nwc,
        "operating_cash_flow": period.operating_cash_flow,
        "free_cash_flow": period.free_cash_flow,
        "cash": period.cash,
        "total_debt": period.total_debt,
        "shareholders_equity": period.shareholders_equity,
        "shares_outstanding": period.shares_outstanding,
    }


def _serialize_dcf_output(dcf_output: DCFOutput | None) -> dict[str, Any]:
    if dcf_output is None:
        return {}

    return {
        "fair_value_per_share": dcf_output.fair_value_per_share,
        "current_price": dcf_output.current_price,
        "upside_downside_pct": dcf_output.upside_downside_pct,
        "enterprise_value": dcf_output.enterprise_value,
        "equity_value": dcf_output.equity_value,
        "terminal_value_pct_of_enterprise_value": dcf_output.terminal_value_pct_of_enterprise_value,
        "projection_years": len(dcf_output.projected_years),
        "assumption_source": "OpenAI-estimated company-specific assumptions",
        "assumptions_used": {
            "projection_years": dcf_output.assumptions_used.projection_years
            if dcf_output.assumptions_used
            else None,
            "wacc": dcf_output.assumptions_used.wacc if dcf_output.assumptions_used else None,
            "exit_multiple": (
                dcf_output.assumptions_used.exit_multiple
                if dcf_output.assumptions_used
                else None
            ),
            "revenue_growth_rates": (
                dcf_output.assumptions_used.revenue_growth_rates
                if dcf_output.assumptions_used
                else None
            ),
            "ebit_margins": (
                dcf_output.assumptions_used.ebit_margins
                if dcf_output.assumptions_used
                else None
            ),
        },
    }


def _serialize_ddm_output(ddm_output: DDMOutput | None) -> dict[str, Any]:
    if ddm_output is None:
        return {}

    return {
        "selected_model": "ddm",
        "fair_value_per_share": ddm_output.fair_value_per_share,
        "current_price": ddm_output.current_price,
        "upside_downside_pct": ddm_output.upside_downside_pct,
        "equity_value": ddm_output.equity_value,
        "terminal_value_pct_of_fair_value": ddm_output.terminal_value_pct_of_fair_value,
        "projection_years": len(ddm_output.projected_years),
        "assumption_source": "OpenAI-estimated company-specific assumptions",
        "assumptions_used": {
            "projection_years": ddm_output.assumptions_used.projection_years
            if ddm_output.assumptions_used
            else None,
            "cost_of_equity": (
                ddm_output.assumptions_used.cost_of_equity
                if ddm_output.assumptions_used
                else None
            ),
            "terminal_growth_rate": (
                ddm_output.assumptions_used.terminal_growth_rate
                if ddm_output.assumptions_used
                else None
            ),
            "dividend_growth_rates": (
                ddm_output.assumptions_used.dividend_growth_rates
                if ddm_output.assumptions_used
                else None
            ),
        },
    }


def _serialize_rim_output(rim_output: RIMOutput | None) -> dict[str, Any]:
    if rim_output is None:
        return {}

    return {
        "selected_model": "rim",
        "fair_value_per_share": rim_output.fair_value_per_share,
        "current_price": rim_output.current_price,
        "upside_downside_pct": rim_output.upside_downside_pct,
        "equity_value": rim_output.equity_value,
        "terminal_value_pct_of_fair_value": rim_output.terminal_value_pct_of_fair_value,
        "projection_years": len(rim_output.projected_years),
        "assumption_source": "OpenAI-estimated company-specific assumptions",
        "assumptions_used": {
            "projection_years": rim_output.assumptions_used.projection_years
            if rim_output.assumptions_used
            else None,
            "cost_of_equity": (
                rim_output.assumptions_used.cost_of_equity
                if rim_output.assumptions_used
                else None
            ),
            "terminal_return_on_equity": (
                rim_output.assumptions_used.terminal_return_on_equity
                if rim_output.assumptions_used
                else None
            ),
            "terminal_growth_rate": (
                rim_output.assumptions_used.terminal_growth_rate
                if rim_output.assumptions_used
                else None
            ),
            "return_on_equity": (
                rim_output.assumptions_used.return_on_equity
                if rim_output.assumptions_used
                else None
            ),
            "payout_ratios": (
                rim_output.assumptions_used.payout_ratios
                if rim_output.assumptions_used
                else None
            ),
        },
    }


def _serialize_valuation_output(
    selected_model: str | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
) -> dict[str, Any]:
    if selected_model == "dcf":
        return _serialize_dcf_output(valuation_output if isinstance(valuation_output, DCFOutput) else None)
    if selected_model == "ddm":
        return _serialize_ddm_output(valuation_output if isinstance(valuation_output, DDMOutput) else None)
    if selected_model == "rim":
        return _serialize_rim_output(valuation_output if isinstance(valuation_output, RIMOutput) else None)
    return {}


def _build_missing_data_notes(
    company_info: CompanyInfo | None,
    market_snapshot: MarketSnapshot | None,
    annual_financials: list[FinancialPeriod],
    quarterly_financials: list[FinancialPeriod],
    selected_model: str | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
    errors: list[str],
    include_valuation_note: bool = True,
) -> list[str]:
    notes: list[str] = []

    if company_info is None:
        notes.append("Company metadata unavailable.")
    if market_snapshot is None:
        notes.append("Market snapshot unavailable.")
    if not annual_financials:
        notes.append("Annual financials unavailable.")
    if not quarterly_financials:
        notes.append("Quarterly financials unavailable.")
    if include_valuation_note and valuation_output is None:
        if selected_model:
            notes.append(f"{selected_model.upper()} output unavailable or not run.")
        else:
            notes.append("Valuation output unavailable or not run.")

    notes.append("Transcript data is not available in this run.")
    notes.append("SEC filing data is not available in this run.")

    notes.extend(errors)
    return notes


def _prepare_market_context(
    ticker: str,
    company_info: CompanyInfo | None,
    market_snapshot: MarketSnapshot | None,
    annual_financials: list[FinancialPeriod],
    quarterly_financials: list[FinancialPeriod],
    selected_model: str | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
    errors: list[str],
    include_valuation_context: bool = True,
) -> dict[str, Any]:
    annual_sorted = _sort_periods(annual_financials)
    quarterly_sorted = _sort_periods(quarterly_financials)
    latest_annual = _latest_period(annual_sorted)
    previous_annual = annual_sorted[-2] if len(annual_sorted) >= 2 else None

    latest_revenue_growth = (
        _growth_rate(latest_annual.revenue, previous_annual.revenue)
        if latest_annual and previous_annual
        else None
    )
    latest_ebit_growth = (
        _growth_rate(latest_annual.ebit, previous_annual.ebit)
        if latest_annual and previous_annual
        else None
    )
    latest_net_income_growth = (
        _growth_rate(latest_annual.net_income, previous_annual.net_income)
        if latest_annual and previous_annual
        else None
    )

    context = {
        "ticker": ticker,
        "company_info": _serialize_company_info(company_info),
        "market_snapshot": _serialize_market_snapshot(market_snapshot),
        "recent_annual_financials": [
            _serialize_financial_period(period) for period in annual_sorted[-5:]
        ],
        "recent_quarterly_financials": [
            _serialize_financial_period(period) for period in quarterly_sorted[-4:]
        ],
        "trend_summary": {
            "latest_annual_revenue_growth": latest_revenue_growth,
            "latest_annual_ebit_growth": latest_ebit_growth,
            "latest_annual_net_income_growth": latest_net_income_growth,
            "latest_annual_revenue_growth_text": _format_percent(latest_revenue_growth),
            "latest_annual_ebit_growth_text": _format_percent(latest_ebit_growth),
            "latest_annual_net_income_growth_text": _format_percent(
                latest_net_income_growth
            ),
            "latest_annual_revenue_text": _format_number(
                latest_annual.revenue if latest_annual else None
            ),
            "latest_annual_ebit_text": _format_number(
                latest_annual.ebit if latest_annual else None
            ),
            "latest_annual_net_income_text": _format_number(
                latest_annual.net_income if latest_annual else None
            ),
        },
        "missing_data_notes": _build_missing_data_notes(
            company_info=company_info,
            market_snapshot=market_snapshot,
            annual_financials=annual_financials,
            quarterly_financials=quarterly_financials,
            selected_model=selected_model,
            valuation_output=valuation_output,
            errors=errors,
            include_valuation_note=include_valuation_context,
        ),
    }

    if include_valuation_context:
        context["selected_model"] = selected_model
        context["valuation_summary"] = _serialize_valuation_output(
            selected_model,
            valuation_output,
        )

    return context


def _build_final_report_instruction_block(skills: dict[str, str]) -> str:
    sections = [
        "You are a fundamental analysis assistant.",
        "Use only the provided context.",
        "Do not invent facts, news, transcript content, SEC details, competitors, or macro claims not supported by the context.",
        "If transcript or SEC data is missing, explicitly state that the assessment is limited.",
        "Use the precomputed macro, qualitative, and quantitative analysis as fixed inputs rather than rewriting them.",
        "Write concise but useful valuation analysis and notes.",
        "Do not use markdown formatting such as asterisks, bold, italics, bullets, headers, or code fences.",
        "Return plain text sentences inside each JSON value.",
        "Return JSON only with exactly these keys: valuation_analysis, notes.",
        "Each value must be a string.",
    ]

    for skill_name in ["valuation_analysis", "conclusion"]:
        skill_text = skills.get(skill_name, "").strip()
        if skill_text:
            sections.append(f"{skill_name} guidance:\n{skill_text}")

    return "\n\n".join(sections)


def _build_user_prompt(ticker: str, context: dict[str, Any]) -> str:
    prompt_payload = {
        "task": "Generate structured fundamental analysis for the given ticker.",
        "ticker": ticker,
        "context": context,
    }
    return json.dumps(prompt_payload, indent=2)


def _build_final_report_prompt(
    ticker: str,
    context: dict[str, Any],
    core_analysis: dict[str, str],
) -> str:
    prompt_payload = {
        "task": "Assemble the final structured fundamental analysis report for the given ticker.",
        "ticker": ticker,
        "context": context,
        "precomputed_analysis": core_analysis,
    }
    return json.dumps(prompt_payload, indent=2)


def _final_report_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "valuation_analysis": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": FINAL_REPORT_KEYS,
        "additionalProperties": False,
    }


def _call_model(
    client: OpenAI,
    model: str,
    instructions: str,
    user_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
) -> str:
    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=user_prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    )

    response_text = getattr(response, "output_text", "") or ""
    if not response_text.strip():
        raise RuntimeError("OpenAI response did not contain JSON output text.")

    return response_text


def _parse_final_report_output(raw_json: str) -> dict[str, str]:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse final report JSON output: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("Final report output was not a JSON object.")

    missing_keys = [key for key in FINAL_REPORT_KEYS if key not in payload]
    if missing_keys:
        raise RuntimeError(
            f"Final report JSON is missing required keys: {', '.join(sorted(missing_keys))}."
        )

    return {
        "valuation_analysis": str(payload.get("valuation_analysis") or ""),
        "notes": str(payload.get("notes") or ""),
    }


def _deepagents_supported() -> bool:
    return (
        create_deep_agent is not None
        and DeepAgentContextResponse is not None
        and DeepAgentValuationWorkflowResponse is not None
        and DeepAgentWriterDraftResponse is not None
        and DeepAgentWriterFinalizeResponse is not None
    )


def _normalize_langchain_model(model: str) -> str:
    normalized = (model or DEFAULT_MODEL).strip()
    if not normalized:
        normalized = DEFAULT_MODEL
    if ":" in normalized:
        return normalized
    return f"openai:{normalized}"


def _format_currency_precise(value: float | None) -> str | None:
    if value is None:
        return None
    return f"${value:,.2f}"


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped


def _merge_note_text(*note_groups: str | list[str] | None) -> str:
    collected: list[str] = []
    for note_group in note_groups:
        if note_group is None:
            continue
        if isinstance(note_group, list):
            collected.extend(str(item) for item in note_group if str(item).strip())
            continue
        parts = [part.strip() for part in str(note_group).splitlines() if part.strip()]
        if parts:
            collected.append(" ".join(parts))
    return "\n".join(_dedupe_strings(collected))


def _model_to_dict(model_instance: Any) -> dict[str, Any]:
    if hasattr(model_instance, "model_dump"):
        return model_instance.model_dump()
    if hasattr(model_instance, "dict"):
        return model_instance.dict()
    raise RuntimeError("Structured response could not be converted to a dictionary.")


def _validate_structured_response(payload: Any, schema_cls: Any) -> Any:
    if schema_cls is None:
        raise RuntimeError("Structured response schema is unavailable.")

    if isinstance(payload, schema_cls):
        return payload

    if hasattr(schema_cls, "model_validate"):
        return schema_cls.model_validate(payload)

    return schema_cls.parse_obj(payload)


def _build_context_builder_agent_prompt(skills: dict[str, str]) -> str:
    sections = [
        "You are the context-building agent for an equity research workflow.",
        "Your job is to retrieve the relevant local data and build a clean shared context bundle for downstream agents.",
        "Always begin by calling load_context_source_data for the requested ticker.",
        "Use only tool output. Do not invent facts, transcript commentary, filing commentary, management statements, or unsupported industry claims.",
        "Do not choose a valuation model, do not estimate assumptions, and do not write the final report.",
        "Your context bundle should be high-signal and practical for valuation and writing.",
        "Return a concise context_summary and 4 to 8 key_observations that capture the most important operating, balance-sheet, and valuation-relevant signals.",
        "If source data is missing, capture that explicitly in missing_data_notes.",
    ]

    for skill_name in CORE_ANALYSIS_KEYS:
        skill_text = skills.get(skill_name, "").strip()
        if skill_text:
            sections.append(f"{skill_name} guidance:\n{skill_text}")

    return "\n\n".join(sections)


def _build_context_builder_user_prompt(ticker: str) -> str:
    payload = {
        "task": "Build the shared context bundle for this ticker before valuation and report writing.",
        "ticker": ticker,
    }
    return json.dumps(payload, indent=2)


def _build_parallel_valuation_agent_prompt(
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> str:
    sections = [
        "You are the valuation agent for an equity research workflow.",
        "You receive a completed shared context bundle from the context-building step.",
        "First, confirm the available model set by calling list_available_valuation_models with the ticker from the shared context bundle.",
        "Then select the best currently available model and justify the selection using business fit and input-data readiness.",
        "Estimate company-specific assumptions from the provided context only.",
        "If you select DCF, call run_dcf_valuation_tool.",
        "If you select DDM, call run_ddm_valuation_tool.",
        "If you select RIM, call run_rim_valuation_tool.",
        "Do not write macro, qualitative, or quantitative report sections.",
        "Return the selected_model, model_selection_reason, the exact assumptions you used in an assumptions object, the valuation tool result in a valuation_result object, and a concise interpretation of what the result implies.",
        "Return decimals, not percentages.",
        "Do not invent tool outputs. Copy valuation implications only from the calculated result.",
    ]
    if dcf_skill_text.strip():
        sections.append(f"{DCF_ASSUMPTION_SKILL_NAME} guidance:\n{dcf_skill_text.strip()}")
    if ddm_skill_text.strip():
        sections.append(f"{DDM_ASSUMPTION_SKILL_NAME} guidance:\n{ddm_skill_text.strip()}")
    if rim_skill_text.strip():
        sections.append(f"{RIM_ASSUMPTION_SKILL_NAME} guidance:\n{rim_skill_text.strip()}")
    return "\n\n".join(sections)


def _build_parallel_writer_prompt(skills: dict[str, str]) -> str:
    sections = [
        "You are the writer agent for the final AI equity report.",
        "Your job is to convert the structured context and valuation output into polished, professional report prose.",
        "Write like a strong equity research analyst: insight-first, crisp, and specific.",
        "Do not invent facts, numbers, management commentary, filing commentary, or industry claims beyond the provided payload.",
        "Do not output markdown tables. The application will render clean tables separately.",
        "Your prose must complement the tables rather than repeat every number already shown there.",
        "Keep the report sections interesting by explaining why the numbers matter, what drives the result, and where the analysis is fragile.",
    ]

    for skill_name in [
        "macro_industry_analysis",
        "qualitative_analysis",
        "quantitative_analysis",
        "valuation_analysis",
        "conclusion",
    ]:
        skill_text = skills.get(skill_name, "").strip()
        if skill_text:
            sections.append(f"{skill_name} guidance:\n{skill_text}")

    return "\n\n".join(sections)


def _build_parallel_writer_draft_input(context_bundle: DeepAgentContextResponse) -> str:
    payload = {
        "phase": "draft",
        "task": "Write the first three report sections from the shared context bundle.",
        "context": _model_to_dict(context_bundle),
        "sections_to_write": [
            "macro_industry_analysis",
            "qualitative_analysis",
            "quantitative_analysis",
        ],
    }
    return json.dumps(payload, indent=2)


def _build_parallel_writer_finalize_input(
    context_bundle: DeepAgentContextResponse,
    valuation_result: DeepAgentValuationWorkflowResponse,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
    notes: str,
) -> str:
    payload = {
        "phase": "finalize",
        "task": "Write the valuation section and final notes using the completed valuation result.",
        "context": _model_to_dict(context_bundle),
        "valuation_result": _model_to_dict(valuation_result),
        "valuation_output": _serialize_valuation_output(
            valuation_result.selected_model,
            valuation_output,
        ),
        "notes": notes,
        "sections_to_write": [
            "valuation_analysis",
            "notes",
            "valuation_table_intro",
        ],
    }
    return json.dumps(payload, indent=2)


def _build_parallel_valuation_user_prompt(
    context_bundle: DeepAgentContextResponse,
) -> str:
    payload = {
        "task": "Choose the valuation model, estimate the model inputs, call the valuation tool, and return the valuation result.",
        "context": _model_to_dict(context_bundle),
    }
    return json.dumps(payload, indent=2)


def _create_structured_deep_agent(
    *,
    name: str,
    model: str,
    system_prompt: str,
    response_format: Any,
    tools: list[Callable[..., Any]] | None = None,
) -> Any:
    if create_deep_agent is None:
        raise RuntimeError("LangChain Deep Agents is not installed.")

    return create_deep_agent(
        name=name,
        model=_normalize_langchain_model(model),
        system_prompt=system_prompt,
        tools=tools or [],
        response_format=response_format,
    )


def _extract_structured_response(result: Any) -> Any:
    structured_response = result.get("structured_response") if isinstance(result, dict) else None
    if structured_response is None:
        raise RuntimeError("Deep agent did not return a structured_response payload.")
    return structured_response


def _run_context_builder_agent(
    ticker: str,
    model: str,
    skills: dict[str, str],
) -> DeepAgentContextResponse:
    agent = _create_structured_deep_agent(
        name="context-builder",
        model=model,
        system_prompt=_build_context_builder_agent_prompt(skills),
        tools=[load_context_source_data],
        response_format=DeepAgentContextResponse,
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": _build_context_builder_user_prompt(ticker),
                }
            ]
        }
    )
    return _validate_structured_response(
        _extract_structured_response(result),
        DeepAgentContextResponse,
    )


def _run_parallel_valuation_agent(
    context_bundle: DeepAgentContextResponse,
    model: str,
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> DeepAgentValuationWorkflowResponse:
    agent = _create_structured_deep_agent(
        name="valuation-agent",
        model=model,
        system_prompt=_build_parallel_valuation_agent_prompt(
            dcf_skill_text,
            ddm_skill_text,
            rim_skill_text,
        ),
        tools=[
            list_available_valuation_models,
            run_dcf_valuation_tool,
            run_ddm_valuation_tool,
            run_rim_valuation_tool,
        ],
        response_format=DeepAgentValuationWorkflowResponse,
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": _build_parallel_valuation_user_prompt(context_bundle),
                }
            ]
        }
    )
    return _validate_structured_response(
        _extract_structured_response(result),
        DeepAgentValuationWorkflowResponse,
    )


def _run_parallel_writer_draft_agent(
    context_bundle: DeepAgentContextResponse,
    model: str,
    skills: dict[str, str],
) -> DeepAgentWriterDraftResponse:
    agent = _create_structured_deep_agent(
        name="writer",
        model=model,
        system_prompt=_build_parallel_writer_prompt(skills),
        response_format=DeepAgentWriterDraftResponse,
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": _build_parallel_writer_draft_input(context_bundle),
                }
            ]
        }
    )
    return _validate_structured_response(
        _extract_structured_response(result),
        DeepAgentWriterDraftResponse,
    )


def _run_parallel_writer_finalize_agent(
    context_bundle: DeepAgentContextResponse,
    valuation_result: DeepAgentValuationWorkflowResponse,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
    notes: str,
    model: str,
    skills: dict[str, str],
) -> DeepAgentWriterFinalizeResponse:
    agent = _create_structured_deep_agent(
        name="writer",
        model=model,
        system_prompt=_build_parallel_writer_prompt(skills),
        response_format=DeepAgentWriterFinalizeResponse,
    )
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": _build_parallel_writer_finalize_input(
                        context_bundle=context_bundle,
                        valuation_result=valuation_result,
                        valuation_output=valuation_output,
                        notes=notes,
                    ),
                }
            ]
        }
    )
    return _validate_structured_response(
        _extract_structured_response(result),
        DeepAgentWriterFinalizeResponse,
    )


def _build_data_collection_subagent_prompt() -> str:
    return "\n\n".join(
        [
            "You are the data collection specialist for an equity valuation workflow.",
            "Always begin by calling load_valuation_context for the requested ticker.",
            "Focus on the facts needed for valuation: company identity, sector, recent annual and quarterly financials, trend summary, market snapshot, and explicit missing-data notes.",
            "Return a concise plain-text memo for the supervisor.",
            "Do not estimate valuation assumptions and do not invent facts beyond tool output.",
        ]
    )


def _build_valuation_subagent_prompt(
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> str:
    sections = [
        "You are the valuation specialist for an equity valuation workflow.",
        "Confirm the currently available valuation model set by calling list_available_valuation_models with the ticker.",
        "Choose the best currently available model and justify the selection.",
        "If you are considering DCF, inspect the exact DCF seed with load_dcf_market_seed.",
        "If you are considering DDM, inspect the exact DDM seed with load_ddm_market_seed.",
        "If you are considering RIM, inspect the exact RIM seed with load_rim_market_seed.",
        "Estimate company-specific assumptions for the selected model using only the evidence provided by the supervisor and the tool outputs.",
        "Return decimals, not percentages. For example, use 0.08 for 8%.",
        "Do not calculate fair value yourself. The application will do the deterministic calculation after you finish.",
        "Return a concise plain-text memo that includes the selected model, the reasoning, and the exact assumptions.",
    ]
    if dcf_skill_text.strip():
        sections.append(f"{DCF_ASSUMPTION_SKILL_NAME} guidance:\n{dcf_skill_text.strip()}")
    if ddm_skill_text.strip():
        sections.append(f"{DDM_ASSUMPTION_SKILL_NAME} guidance:\n{ddm_skill_text.strip()}")
    if rim_skill_text.strip():
        sections.append(f"{RIM_ASSUMPTION_SKILL_NAME} guidance:\n{rim_skill_text.strip()}")
    return "\n\n".join(sections)


def _build_deep_agent_supervisor_prompt(
    skills: dict[str, str],
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> str:
    sections = [
        "You are the supervisor for an equity valuation workflow.",
        "You must coordinate the workflow in this order: collect data, choose the valuation model, estimate the model inputs, then return the final structured response.",
        "Delegate data gathering to the data-collector subagent before you finalize any analysis.",
        "Delegate model selection and valuation assumption work to the valuation-specialist subagent after data collection.",
        "Use only information returned by tools and subagents. Do not invent facts, management commentary, transcript content, SEC details, or valuation inputs.",
        "For macro_industry_analysis, qualitative_analysis, and quantitative_analysis, use the available evidence without explicitly calling out missing data inside those sections. Keep explicit limitations in notes when needed.",
        "Do not calculate fair value yourself. Your responsibility is to return the selected model, the reason, and validated model-specific assumptions. The application will compute fair value after your response.",
        "Write concise but useful section text.",
    ]

    for skill_name in CORE_ANALYSIS_KEYS:
        skill_text = skills.get(skill_name, "").strip()
        if skill_text:
            sections.append(f"{skill_name} guidance:\n{skill_text}")

    valuation_skill = skills.get("valuation_analysis", "").strip()
    if valuation_skill:
        sections.append(f"valuation_analysis guidance:\n{valuation_skill}")

    conclusion_skill = skills.get("conclusion", "").strip()
    if conclusion_skill:
        sections.append(f"conclusion guidance:\n{conclusion_skill}")

    if dcf_skill_text.strip():
        sections.append(f"{DCF_ASSUMPTION_SKILL_NAME} guidance:\n{dcf_skill_text.strip()}")
    if ddm_skill_text.strip():
        sections.append(f"{DDM_ASSUMPTION_SKILL_NAME} guidance:\n{ddm_skill_text.strip()}")
    if rim_skill_text.strip():
        sections.append(f"{RIM_ASSUMPTION_SKILL_NAME} guidance:\n{rim_skill_text.strip()}")

    return "\n\n".join(sections)


def _validate_deep_agent_payload(payload: Any) -> DeepAgentValuationResponse:
    if DeepAgentValuationResponse is None:
        raise RuntimeError("Deep agent response schema is unavailable.")

    if isinstance(payload, DeepAgentValuationResponse):
        return payload

    if hasattr(DeepAgentValuationResponse, "model_validate"):
        return DeepAgentValuationResponse.model_validate(payload)

    return DeepAgentValuationResponse.parse_obj(payload)


def _run_deep_agent_supervisor(
    ticker: str,
    model: str,
    skills: dict[str, str],
    dcf_skill_text: str,
    ddm_skill_text: str,
    rim_skill_text: str,
) -> DeepAgentValuationResponse:
    if not _deepagents_supported():
        raise RuntimeError(
            "LangChain Deep Agents dependencies are not installed. Install deepagents, langchain-openai, and pydantic."
        )

    subagents = [
        {
            "name": "data-collector",
            "description": "Collects the local company and market context required for valuation and returns a concise evidence summary.",
            "system_prompt": _build_data_collection_subagent_prompt(),
            "tools": [load_valuation_context],
        },
        {
            "name": "valuation-specialist",
            "description": "Chooses the best available valuation model and estimates company-specific valuation assumptions from the collected evidence.",
            "system_prompt": _build_valuation_subagent_prompt(
                dcf_skill_text,
                ddm_skill_text,
                rim_skill_text,
            ),
            "tools": [
                list_available_valuation_models,
                load_dcf_market_seed,
                load_ddm_market_seed,
                load_rim_market_seed,
            ],
        },
    ]

    agent = create_deep_agent(
        name="valuation-supervisor",
        model=_normalize_langchain_model(model),
        system_prompt=_build_deep_agent_supervisor_prompt(
            skills,
            dcf_skill_text,
            ddm_skill_text,
            rim_skill_text,
        ),
        subagents=subagents,
        response_format=DeepAgentValuationResponse,
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"Run the valuation workflow for ticker {ticker}. "
                        "Collect the necessary local data, choose the valuation model, "
                        "estimate the model inputs, and return the structured result."
                    ),
                }
            ]
        }
    )

    structured_response = result.get("structured_response") if isinstance(result, dict) else None
    if structured_response is None:
        raise RuntimeError("Deep agent did not return a structured_response payload.")

    return _validate_deep_agent_payload(structured_response)


def _summarize_valuation_result(
    selected_model: str | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
) -> str:
    if selected_model is None or valuation_output is None:
        return ""

    fair_value_per_share = getattr(valuation_output, "fair_value_per_share", None)
    current_price = getattr(valuation_output, "current_price", None)
    upside_downside_pct = getattr(valuation_output, "upside_downside_pct", None)
    fair_value_text = _format_currency_precise(fair_value_per_share) or "N/A"
    current_price_text = _format_currency_precise(current_price) or "N/A"
    upside_text = _format_percent(upside_downside_pct) or "N/A"
    return (
        f"Selected model: {selected_model.upper()}. "
        f"Estimated fair value per share is {fair_value_text} versus current price {current_price_text}, "
        f"implying {upside_text} upside/downside."
    )


def _serialize_assumptions_for_report(
    assumptions: DCFAssumptions | DDMAssumptions | RIMAssumptions | None,
) -> dict[str, Any]:
    if assumptions is None:
        return {}

    if isinstance(assumptions, DCFAssumptions):
        return {
            "selected_model": "dcf",
            "projection_years": assumptions.projection_years,
            "revenue_growth_rates": list(assumptions.revenue_growth_rates),
            "ebit_margins": list(assumptions.ebit_margins),
            "tax_rates": (
                list(assumptions.tax_rates)
                if isinstance(assumptions.tax_rates, list)
                else assumptions.tax_rates
            ),
            "da_as_pct_revenue": (
                list(assumptions.da_as_pct_revenue)
                if isinstance(assumptions.da_as_pct_revenue, list)
                else assumptions.da_as_pct_revenue
            ),
            "capex_as_pct_revenue": (
                list(assumptions.capex_as_pct_revenue)
                if isinstance(assumptions.capex_as_pct_revenue, list)
                else assumptions.capex_as_pct_revenue
            ),
            "nwc_as_pct_revenue": (
                list(assumptions.nwc_as_pct_revenue)
                if isinstance(assumptions.nwc_as_pct_revenue, list)
                else assumptions.nwc_as_pct_revenue
            ),
            "wacc": assumptions.wacc,
            "exit_multiple": assumptions.exit_multiple,
        }

    if isinstance(assumptions, DDMAssumptions):
        return {
            "selected_model": "ddm",
            "projection_years": assumptions.projection_years,
            "dividend_growth_rates": list(assumptions.dividend_growth_rates),
            "cost_of_equity": assumptions.cost_of_equity,
            "terminal_growth_rate": assumptions.terminal_growth_rate,
        }

    if isinstance(assumptions, RIMAssumptions):
        return {
            "selected_model": "rim",
            "projection_years": assumptions.projection_years,
            "return_on_equity": list(assumptions.return_on_equity),
            "payout_ratios": (
                list(assumptions.payout_ratios)
                if isinstance(assumptions.payout_ratios, list)
                else assumptions.payout_ratios
            ),
            "cost_of_equity": assumptions.cost_of_equity,
            "terminal_return_on_equity": assumptions.terminal_return_on_equity,
            "terminal_growth_rate": assumptions.terminal_growth_rate,
        }

    return {}


def _prepend_valuation_summary(
    valuation_analysis: str,
    selected_model: str | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
) -> str:
    summary = _summarize_valuation_result(selected_model, valuation_output)
    analysis = (valuation_analysis or "").strip()
    if summary and analysis:
        return f"{summary} {analysis}"
    return summary or analysis


def _build_writer_agent_prompt(skills: dict[str, str]) -> str:
    sections = [
        "You are the writer agent for the final AI equity report.",
        "Your job is to transform the provided structured analysis and valuation output into polished report sections.",
        "Do not invent facts, assumptions, or valuation figures beyond the provided payload.",
        "Use the computed valuation result exactly as provided.",
        "Keep each section concise, readable, and investment-report oriented.",
        "For macro_industry_analysis, qualitative_analysis, and quantitative_analysis, keep the writing focused on the available evidence and do not explicitly call out missing data inside those sections. Put explicit limitations in notes when needed.",
    ]

    for skill_name in [
        "macro_industry_analysis",
        "qualitative_analysis",
        "quantitative_analysis",
        "valuation_analysis",
        "conclusion",
    ]:
        skill_text = skills.get(skill_name, "").strip()
        if skill_text:
            sections.append(f"{skill_name} guidance:\n{skill_text}")

    return "\n\n".join(sections)


def _build_writer_agent_input(
    ticker: str,
    supervisor_response: DeepAgentValuationResponse,
    estimated_assumptions: DCFAssumptions | DDMAssumptions | RIMAssumptions | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
    notes: str,
) -> str:
    payload = {
        "task": "Format the final AI report from the collected analysis and valuation output.",
        "ticker": ticker,
        "selected_model": supervisor_response.selected_model,
        "model_selection_reason": supervisor_response.model_selection_reason,
        "draft_sections": {
            "macro_industry_analysis": supervisor_response.macro_industry_analysis,
            "qualitative_analysis": supervisor_response.qualitative_analysis,
            "quantitative_analysis": supervisor_response.quantitative_analysis,
            "valuation_analysis": supervisor_response.valuation_analysis,
            "notes": supervisor_response.notes,
        },
        "estimated_valuation_assumptions": _serialize_assumptions_for_report(
            estimated_assumptions
        ),
        "valuation_output": _serialize_valuation_output(
            supervisor_response.selected_model,
            valuation_output,
        ),
        "final_notes": notes,
    }
    return json.dumps(payload, indent=2)


def _validate_writer_payload(payload: Any) -> DeepAgentReportResponse:
    if DeepAgentReportResponse is None:
        raise RuntimeError("Writer response schema is unavailable.")

    if isinstance(payload, DeepAgentReportResponse):
        return payload

    if hasattr(DeepAgentReportResponse, "model_validate"):
        return DeepAgentReportResponse.model_validate(payload)

    return DeepAgentReportResponse.parse_obj(payload)


def _run_writer_agent(
    ticker: str,
    model: str,
    skills: dict[str, str],
    supervisor_response: DeepAgentValuationResponse,
    estimated_assumptions: DCFAssumptions | DDMAssumptions | RIMAssumptions | None,
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None,
    notes: str,
) -> DeepAgentReportResponse:
    if create_deep_agent is None or DeepAgentReportResponse is None:
        raise RuntimeError("Writer agent dependencies are unavailable.")

    writer_agent = create_deep_agent(
        name="writer",
        model=_normalize_langchain_model(model),
        system_prompt=_build_writer_agent_prompt(skills),
        response_format=DeepAgentReportResponse,
    )

    result = writer_agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": _build_writer_agent_input(
                        ticker=ticker,
                        supervisor_response=supervisor_response,
                        estimated_assumptions=estimated_assumptions,
                        valuation_output=valuation_output,
                        notes=notes,
                    ),
                }
            ]
        }
    )

    structured_response = result.get("structured_response") if isinstance(result, dict) else None
    if structured_response is None:
        raise RuntimeError("Writer agent did not return a structured_response payload.")

    return _validate_writer_payload(structured_response)


def _run_deep_agent(agent_input: AgentInput) -> AgentOutput:
    ticker = _normalize_ticker(agent_input.ticker)
    if not ticker:
        raise ValueError("AgentInput.ticker must be provided.")

    skills = {name: load_skill(name) for name in SKILL_NAMES}
    dcf_skill_text = load_skill(DCF_ASSUMPTION_SKILL_NAME)
    ddm_skill_text = load_skill(DDM_ASSUMPTION_SKILL_NAME)
    rim_skill_text = load_skill(RIM_ASSUMPTION_SKILL_NAME)
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    errors: list[str] = []
    context_bundle = _run_context_builder_agent(
        ticker=ticker,
        model=model,
        skills=skills,
    )

    valuation_result: DeepAgentValuationWorkflowResponse | None = None
    writer_draft: DeepAgentWriterDraftResponse | None = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        valuation_future = executor.submit(
            _run_parallel_valuation_agent,
            context_bundle,
            model,
            dcf_skill_text,
            ddm_skill_text,
            rim_skill_text,
        )
        writer_draft_future = executor.submit(
            _run_parallel_writer_draft_agent,
            context_bundle,
            model,
            skills,
        )

        try:
            valuation_result = valuation_future.result()
        except Exception as exc:
            errors.append(f"valuation agent failed: {exc}")

        try:
            writer_draft = writer_draft_future.result()
        except Exception as exc:
            errors.append(f"writer draft agent failed: {exc}")

    selected_model: str | None = None
    estimated_assumptions: DCFAssumptions | DDMAssumptions | RIMAssumptions | None = None
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None = None

    if valuation_result is not None:
        try:
            selected_model, estimated_assumptions = _valuation_from_deep_agent_response(
                valuation_result
            )
        except Exception as exc:
            errors.append(f"Estimated valuation assumptions were invalid: {exc}")

    if valuation_result is None:
        errors.append("Valuation output unavailable because the valuation agent failed.")
    elif estimated_assumptions is not None:
        try:
            valuation_output = _run_selected_valuation(
                ticker=ticker,
                selected_model=selected_model or valuation_result.selected_model,
                assumptions=estimated_assumptions,
            )
        except Exception as exc:
            errors.append(f"Valuation reconstruction failed: {exc}")

    notes = _merge_note_text(
        context_bundle.missing_data_notes,
        valuation_result.valuation_notes if valuation_result is not None else None,
        errors,
    )

    final_macro = (
        writer_draft.macro_industry_analysis
        if writer_draft is not None
        else context_bundle.context_summary
    )
    final_qualitative = (
        writer_draft.qualitative_analysis
        if writer_draft is not None
        else "Qualitative write-up unavailable because the writer draft step failed."
    )
    final_quantitative = (
        writer_draft.quantitative_analysis
        if writer_draft is not None
        else "Quantitative write-up unavailable because the writer draft step failed."
    )
    final_valuation_analysis = (
        valuation_result.valuation_summary
        if valuation_result is not None
        else "Valuation analysis unavailable because the valuation step did not complete."
    )
    final_notes = notes

    if valuation_result is not None:
        try:
            writer_finalize = _run_parallel_writer_finalize_agent(
                context_bundle=context_bundle,
                valuation_result=valuation_result,
                valuation_output=valuation_output,
                notes=notes,
                model=model,
                skills=skills,
            )
            final_valuation_analysis = "\n\n".join(
                [
                    text
                    for text in [
                        writer_finalize.valuation_table_intro.strip(),
                        writer_finalize.valuation_analysis.strip(),
                    ]
                    if text
                ]
            )
            final_notes = _merge_note_text(writer_finalize.notes, notes)
        except Exception as exc:
            final_valuation_analysis = _prepend_valuation_summary(
                valuation_result.valuation_summary,
                selected_model,
                valuation_output,
            )
            final_notes = _merge_note_text(
                notes,
                f"Writer finalize step failed, so the valuation section used the valuation agent summary instead: {exc}",
            )
    else:
        final_valuation_analysis = _prepend_valuation_summary(
            final_valuation_analysis,
            selected_model,
            valuation_output,
        )

    return AgentOutput(
        ticker=ticker,
        macro_industry_analysis=final_macro,
        qualitative_analysis=final_qualitative,
        quantitative_analysis=final_quantitative,
        selected_model=(
            selected_model if selected_model is not None else (
                valuation_result.selected_model if valuation_result is not None else None
            )
        ),
        model_selection_reason=(
            valuation_result.model_selection_reason
            if valuation_result is not None
            else None
        ),
        estimated_dcf_assumptions=(
            estimated_assumptions if isinstance(estimated_assumptions, DCFAssumptions) else None
        ),
        estimated_ddm_assumptions=(
            estimated_assumptions if isinstance(estimated_assumptions, DDMAssumptions) else None
        ),
        estimated_rim_assumptions=(
            estimated_assumptions if isinstance(estimated_assumptions, RIMAssumptions) else None
        ),
        valuation_analysis=final_valuation_analysis,
        notes=final_notes,
        dcf_output=valuation_output if isinstance(valuation_output, DCFOutput) else None,
        ddm_output=valuation_output if isinstance(valuation_output, DDMOutput) else None,
        rim_output=valuation_output if isinstance(valuation_output, RIMOutput) else None,
    )


def _run_legacy_agent(agent_input: AgentInput) -> AgentOutput:
    """Run the agent workflow using OpenAI plus local app tools."""
    ticker = _normalize_ticker(agent_input.ticker)
    if not ticker:
        raise ValueError("AgentInput.ticker must be provided.")

    errors: list[str] = []
    skills = {name: load_skill(name) for name in SKILL_NAMES}
    dcf_skill_text = load_skill(DCF_ASSUMPTION_SKILL_NAME)
    ddm_skill_text = load_skill(DDM_ASSUMPTION_SKILL_NAME)
    rim_skill_text = load_skill(RIM_ASSUMPTION_SKILL_NAME)

    company_info = _safe_tool_call(
        load_company_info,
        ticker,
        default=None,
        errors=errors,
        label="company info load",
    )
    market_snapshot = _safe_tool_call(
        load_market_snapshot,
        ticker,
        default=None,
        errors=errors,
        label="market snapshot load",
    )
    annual_financials = _safe_tool_call(
        load_annual_financials,
        ticker,
        default=[],
        errors=errors,
        label="annual financial load",
    )
    quarterly_financials = _safe_tool_call(
        load_quarterly_financials,
        ticker,
        default=[],
        errors=errors,
        label="quarterly financial load",
    )

    base_market_context = _prepare_market_context(
        ticker=ticker,
        company_info=company_info,
        market_snapshot=market_snapshot,
        annual_financials=annual_financials,
        quarterly_financials=quarterly_financials,
        selected_model=None,
        valuation_output=None,
        errors=errors,
        include_valuation_context=False,
    )

    client = _get_openai_client()
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    core_analysis = _generate_core_analysis(
        client=client,
        model=model,
        ticker=ticker,
        context=base_market_context,
        skills=skills,
    )

    selected_model: str | None = None
    model_selection_reason: str | None = None
    estimated_assumptions: DCFAssumptions | DDMAssumptions | RIMAssumptions | None = None
    valuation_output: DCFOutput | DDMOutput | RIMOutput | None = None

    try:
        selection = _select_valuation_model(
            client=client,
            model=model,
            ticker=ticker,
            market_context=base_market_context,
            dcf_skill_text=dcf_skill_text,
            ddm_skill_text=ddm_skill_text,
            rim_skill_text=rim_skill_text,
        )
        selected_model = selection["selected_model"]
        model_selection_reason = selection["model_selection_reason"]
    except Exception as exc:
        errors.append(f"Valuation model selection failed: {exc}")

    if selected_model is not None:
        try:
            if selected_model == "dcf":
                estimated_assumptions = _estimate_dcf_assumptions(
                    client=client,
                    model=model,
                    ticker=ticker,
                    market_context=base_market_context,
                    dcf_skill_text=dcf_skill_text,
                )
            elif selected_model == "ddm":
                estimated_assumptions = _estimate_ddm_assumptions(
                    client=client,
                    model=model,
                    ticker=ticker,
                    market_context=base_market_context,
                    ddm_skill_text=ddm_skill_text,
                )
            elif selected_model == "rim":
                estimated_assumptions = _estimate_rim_assumptions(
                    client=client,
                    model=model,
                    ticker=ticker,
                    market_context=base_market_context,
                    rim_skill_text=rim_skill_text,
                )
        except Exception as exc:
            errors.append(
                f"{selected_model.upper()} assumption estimation failed: {exc}"
            )

    if selected_model is not None and estimated_assumptions is not None:
        try:
            valuation_output = _run_selected_valuation(
                ticker=ticker,
                selected_model=selected_model,
                assumptions=estimated_assumptions,
            )
        except Exception as exc:
            errors.append(f"{selected_model.upper()} valuation failed: {exc}")

    final_market_context = _prepare_market_context(
        ticker=ticker,
        company_info=company_info,
        market_snapshot=market_snapshot,
        annual_financials=annual_financials,
        quarterly_financials=quarterly_financials,
        selected_model=selected_model,
        valuation_output=valuation_output,
        errors=errors,
    )

    instructions = _build_final_report_instruction_block(skills)
    user_prompt = _build_final_report_prompt(
        ticker=ticker,
        context=final_market_context,
        core_analysis=core_analysis,
    )
    raw_json = _call_model(
        client=client,
        model=model,
        instructions=instructions,
        user_prompt=user_prompt,
        schema_name="agent_analysis",
        schema=_final_report_json_schema(),
    )

    final_report = _parse_final_report_output(raw_json)
    return AgentOutput(
        ticker=ticker,
        macro_industry_analysis=core_analysis["macro_industry_analysis"],
        qualitative_analysis=core_analysis["qualitative_analysis"],
        quantitative_analysis=core_analysis["quantitative_analysis"],
        selected_model=selected_model,
        model_selection_reason=model_selection_reason,
        estimated_dcf_assumptions=(
            estimated_assumptions if isinstance(estimated_assumptions, DCFAssumptions) else None
        ),
        estimated_ddm_assumptions=(
            estimated_assumptions if isinstance(estimated_assumptions, DDMAssumptions) else None
        ),
        estimated_rim_assumptions=(
            estimated_assumptions if isinstance(estimated_assumptions, RIMAssumptions) else None
        ),
        valuation_analysis=final_report["valuation_analysis"],
        notes=final_report["notes"],
        dcf_output=valuation_output if isinstance(valuation_output, DCFOutput) else None,
        ddm_output=valuation_output if isinstance(valuation_output, DDMOutput) else None,
        rim_output=valuation_output if isinstance(valuation_output, RIMOutput) else None,
    )


def run_agent(agent_input: AgentInput) -> AgentOutput:
    """Run the preferred deep-agent workflow and fall back to the legacy flow if needed."""
    preferred_backend = os.getenv("AGENT_BACKEND", "deepagents").strip().lower()
    if preferred_backend != "legacy" and _deepagents_supported():
        return _run_deep_agent(agent_input)

    output = _run_legacy_agent(agent_input)
    if preferred_backend != "legacy":
        output.notes = _merge_note_text(
            output.notes,
            "LangChain Deep Agents dependencies were unavailable, so the app used the legacy single-shot workflow instead.",
        )
    return output
