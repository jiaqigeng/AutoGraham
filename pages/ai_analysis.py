from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from agent.schemas import AgentInput, AgentOutput
from agent.service import run_agent
from valuation.ddm.schemas import DDMOutput
from valuation.dcf.schemas import DCFOutput
from valuation.rim.schemas import RIMOutput


st.set_page_config(page_title="AI Analysis", layout="wide")


def _clean_section_text(content: str | None) -> str:
    if not content:
        return ""

    cleaned = content.strip().replace("\r\n", "\n")
    cleaned = cleaned.replace("**", "").replace("*", "").replace("`", "")
    cleaned = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", cleaned)
    cleaned = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", cleaned)
    cleaned = re.sub(r"(?<=[A-Za-z])(?=\()", " ", cleaned)
    cleaned = re.sub(r"(?<=\))(?=[A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"(?<=[,;:])(?=\S)", " ", cleaned)
    cleaned = re.sub(r"(?<=[.!?])(?=[A-Za-z])", " ", cleaned)
    cleaned = re.sub(r"(?<=\w)→(?=\w)", " → ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _display_section(title: str, content: str | None) -> None:
    st.subheader(title)
    cleaned = _clean_section_text(content)

    if cleaned:
        escaped = html.escape(cleaned).replace("\n", "<br>")
        st.markdown(
            (
                "<div style='white-space: pre-wrap; line-height: 1.65;'>"
                f"{escaped}"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
    else:
        st.caption("No analysis available.")


def _format_currency(value: float | None) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def _format_multiple(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}x"


def _display_table(title: str, rows: list[dict[str, str | int | float]]) -> None:
    if not rows:
        return

    st.caption(title)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _series_value(values: float | list[float], index: int) -> float:
    if isinstance(values, list):
        return values[index]
    return values


def _build_dcf_summary_rows(dcf_output: DCFOutput) -> list[dict[str, str]]:
    assumptions = dcf_output.assumptions_used
    return [
        {"Metric": "Fair Value / Share", "Value": _format_currency(dcf_output.fair_value_per_share)},
        {"Metric": "Current Price", "Value": _format_currency(dcf_output.current_price)},
        {"Metric": "Upside / Downside", "Value": _format_percent(dcf_output.upside_downside_pct)},
        {"Metric": "Enterprise Value", "Value": _format_currency(dcf_output.enterprise_value)},
        {"Metric": "Equity Value", "Value": _format_currency(dcf_output.equity_value)},
        {"Metric": "PV of Projected FCFF", "Value": _format_currency(dcf_output.pv_of_projected_fcff)},
        {"Metric": "PV of Terminal Value", "Value": _format_currency(dcf_output.present_value_terminal_value)},
        {"Metric": "Terminal Value", "Value": _format_currency(dcf_output.terminal_value)},
        {
            "Metric": "Terminal Value % of EV",
            "Value": _format_percent(dcf_output.terminal_value_pct_of_enterprise_value),
        },
        {"Metric": "Terminal EBITDA", "Value": _format_currency(dcf_output.terminal_ebitda)},
        {"Metric": "Exit Multiple", "Value": _format_multiple(dcf_output.exit_multiple)},
        {
            "Metric": "WACC",
            "Value": _format_percent(assumptions.wacc if assumptions else None),
        },
        {
            "Metric": "Projection Years",
            "Value": str(len(dcf_output.projected_years)),
        },
    ]


def _build_dcf_assumption_rows(dcf_output: DCFOutput) -> list[dict[str, str | int]]:
    assumptions = dcf_output.assumptions_used
    if assumptions is None:
        return []

    return [
        {
            "Year": index + 1,
            "Revenue Growth": _format_percent(assumptions.revenue_growth_rates[index]),
            "EBIT Margin": _format_percent(assumptions.ebit_margins[index]),
            "Tax Rate": _format_percent(_series_value(assumptions.tax_rates, index)),
            "D&A % Revenue": _format_percent(
                _series_value(assumptions.da_as_pct_revenue, index)
            ),
            "Capex % Revenue": _format_percent(
                _series_value(assumptions.capex_as_pct_revenue, index)
            ),
            "NWC % Revenue": _format_percent(
                _series_value(assumptions.nwc_as_pct_revenue, index)
            ),
        }
        for index in range(assumptions.projection_years)
    ]


def _build_dcf_projection_rows(dcf_output: DCFOutput) -> list[dict[str, str | int]]:
    return [
        {
            "Year": year.year,
            "Revenue": _format_currency(year.revenue),
            "EBIT": _format_currency(year.ebit),
            "EBIT Margin": _format_percent(year.ebit_margin),
            "Taxes": _format_currency(year.taxes),
            "NOPAT": _format_currency(year.nopat),
            "D&A": _format_currency(year.depreciation_amortization),
            "EBITDA": _format_currency(year.ebitda),
            "Capex": _format_currency(year.capex),
            "Change in NWC": _format_currency(year.change_in_nwc),
            "FCFF": _format_currency(year.fcff),
            "Discount Factor": f"{year.discount_factor:.4f}",
            "PV of FCFF": _format_currency(year.present_value_fcff),
        }
        for year in dcf_output.projected_years
    ]


def _build_ddm_summary_rows(ddm_output: DDMOutput) -> list[dict[str, str]]:
    assumptions = ddm_output.assumptions_used
    return [
        {"Metric": "Fair Value / Share", "Value": _format_currency(ddm_output.fair_value_per_share)},
        {"Metric": "Current Price", "Value": _format_currency(ddm_output.current_price)},
        {"Metric": "Upside / Downside", "Value": _format_percent(ddm_output.upside_downside_pct)},
        {"Metric": "Equity Value", "Value": _format_currency(ddm_output.equity_value)},
        {"Metric": "PV of Projected Dividends", "Value": _format_currency(ddm_output.pv_of_projected_dividends)},
        {"Metric": "PV of Terminal Value", "Value": _format_currency(ddm_output.present_value_terminal_value)},
        {"Metric": "Terminal Value / Share", "Value": _format_currency(ddm_output.terminal_value_per_share)},
        {"Metric": "Terminal Dividend / Share", "Value": _format_currency(ddm_output.terminal_dividend_per_share)},
        {
            "Metric": "Terminal Value % of Fair Value",
            "Value": _format_percent(ddm_output.terminal_value_pct_of_fair_value),
        },
        {
            "Metric": "Cost of Equity",
            "Value": _format_percent(assumptions.cost_of_equity if assumptions else None),
        },
        {
            "Metric": "Projection Years",
            "Value": str(len(ddm_output.projected_years)),
        },
    ]


def _build_ddm_assumption_rows(ddm_output: DDMOutput) -> list[dict[str, str | int]]:
    assumptions = ddm_output.assumptions_used
    if assumptions is None:
        return []

    return [
        {
            "Year": index + 1,
            "Dividend Growth": _format_percent(assumptions.dividend_growth_rates[index]),
        }
        for index in range(assumptions.projection_years)
    ]


def _build_ddm_projection_rows(ddm_output: DDMOutput) -> list[dict[str, str | int]]:
    return [
        {
            "Year": year.year,
            "Dividend / Share": _format_currency(year.dividend_per_share),
            "Growth Rate": _format_percent(year.growth_rate),
            "Discount Factor": f"{year.discount_factor:.4f}",
            "PV of Dividend": _format_currency(year.present_value_dividend),
        }
        for year in ddm_output.projected_years
    ]


def _build_rim_summary_rows(rim_output: RIMOutput) -> list[dict[str, str]]:
    assumptions = rim_output.assumptions_used
    return [
        {"Metric": "Fair Value / Share", "Value": _format_currency(rim_output.fair_value_per_share)},
        {"Metric": "Current Price", "Value": _format_currency(rim_output.current_price)},
        {"Metric": "Upside / Downside", "Value": _format_percent(rim_output.upside_downside_pct)},
        {"Metric": "Equity Value", "Value": _format_currency(rim_output.equity_value)},
        {"Metric": "PV of Projected Residual Income", "Value": _format_currency(rim_output.pv_of_projected_residual_income)},
        {"Metric": "PV of Terminal Value", "Value": _format_currency(rim_output.present_value_terminal_value)},
        {"Metric": "Terminal Value / Share", "Value": _format_currency(rim_output.terminal_value_per_share)},
        {"Metric": "Terminal Book Value / Share", "Value": _format_currency(rim_output.terminal_book_value_per_share)},
        {"Metric": "Terminal Residual Income / Share", "Value": _format_currency(rim_output.terminal_residual_income_per_share)},
        {
            "Metric": "Terminal Value % of Fair Value",
            "Value": _format_percent(rim_output.terminal_value_pct_of_fair_value),
        },
        {
            "Metric": "Cost of Equity",
            "Value": _format_percent(assumptions.cost_of_equity if assumptions else None),
        },
        {
            "Metric": "Projection Years",
            "Value": str(len(rim_output.projected_years)),
        },
    ]


def _build_rim_assumption_rows(rim_output: RIMOutput) -> list[dict[str, str | int]]:
    assumptions = rim_output.assumptions_used
    if assumptions is None:
        return []

    return [
        {
            "Year": index + 1,
            "ROE": _format_percent(assumptions.return_on_equity[index]),
            "Payout Ratio": _format_percent(_series_value(assumptions.payout_ratios, index)),
        }
        for index in range(assumptions.projection_years)
    ]


def _build_rim_projection_rows(rim_output: RIMOutput) -> list[dict[str, str | int]]:
    return [
        {
            "Year": year.year,
            "Beginning BVPS": _format_currency(year.beginning_book_value_per_share),
            "Ending BVPS": _format_currency(year.ending_book_value_per_share),
            "ROE": _format_percent(year.return_on_equity),
            "EPS": _format_currency(year.earnings_per_share),
            "Payout Ratio": _format_percent(year.payout_ratio),
            "Dividend / Share": _format_currency(year.dividends_per_share),
            "Retained Earnings / Share": _format_currency(year.retained_earnings_per_share),
            "Residual Income / Share": _format_currency(year.residual_income_per_share),
            "Discount Factor": f"{year.discount_factor:.4f}",
            "PV of Residual Income": _format_currency(year.present_value_residual_income),
        }
        for year in rim_output.projected_years
    ]


def _display_valuation_section(output: AgentOutput) -> None:
    if output.selected_model:
        st.caption(f"Selected Model: {str(output.selected_model).upper()}")
    if output.model_selection_reason:
        st.write(output.model_selection_reason)

    _display_section("Valuation Analysis", output.valuation_analysis)

    if output.dcf_output is not None:
        _display_table("Valuation Summary", _build_dcf_summary_rows(output.dcf_output))
        _display_table("DCF Assumptions by Year", _build_dcf_assumption_rows(output.dcf_output))
        _display_table("DCF Projections by Year", _build_dcf_projection_rows(output.dcf_output))
        return

    if output.ddm_output is not None:
        _display_table("Valuation Summary", _build_ddm_summary_rows(output.ddm_output))
        _display_table("DDM Assumptions by Year", _build_ddm_assumption_rows(output.ddm_output))
        _display_table("DDM Projections by Year", _build_ddm_projection_rows(output.ddm_output))
        return

    if output.rim_output is not None:
        _display_table("Valuation Summary", _build_rim_summary_rows(output.rim_output))
        _display_table("RIM Assumptions by Year", _build_rim_assumption_rows(output.rim_output))
        _display_table("RIM Projections by Year", _build_rim_projection_rows(output.rim_output))
        return

    st.caption("No structured valuation output available.")


st.title("AI Analysis")
st.write("Run the agent for a ticker and review the structured analysis output.")

ticker = st.text_input("Ticker", value="AAPL").strip().upper()
run_clicked = st.button("Run AI Analysis", type="primary")


if "ai_analysis_output" not in st.session_state:
    st.session_state.ai_analysis_output = None
if "ai_analysis_error" not in st.session_state:
    st.session_state.ai_analysis_error = None


if run_clicked:
    if not ticker:
        st.warning("Please enter a ticker symbol.")
    else:
        try:
            agent_input = AgentInput(ticker=ticker)
            st.session_state.ai_analysis_output = run_agent(agent_input)
            st.session_state.ai_analysis_error = None

        except Exception as exc:
            st.session_state.ai_analysis_output = None
            st.session_state.ai_analysis_error = str(exc)


if st.session_state.ai_analysis_error:
    st.error(f"Failed to run AI analysis for {ticker}: {st.session_state.ai_analysis_error}")


if st.session_state.ai_analysis_output is not None:
    output = st.session_state.ai_analysis_output

    st.success(f"AI analysis completed for {output.ticker}.")
    st.caption(f"Structured analysis for {output.ticker}")

    _display_section("Macro / Industry Analysis", output.macro_industry_analysis)
    _display_section("Qualitative Analysis", output.qualitative_analysis)
    _display_section("Quantitative Analysis", output.quantitative_analysis)
    _display_valuation_section(output)
    _display_section("Notes", output.notes)
