from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from data.market.schemas import FinancialPeriod, MarketDataBundle
from data.market.service import get_market_data_bundle
from valuation.dcf.schemas import DCFAssumptions, DCFInput, DCFMarketData, DCFOutput
from valuation.dcf.service import run_dcf_valuation
from valuation.ddm.schemas import DDMAssumptions, DDMInput, DDMMarketData, DDMOutput
from valuation.ddm.service import run_ddm_valuation
from valuation.rim.schemas import RIMAssumptions, RIMInput, RIMMarketData, RIMOutput
from valuation.rim.service import run_rim_valuation


st.set_page_config(page_title="Valuation Calculators", layout="wide")


MODEL_OPTIONS = ("DCF", "DDM", "RIM")


@dataclass(slots=True)
class DerivedValue:
    label: str
    value: float
    source: str
    kind: str = "currency"


def _sort_periods(periods: list[FinancialPeriod]) -> list[FinancialPeriod]:
    return sorted(periods, key=lambda period: period.period_end)


def _latest_value(
    periods: list[FinancialPeriod],
    extractor,
) -> tuple[float | None, FinancialPeriod | None]:
    for period in reversed(_sort_periods(periods)):
        value = extractor(period)
        if value is not None:
            return float(value), period
    return None, None


def _ebit_like(period: FinancialPeriod) -> float | None:
    if period.ebit is not None:
        return period.ebit
    return period.operating_income


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def _period_source(period: FinancialPeriod | None) -> str:
    if period is None:
        return "N/A"
    if period.period_type == "quarterly" and period.fiscal_quarter is not None:
        return f"FY{period.fiscal_year} Q{period.fiscal_quarter}"
    return f"FY{period.fiscal_year or period.period_end.year}"


def _format_currency(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def _format_currency_compact(value: float | None) -> str:
    if value is None:
        return "N/A"

    absolute_value = abs(value)
    scaled_value = value
    suffix = ""

    if absolute_value >= 1_000_000_000_000:
        scaled_value = value / 1_000_000_000_000
        suffix = "T"
    elif absolute_value >= 1_000_000_000:
        scaled_value = value / 1_000_000_000
        suffix = "B"
    elif absolute_value >= 1_000_000:
        scaled_value = value / 1_000_000
        suffix = "M"

    return f"${scaled_value:,.2f}{suffix}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def _format_multiple(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}x"


def _current_price(bundle: MarketDataBundle) -> float | None:
    snapshot = bundle.market_snapshot
    if snapshot is None:
        return None
    return snapshot.current_price


def _shares_outstanding(bundle: MarketDataBundle) -> DerivedValue | None:
    snapshot = bundle.market_snapshot
    if snapshot is not None and snapshot.shares_outstanding is not None:
        return DerivedValue(
            label="Shares Outstanding",
            value=float(snapshot.shares_outstanding),
            source="Market snapshot",
            kind="count",
        )

    value, period = _latest_value(bundle.annual_financials, lambda item: item.shares_outstanding)
    if value is None:
        value, period = _latest_value(bundle.quarterly_financials, lambda item: item.shares_outstanding)
    if value is None:
        return None

    return DerivedValue(
        label="Shares Outstanding",
        value=value,
        source=_period_source(period),
        kind="count",
    )


def _format_display_value(item: DerivedValue) -> str:
    if item.kind == "count":
        return f"{item.value:,.0f}"
    return _format_currency(item.value)


def _build_display_frame(values: list[DerivedValue]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Field": item.label, "Value": _format_display_value(item), "Source": item.source}
            for item in values
        ]
    )


def _growth_series(periods: list[FinancialPeriod], extractor) -> list[float]:
    sorted_periods = _sort_periods(periods)
    values: list[float] = []

    for period in sorted_periods:
        value = extractor(period)
        if value is None:
            continue
        values.append(float(value))

    growth_rates: list[float] = []
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        if previous == 0:
            continue
        growth_rates.append((current - previous) / abs(previous))

    return growth_rates


def _fade_series(start: float, end: float, years: int) -> list[float]:
    if years <= 1:
        return [start]

    return [
        start + ((end - start) * index / (years - 1))
        for index in range(years)
    ]


def _recent_growth_or_default(growth_rates: list[float], fallback: float) -> float:
    if growth_rates:
        return growth_rates[-1]
    return fallback


def _cost_of_equity_from_beta(bundle: MarketDataBundle) -> float:
    snapshot = bundle.market_snapshot
    beta = snapshot.beta if snapshot else None
    if beta is None:
        return 0.09
    return _clamp(0.045 + (float(beta) * 0.05), 0.07, 0.14)


def _display_header(bundle: MarketDataBundle) -> None:
    company_info = bundle.company_info
    snapshot = bundle.market_snapshot

    if company_info is None:
        st.title("Valuation Calculators")
        return

    name = company_info.company_name or company_info.ticker
    st.title(f"{name} ({company_info.ticker})")

    descriptors = [company_info.sector, company_info.industry, company_info.exchange]
    st.caption(" | ".join(part for part in descriptors if part))

    metrics = st.columns(4)
    metrics[0].metric("Current Price", _format_currency(snapshot.current_price if snapshot else None))
    metrics[1].metric("Market Cap", _format_currency_compact(snapshot.market_cap if snapshot else None))
    metrics[2].metric(
        "Enterprise Value",
        _format_currency_compact(snapshot.enterprise_value if snapshot else None),
    )
    metrics[3].metric(
        "Shares Outstanding",
        f"{(snapshot.shares_outstanding or 0) / 1_000_000_000:,.2f}B" if snapshot and snapshot.shares_outstanding else "N/A",
    )


def _derive_dcf_defaults(bundle: MarketDataBundle) -> tuple[DCFMarketData, dict[str, object], pd.DataFrame]:
    annual_periods = bundle.annual_financials

    revenue_value, revenue_period = _latest_value(annual_periods, lambda item: item.revenue)
    ebit_value, ebit_period = _latest_value(annual_periods, _ebit_like)
    cash_value, cash_period = _latest_value(annual_periods, lambda item: item.cash)
    debt_value, debt_period = _latest_value(annual_periods, lambda item: item.total_debt)
    da_value, da_period = _latest_value(annual_periods, lambda item: item.depreciation_amortization)
    capex_value, capex_period = _latest_value(annual_periods, lambda item: abs(item.capex) if item.capex is not None else None)
    nwc_value, nwc_period = _latest_value(annual_periods, lambda item: item.change_in_nwc)
    tax_rate_value, _ = _latest_value(
        annual_periods,
        lambda item: _safe_ratio(item.income_tax_expense, _ebit_like(item)),
    )
    shares = _shares_outstanding(bundle)
    current_price = _current_price(bundle)

    missing_fields: list[str] = []
    if revenue_value is None:
        missing_fields.append("current revenue")
    if ebit_value is None:
        missing_fields.append("current EBIT")
    if cash_value is None:
        missing_fields.append("cash")
    if debt_value is None:
        missing_fields.append("total debt")
    if da_value is None:
        missing_fields.append("depreciation & amortization")
    if capex_value is None:
        missing_fields.append("capex")
    if nwc_value is None:
        missing_fields.append("change in working capital")
    if tax_rate_value is None:
        missing_fields.append("tax rate")
    if shares is None:
        missing_fields.append("shares outstanding")
    if current_price is None:
        missing_fields.append("current price")

    if missing_fields:
        raise ValueError(
            "Missing auto-loaded DCF inputs: " + ", ".join(missing_fields) + "."
        )

    revenue_growth = _clamp(
        _recent_growth_or_default(_growth_series(annual_periods, lambda item: item.revenue), 0.08),
        -0.20,
        0.25,
    )
    terminal_growth_anchor = 0.03
    ebit_margin = _clamp((ebit_value or 0.0) / (revenue_value or 1.0), -0.20, 0.50)
    tax_rate = _clamp(tax_rate_value or 0.21, 0.05, 0.35)
    da_rate = _clamp((da_value or 0.0) / (revenue_value or 1.0), 0.0, 0.15)
    capex_rate = _clamp((capex_value or 0.0) / (revenue_value or 1.0), 0.0, 0.20)
    nwc_rate = _clamp((nwc_value or 0.0) / (revenue_value or 1.0), -0.10, 0.10)
    wacc = _clamp(_cost_of_equity_from_beta(bundle) - 0.01, 0.07, 0.13)

    latest_ebitda = (ebit_value or 0.0) + (da_value or 0.0)
    snapshot = bundle.market_snapshot
    if snapshot and snapshot.enterprise_value not in (None, 0) and latest_ebitda > 0:
        exit_multiple = _clamp(snapshot.enterprise_value / latest_ebitda, 6.0, 20.0)
    else:
        exit_multiple = 12.0

    market_data = DCFMarketData(
        current_revenue=revenue_value,
        current_ebit=ebit_value,
        tax_rate=tax_rate,
        depreciation_amortization=da_value,
        capex=capex_value,
        change_in_nwc=nwc_value,
        cash=cash_value,
        total_debt=debt_value,
        shares_outstanding=shares.value,
        current_price=current_price,
    )

    base_values = [
        DerivedValue("Current Revenue", revenue_value, _period_source(revenue_period)),
        DerivedValue("Current EBIT", ebit_value, _period_source(ebit_period)),
        DerivedValue("Cash", cash_value, _period_source(cash_period)),
        DerivedValue("Total Debt", debt_value, _period_source(debt_period)),
        DerivedValue("Depreciation & Amortization", da_value, _period_source(da_period)),
        DerivedValue("Capex", capex_value, _period_source(capex_period)),
        DerivedValue("Change in NWC", nwc_value, _period_source(nwc_period)),
        DerivedValue("Shares Outstanding", shares.value, shares.source),
        DerivedValue("Current Price", current_price, "Market snapshot"),
    ]

    assumptions_frame = pd.DataFrame(
        [
            {
                "Year": year + 1,
                "Revenue Growth (%)": value * 100,
                "EBIT Margin (%)": ebit_margin * 100,
                "Tax Rate (%)": tax_rate * 100,
                "D&A / Revenue (%)": da_rate * 100,
                "Capex / Revenue (%)": capex_rate * 100,
                "Change in NWC / Revenue (%)": nwc_rate * 100,
            }
            for year, value in enumerate(_fade_series(revenue_growth, terminal_growth_anchor, 5))
        ]
    )

    return (
        market_data,
        {
            "base_values": base_values,
            "default_projection_years": 5,
            "default_wacc": wacc,
            "default_exit_multiple": exit_multiple,
        },
        assumptions_frame,
    )


def _current_dividend_per_share(bundle: MarketDataBundle) -> DerivedValue | None:
    shares = _shares_outstanding(bundle)
    dividend_paid, dividend_period = _latest_value(
        bundle.annual_financials,
        lambda item: abs(item.dividends_paid) if item.dividends_paid is not None else None,
    )
    if shares is not None and dividend_paid is not None and shares.value > 0:
        return DerivedValue(
            label="Current Dividend / Share",
            value=dividend_paid / shares.value,
            source=_period_source(dividend_period),
        )

    snapshot = bundle.market_snapshot
    current_price = _current_price(bundle)
    if snapshot and snapshot.dividend_yield is not None and current_price is not None:
        return DerivedValue(
            label="Current Dividend / Share",
            value=current_price * (float(snapshot.dividend_yield) / 100),
            source="Market snapshot dividend yield",
        )

    return None


def _dividend_per_share_growth_series(bundle: MarketDataBundle) -> list[float]:
    sorted_periods = _sort_periods(bundle.annual_financials)
    values: list[float] = []

    for period in sorted_periods:
        if period.dividends_paid is None:
            continue
        shares = period.shares_outstanding
        if shares in (None, 0):
            continue
        values.append(abs(period.dividends_paid) / shares)

    growth_rates: list[float] = []
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        if previous == 0:
            continue
        growth_rates.append((current - previous) / previous)

    return growth_rates


def _derive_ddm_defaults(bundle: MarketDataBundle) -> tuple[DDMMarketData, dict[str, object], pd.DataFrame]:
    dividend_per_share = _current_dividend_per_share(bundle)
    shares = _shares_outstanding(bundle)
    current_price = _current_price(bundle)

    missing_fields: list[str] = []
    if dividend_per_share is None:
        missing_fields.append("current dividend per share")
    if shares is None:
        missing_fields.append("shares outstanding")
    if current_price is None:
        missing_fields.append("current price")

    if missing_fields:
        raise ValueError(
            "Missing auto-loaded DDM inputs: " + ", ".join(missing_fields) + "."
        )

    cost_of_equity = _cost_of_equity_from_beta(bundle)
    terminal_growth_rate = min(0.03, cost_of_equity - 0.01)
    dividend_growth = _clamp(
        _recent_growth_or_default(_dividend_per_share_growth_series(bundle), 0.05),
        -0.10,
        0.18,
    )

    market_data = DDMMarketData(
        current_dividend_per_share=dividend_per_share.value,
        shares_outstanding=shares.value,
        current_price=current_price,
    )

    base_values = [
        DerivedValue("Current Dividend / Share", dividend_per_share.value, dividend_per_share.source),
        DerivedValue("Shares Outstanding", shares.value, shares.source),
        DerivedValue("Current Price", current_price, "Market snapshot"),
    ]

    assumptions_frame = pd.DataFrame(
        [
            {
                "Year": year + 1,
                "Dividend Growth (%)": value * 100,
            }
            for year, value in enumerate(_fade_series(dividend_growth, terminal_growth_rate, 5))
        ]
    )

    return (
        market_data,
        {
            "base_values": base_values,
            "default_projection_years": 5,
            "default_cost_of_equity": cost_of_equity,
            "default_terminal_growth_rate": terminal_growth_rate,
        },
        assumptions_frame,
    )


def _current_book_value_per_share(bundle: MarketDataBundle) -> DerivedValue | None:
    shares = _shares_outstanding(bundle)
    equity, equity_period = _latest_value(bundle.annual_financials, lambda item: item.shareholders_equity)
    if shares is None or equity is None or shares.value <= 0:
        return None

    return DerivedValue(
        label="Current Book Value / Share",
        value=equity / shares.value,
        source=_period_source(equity_period),
    )


def _derive_rim_defaults(bundle: MarketDataBundle) -> tuple[RIMMarketData, dict[str, object], pd.DataFrame]:
    book_value_per_share = _current_book_value_per_share(bundle)
    shares = _shares_outstanding(bundle)
    current_price = _current_price(bundle)
    net_income, net_income_period = _latest_value(bundle.annual_financials, lambda item: item.net_income)
    equity, _ = _latest_value(bundle.annual_financials, lambda item: item.shareholders_equity)
    payout_ratio, payout_period = _latest_value(
        bundle.annual_financials,
        lambda item: _safe_ratio(abs(item.dividends_paid), item.net_income)
        if item.dividends_paid is not None
        else None,
    )

    missing_fields: list[str] = []
    if book_value_per_share is None:
        missing_fields.append("current book value per share")
    if shares is None:
        missing_fields.append("shares outstanding")
    if current_price is None:
        missing_fields.append("current price")
    if net_income is None or equity in (None, 0):
        missing_fields.append("historical ROE anchor")

    if missing_fields:
        raise ValueError(
            "Missing auto-loaded RIM inputs: " + ", ".join(missing_fields) + "."
        )

    current_roe = _clamp((net_income or 0.0) / (equity or 1.0), -0.10, 0.35)
    cost_of_equity = _cost_of_equity_from_beta(bundle)
    terminal_growth_rate = min(0.03, cost_of_equity - 0.01)
    terminal_roe = _clamp(max(cost_of_equity + 0.01, current_roe * 0.85), -0.05, 0.20)
    payout_ratio_value = _clamp(payout_ratio or 0.30, 0.0, 0.90)

    market_data = RIMMarketData(
        current_book_value_per_share=book_value_per_share.value,
        shares_outstanding=shares.value,
        current_price=current_price,
    )

    base_values = [
        DerivedValue("Current Book Value / Share", book_value_per_share.value, book_value_per_share.source),
        DerivedValue("Latest Net Income", net_income or 0.0, _period_source(net_income_period)),
        DerivedValue("Shares Outstanding", shares.value, shares.source),
        DerivedValue("Current Price", current_price, "Market snapshot"),
    ]

    assumptions_frame = pd.DataFrame(
        [
            {
                "Year": year + 1,
                "ROE (%)": roe * 100,
                "Payout Ratio (%)": payout_ratio_value * 100,
            }
            for year, roe in enumerate(_fade_series(current_roe, terminal_roe, 5))
        ]
    )

    return (
        market_data,
        {
            "base_values": base_values,
            "default_projection_years": 5,
            "default_cost_of_equity": cost_of_equity,
            "default_terminal_roe": terminal_roe,
            "default_terminal_growth_rate": terminal_growth_rate,
            "payout_source": _period_source(payout_period),
        },
        assumptions_frame,
    )


def _render_assumption_editor(model: str, assumption_frame: pd.DataFrame, editor_key: str) -> pd.DataFrame:
    if model == "DCF":
        return st.data_editor(
            assumption_frame,
            key=editor_key,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            column_config={
                "Year": st.column_config.NumberColumn(disabled=True, format="%d"),
                "Revenue Growth (%)": st.column_config.NumberColumn(format="%.2f"),
                "EBIT Margin (%)": st.column_config.NumberColumn(format="%.2f"),
                "Tax Rate (%)": st.column_config.NumberColumn(format="%.2f"),
                "D&A / Revenue (%)": st.column_config.NumberColumn(format="%.2f"),
                "Capex / Revenue (%)": st.column_config.NumberColumn(format="%.2f"),
                "Change in NWC / Revenue (%)": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    if model == "DDM":
        return st.data_editor(
            assumption_frame,
            key=editor_key,
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            column_config={
                "Year": st.column_config.NumberColumn(disabled=True, format="%d"),
                "Dividend Growth (%)": st.column_config.NumberColumn(format="%.2f"),
            },
        )

    return st.data_editor(
        assumption_frame,
        key=editor_key,
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        column_config={
            "Year": st.column_config.NumberColumn(disabled=True, format="%d"),
            "ROE (%)": st.column_config.NumberColumn(format="%.2f"),
            "Payout Ratio (%)": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def _display_base_inputs(model: str, metadata: dict[str, object]) -> None:
    base_values = metadata["base_values"]
    st.subheader("Auto-Loaded Base Inputs")
    st.caption("These values come from the latest cached market snapshot and financial statements.")
    st.dataframe(
        _build_display_frame(base_values),
        width="stretch",
        hide_index=True,
    )

    if model == "DCF":
        st.caption("DCF uses the latest annual revenue, EBIT, cash, debt, D&A, capex, and working-capital data.")
    elif model == "DDM":
        st.caption("DDM uses the latest annual dividend per share when available, otherwise the current dividend yield.")
    else:
        payout_source = metadata.get("payout_source")
        if payout_source:
            st.caption(f"RIM payout defaults are anchored to {payout_source}.")


def _build_dcf_input(
    market_data: DCFMarketData,
    edited_assumptions: pd.DataFrame,
    projection_years: int,
    wacc_pct: float,
    exit_multiple: float,
) -> DCFInput:
    return DCFInput(
        market_data=market_data,
        assumptions=DCFAssumptions(
            projection_years=projection_years,
            revenue_growth_rates=[value / 100 for value in edited_assumptions["Revenue Growth (%)"].tolist()],
            ebit_margins=[value / 100 for value in edited_assumptions["EBIT Margin (%)"].tolist()],
            tax_rates=[value / 100 for value in edited_assumptions["Tax Rate (%)"].tolist()],
            da_as_pct_revenue=[value / 100 for value in edited_assumptions["D&A / Revenue (%)"].tolist()],
            capex_as_pct_revenue=[value / 100 for value in edited_assumptions["Capex / Revenue (%)"].tolist()],
            nwc_as_pct_revenue=[value / 100 for value in edited_assumptions["Change in NWC / Revenue (%)"].tolist()],
            wacc=wacc_pct / 100,
            exit_multiple=exit_multiple,
        ),
    )


def _build_ddm_input(
    market_data: DDMMarketData,
    edited_assumptions: pd.DataFrame,
    projection_years: int,
    cost_of_equity_pct: float,
    terminal_growth_pct: float,
) -> DDMInput:
    return DDMInput(
        market_data=market_data,
        assumptions=DDMAssumptions(
            projection_years=projection_years,
            dividend_growth_rates=[value / 100 for value in edited_assumptions["Dividend Growth (%)"].tolist()],
            cost_of_equity=cost_of_equity_pct / 100,
            terminal_growth_rate=terminal_growth_pct / 100,
        ),
    )


def _build_rim_input(
    market_data: RIMMarketData,
    edited_assumptions: pd.DataFrame,
    projection_years: int,
    cost_of_equity_pct: float,
    terminal_roe_pct: float,
    terminal_growth_pct: float,
) -> RIMInput:
    return RIMInput(
        market_data=market_data,
        assumptions=RIMAssumptions(
            projection_years=projection_years,
            return_on_equity=[value / 100 for value in edited_assumptions["ROE (%)"].tolist()],
            payout_ratios=[value / 100 for value in edited_assumptions["Payout Ratio (%)"].tolist()],
            cost_of_equity=cost_of_equity_pct / 100,
            terminal_return_on_equity=terminal_roe_pct / 100,
            terminal_growth_rate=terminal_growth_pct / 100,
        ),
    )


def _display_dcf_output(output: DCFOutput) -> None:
    metric_columns = st.columns(4)
    metric_columns[0].metric("Fair Value / Share", _format_currency(output.fair_value_per_share))
    metric_columns[1].metric("Current Price", _format_currency(output.current_price))
    metric_columns[2].metric("Upside / Downside", _format_percent(output.upside_downside_pct))
    metric_columns[3].metric("Enterprise Value", _format_currency_compact(output.enterprise_value))

    tabs = st.tabs(["Summary", "Assumptions", "Projection"])

    with tabs[0]:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Metric": "Equity Value", "Value": _format_currency(output.equity_value)},
                    {"Metric": "PV of Projected FCFF", "Value": _format_currency(output.pv_of_projected_fcff)},
                    {"Metric": "PV of Terminal Value", "Value": _format_currency(output.present_value_terminal_value)},
                    {"Metric": "Terminal Value", "Value": _format_currency(output.terminal_value)},
                    {"Metric": "Terminal EBITDA", "Value": _format_currency(output.terminal_ebitda)},
                    {"Metric": "Exit Multiple", "Value": _format_multiple(output.exit_multiple)},
                    {
                        "Metric": "Terminal Value % of EV",
                        "Value": _format_percent(output.terminal_value_pct_of_enterprise_value),
                    },
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    with tabs[1]:
        assumptions = output.assumptions_used
        if assumptions is None:
            st.info("No assumptions returned.")
        else:
            tax_rates = assumptions.tax_rates if isinstance(assumptions.tax_rates, list) else [assumptions.tax_rates] * assumptions.projection_years
            da_rates = assumptions.da_as_pct_revenue if isinstance(assumptions.da_as_pct_revenue, list) else [assumptions.da_as_pct_revenue] * assumptions.projection_years
            capex_rates = assumptions.capex_as_pct_revenue if isinstance(assumptions.capex_as_pct_revenue, list) else [assumptions.capex_as_pct_revenue] * assumptions.projection_years
            nwc_rates = assumptions.nwc_as_pct_revenue if isinstance(assumptions.nwc_as_pct_revenue, list) else [assumptions.nwc_as_pct_revenue] * assumptions.projection_years

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Year": index + 1,
                            "Revenue Growth (%)": assumptions.revenue_growth_rates[index] * 100,
                            "EBIT Margin (%)": assumptions.ebit_margins[index] * 100,
                            "Tax Rate (%)": tax_rates[index] * 100,
                            "D&A / Revenue (%)": da_rates[index] * 100,
                            "Capex / Revenue (%)": capex_rates[index] * 100,
                            "Change in NWC / Revenue (%)": nwc_rates[index] * 100,
                        }
                        for index in range(assumptions.projection_years)
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    with tabs[2]:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Year": year.year,
                        "Revenue": year.revenue,
                        "EBIT": year.ebit,
                        "EBIT Margin (%)": year.ebit_margin * 100,
                        "NOPAT": year.nopat,
                        "D&A": year.depreciation_amortization,
                        "Capex": year.capex,
                        "Change in NWC": year.change_in_nwc,
                        "FCFF": year.fcff,
                        "PV of FCFF": year.present_value_fcff,
                    }
                    for year in output.projected_years
                ]
            ),
            width="stretch",
            hide_index=True,
        )


def _display_ddm_output(output: DDMOutput) -> None:
    metric_columns = st.columns(4)
    metric_columns[0].metric("Fair Value / Share", _format_currency(output.fair_value_per_share))
    metric_columns[1].metric("Current Price", _format_currency(output.current_price))
    metric_columns[2].metric("Upside / Downside", _format_percent(output.upside_downside_pct))
    metric_columns[3].metric("Equity Value", _format_currency_compact(output.equity_value))

    tabs = st.tabs(["Summary", "Assumptions", "Projection"])

    with tabs[0]:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Metric": "PV of Projected Dividends", "Value": _format_currency(output.pv_of_projected_dividends)},
                    {"Metric": "PV of Terminal Value", "Value": _format_currency(output.present_value_terminal_value)},
                    {"Metric": "Terminal Dividend / Share", "Value": _format_currency(output.terminal_dividend_per_share)},
                    {"Metric": "Terminal Value / Share", "Value": _format_currency(output.terminal_value_per_share)},
                    {
                        "Metric": "Terminal Value % of Fair Value",
                        "Value": _format_percent(output.terminal_value_pct_of_fair_value),
                    },
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    with tabs[1]:
        assumptions = output.assumptions_used
        if assumptions is None:
            st.info("No assumptions returned.")
        else:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Year": index + 1,
                            "Dividend Growth (%)": assumptions.dividend_growth_rates[index] * 100,
                        }
                        for index in range(assumptions.projection_years)
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    with tabs[2]:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Year": year.year,
                        "Dividend / Share": year.dividend_per_share,
                        "Growth Rate (%)": year.growth_rate * 100,
                        "PV of Dividend": year.present_value_dividend,
                    }
                    for year in output.projected_years
                ]
            ),
            width="stretch",
            hide_index=True,
        )


def _display_rim_output(output: RIMOutput) -> None:
    metric_columns = st.columns(4)
    metric_columns[0].metric("Fair Value / Share", _format_currency(output.fair_value_per_share))
    metric_columns[1].metric("Current Price", _format_currency(output.current_price))
    metric_columns[2].metric("Upside / Downside", _format_percent(output.upside_downside_pct))
    metric_columns[3].metric("Equity Value", _format_currency_compact(output.equity_value))

    tabs = st.tabs(["Summary", "Assumptions", "Projection"])

    with tabs[0]:
        st.dataframe(
            pd.DataFrame(
                [
                    {"Metric": "PV of Residual Income", "Value": _format_currency(output.pv_of_projected_residual_income)},
                    {"Metric": "PV of Terminal Value", "Value": _format_currency(output.present_value_terminal_value)},
                    {"Metric": "Terminal BVPS", "Value": _format_currency(output.terminal_book_value_per_share)},
                    {
                        "Metric": "Terminal Residual Income / Share",
                        "Value": _format_currency(output.terminal_residual_income_per_share),
                    },
                    {"Metric": "Terminal Value / Share", "Value": _format_currency(output.terminal_value_per_share)},
                    {
                        "Metric": "Terminal Value % of Fair Value",
                        "Value": _format_percent(output.terminal_value_pct_of_fair_value),
                    },
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    with tabs[1]:
        assumptions = output.assumptions_used
        if assumptions is None:
            st.info("No assumptions returned.")
        else:
            payout_ratios = assumptions.payout_ratios if isinstance(assumptions.payout_ratios, list) else [assumptions.payout_ratios] * assumptions.projection_years

            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Year": index + 1,
                            "ROE (%)": assumptions.return_on_equity[index] * 100,
                            "Payout Ratio (%)": payout_ratios[index] * 100,
                        }
                        for index in range(assumptions.projection_years)
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    with tabs[2]:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Year": year.year,
                        "Beginning BVPS": year.beginning_book_value_per_share,
                        "Ending BVPS": year.ending_book_value_per_share,
                        "ROE (%)": year.return_on_equity * 100,
                        "EPS": year.earnings_per_share,
                        "Payout Ratio (%)": year.payout_ratio * 100,
                        "Residual Income / Share": year.residual_income_per_share,
                        "PV of Residual Income": year.present_value_residual_income,
                    }
                    for year in output.projected_years
                ]
            ),
            width="stretch",
            hide_index=True,
        )


st.write("Choose a valuation model, review auto-loaded operating data, edit the assumptions, and calculate fair value.")

with st.form("calculator_load_form"):
    ticker_column, refresh_column = st.columns([3, 1])
    with ticker_column:
        ticker_input = st.text_input("Ticker", value=st.session_state.get("calculator_ticker", "AAPL")).strip().upper()
    with refresh_column:
        refresh_cache = st.checkbox("Refresh cache", value=False)
    load_clicked = st.form_submit_button("Load Company Data", type="primary")

if load_clicked:
    st.session_state["calculator_ticker"] = ticker_input
    st.session_state["calculator_refresh_requested"] = refresh_cache
    st.session_state["calculator_result"] = None
    st.session_state["calculator_error"] = None

selected_ticker = st.session_state.get("calculator_ticker", "AAPL")
selected_refresh = st.session_state.pop("calculator_refresh_requested", False)

if not selected_ticker:
    st.warning("Please enter a ticker symbol.")
else:
    try:
        bundle = get_market_data_bundle(
            ticker=selected_ticker,
            include_annual=True,
            include_quarterly=True,
            use_cache=True,
            refresh=selected_refresh,
        )

        _display_header(bundle)

        model = st.selectbox("Valuation Model", MODEL_OPTIONS, index=0)

        if model == "DCF":
            market_data, metadata, default_frame = _derive_dcf_defaults(bundle)
        elif model == "DDM":
            market_data, metadata, default_frame = _derive_ddm_defaults(bundle)
        else:
            market_data, metadata, default_frame = _derive_rim_defaults(bundle)

        left_column, right_column = st.columns([1.05, 1.4])

        with left_column:
            _display_base_inputs(model, metadata)

        with right_column:
            st.subheader("Editable Assumptions")
            projection_years = st.number_input(
                "Projection Years",
                min_value=1,
                max_value=10,
                value=int(metadata["default_projection_years"]),
                step=1,
                key=f"projection_years_{selected_ticker}_{model}",
            )

            if int(projection_years) != len(default_frame.index):
                if model == "DCF":
                    growth_start = float(default_frame.iloc[0]["Revenue Growth (%)"]) / 100
                    growth_end = float(default_frame.iloc[-1]["Revenue Growth (%)"]) / 100
                    margin = float(default_frame.iloc[0]["EBIT Margin (%)"])
                    tax_rate = float(default_frame.iloc[0]["Tax Rate (%)"])
                    da_rate = float(default_frame.iloc[0]["D&A / Revenue (%)"])
                    capex_rate = float(default_frame.iloc[0]["Capex / Revenue (%)"])
                    nwc_rate = float(default_frame.iloc[0]["Change in NWC / Revenue (%)"])
                    default_frame = pd.DataFrame(
                        [
                            {
                                "Year": year + 1,
                                "Revenue Growth (%)": value * 100,
                                "EBIT Margin (%)": margin,
                                "Tax Rate (%)": tax_rate,
                                "D&A / Revenue (%)": da_rate,
                                "Capex / Revenue (%)": capex_rate,
                                "Change in NWC / Revenue (%)": nwc_rate,
                            }
                            for year, value in enumerate(_fade_series(growth_start, growth_end, int(projection_years)))
                        ]
                    )
                elif model == "DDM":
                    growth_start = float(default_frame.iloc[0]["Dividend Growth (%)"]) / 100
                    growth_end = float(default_frame.iloc[-1]["Dividend Growth (%)"]) / 100
                    default_frame = pd.DataFrame(
                        [
                            {
                                "Year": year + 1,
                                "Dividend Growth (%)": value * 100,
                            }
                            for year, value in enumerate(_fade_series(growth_start, growth_end, int(projection_years)))
                        ]
                    )
                else:
                    roe_start = float(default_frame.iloc[0]["ROE (%)"]) / 100
                    roe_end = float(default_frame.iloc[-1]["ROE (%)"]) / 100
                    payout_ratio = float(default_frame.iloc[0]["Payout Ratio (%)"])
                    default_frame = pd.DataFrame(
                        [
                            {
                                "Year": year + 1,
                                "ROE (%)": value * 100,
                                "Payout Ratio (%)": payout_ratio,
                            }
                            for year, value in enumerate(_fade_series(roe_start, roe_end, int(projection_years)))
                        ]
                    )

            if model == "DCF":
                scalar_left, scalar_right = st.columns(2)
                with scalar_left:
                    wacc_pct = st.number_input(
                        "WACC (%)",
                        min_value=0.0,
                        max_value=40.0,
                        value=round(float(metadata["default_wacc"]) * 100, 2),
                        step=0.25,
                        key=f"wacc_{selected_ticker}_{model}",
                    )
                with scalar_right:
                    exit_multiple = st.number_input(
                        "Exit Multiple (x)",
                        min_value=0.0,
                        max_value=40.0,
                        value=round(float(metadata["default_exit_multiple"]), 2),
                        step=0.25,
                        key=f"exit_multiple_{selected_ticker}_{model}",
                    )
            elif model == "DDM":
                scalar_left, scalar_right = st.columns(2)
                with scalar_left:
                    cost_of_equity_pct = st.number_input(
                        "Cost of Equity (%)",
                        min_value=0.0,
                        max_value=40.0,
                        value=round(float(metadata["default_cost_of_equity"]) * 100, 2),
                        step=0.25,
                        key=f"cost_of_equity_{selected_ticker}_{model}",
                    )
                with scalar_right:
                    terminal_growth_pct = st.number_input(
                        "Terminal Growth (%)",
                        min_value=-5.0,
                        max_value=20.0,
                        value=round(float(metadata["default_terminal_growth_rate"]) * 100, 2),
                        step=0.25,
                        key=f"terminal_growth_{selected_ticker}_{model}",
                    )
            else:
                scalar_left, scalar_mid, scalar_right = st.columns(3)
                with scalar_left:
                    cost_of_equity_pct = st.number_input(
                        "Cost of Equity (%)",
                        min_value=0.0,
                        max_value=40.0,
                        value=round(float(metadata["default_cost_of_equity"]) * 100, 2),
                        step=0.25,
                        key=f"cost_of_equity_{selected_ticker}_{model}",
                    )
                with scalar_mid:
                    terminal_roe_pct = st.number_input(
                        "Terminal ROE (%)",
                        min_value=-20.0,
                        max_value=40.0,
                        value=round(float(metadata["default_terminal_roe"]) * 100, 2),
                        step=0.25,
                        key=f"terminal_roe_{selected_ticker}_{model}",
                    )
                with scalar_right:
                    terminal_growth_pct = st.number_input(
                        "Terminal Growth (%)",
                        min_value=-5.0,
                        max_value=20.0,
                        value=round(float(metadata["default_terminal_growth_rate"]) * 100, 2),
                        step=0.25,
                        key=f"terminal_growth_{selected_ticker}_{model}",
                    )

            edited_assumptions = _render_assumption_editor(
                model=model,
                assumption_frame=default_frame,
                editor_key=f"assumptions_{selected_ticker}_{model}_{int(projection_years)}",
            )

            calculate_clicked = st.button(
                f"Calculate {model} Fair Value",
                type="primary",
                key=f"calculate_{selected_ticker}_{model}",
            )

            if calculate_clicked:
                try:
                    if model == "DCF":
                        valuation_input = _build_dcf_input(
                            market_data=market_data,
                            edited_assumptions=edited_assumptions,
                            projection_years=int(projection_years),
                            wacc_pct=wacc_pct,
                            exit_multiple=exit_multiple,
                        )
                        result = run_dcf_valuation(valuation_input)
                    elif model == "DDM":
                        valuation_input = _build_ddm_input(
                            market_data=market_data,
                            edited_assumptions=edited_assumptions,
                            projection_years=int(projection_years),
                            cost_of_equity_pct=cost_of_equity_pct,
                            terminal_growth_pct=terminal_growth_pct,
                        )
                        result = run_ddm_valuation(valuation_input)
                    else:
                        valuation_input = _build_rim_input(
                            market_data=market_data,
                            edited_assumptions=edited_assumptions,
                            projection_years=int(projection_years),
                            cost_of_equity_pct=cost_of_equity_pct,
                            terminal_roe_pct=terminal_roe_pct,
                            terminal_growth_pct=terminal_growth_pct,
                        )
                        result = run_rim_valuation(valuation_input)

                    st.session_state["calculator_result"] = result
                    st.session_state["calculator_result_model"] = model
                    st.session_state["calculator_error"] = None

                except Exception as exc:
                    st.session_state["calculator_result"] = None
                    st.session_state["calculator_result_model"] = model
                    st.session_state["calculator_error"] = str(exc)

        stored_error = st.session_state.get("calculator_error")
        stored_result = st.session_state.get("calculator_result")
        stored_model = st.session_state.get("calculator_result_model")

        if stored_error and stored_model == model:
            st.error(f"Unable to calculate {model} fair value: {stored_error}")

        if stored_result is not None and stored_model == model:
            st.subheader(f"{model} Fair Value Output")
            if model == "DCF":
                _display_dcf_output(stored_result)
            elif model == "DDM":
                _display_ddm_output(stored_result)
            else:
                _display_rim_output(stored_result)

    except Exception as exc:
        st.error(f"Failed to load calculator inputs for {selected_ticker}: {exc}")
