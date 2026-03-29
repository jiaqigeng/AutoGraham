from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from data.market.schemas import FinancialPeriod, MarketDataBundle, PriceBar
from data.market.service import get_market_data_bundle


st.set_page_config(page_title="Financial Data", layout="wide")


def _format_text(value: object) -> str:
    if value is None or value == "":
        return "N/A"
    return str(value)


def _format_currency(value: float | None, precision: int = 2) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.{precision}f}"


def _format_human_number(value: float | None, prefix: str = "") -> str:
    if value is None:
        return "N/A"

    absolute_value = abs(value)
    suffix = ""
    scaled_value = value

    if absolute_value >= 1_000_000_000_000:
        scaled_value = value / 1_000_000_000_000
        suffix = "T"
    elif absolute_value >= 1_000_000_000:
        scaled_value = value / 1_000_000_000
        suffix = "B"
    elif absolute_value >= 1_000_000:
        scaled_value = value / 1_000_000
        suffix = "M"
    elif absolute_value >= 1_000:
        scaled_value = value / 1_000
        suffix = "K"

    return f"{prefix}{scaled_value:,.1f}{suffix}"


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}x"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _compact_number_label_expr() -> str:
    return (
        "abs(datum.value) >= 1e12 ? format(datum.value / 1e12, '.1f') + 'T' : "
        "abs(datum.value) >= 1e9 ? format(datum.value / 1e9, '.1f') + 'B' : "
        "abs(datum.value) >= 1e6 ? format(datum.value / 1e6, '.1f') + 'M' : "
        "abs(datum.value) >= 1e3 ? format(datum.value / 1e3, '.1f') + 'K' : "
        "format(datum.value, ',.0f')"
    )


def _currency_axis(title: str = "USD") -> dict[str, object]:
    return {
        "title": title,
        "labelExpr": _compact_number_label_expr(),
    }


def _percent_axis(title: str = "Margin") -> dict[str, object]:
    return {
        "title": title,
        "format": ".0%",
    }


def _growth_rate(current_value: float | None, prior_value: float | None) -> float | None:
    if current_value is None or prior_value in (None, 0):
        return None
    return (current_value - prior_value) / abs(prior_value)


def _period_label(period: FinancialPeriod) -> str:
    if period.period_type == "quarterly" and period.fiscal_quarter is not None:
        return f"{period.fiscal_year} Q{period.fiscal_quarter}"
    return str(period.fiscal_year or period.period_end.year)


def _sort_periods(periods: list[FinancialPeriod]) -> list[FinancialPeriod]:
    return sorted(periods, key=lambda period: period.period_end)


def _find_latest_complete_period(periods: list[FinancialPeriod]) -> FinancialPeriod | None:
    for period in reversed(_sort_periods(periods)):
        ebit_like = period.ebit if period.ebit is not None else period.operating_income
        if (
            period.revenue is not None
            and period.gross_profit is not None
            and ebit_like is not None
            and period.net_income is not None
        ):
            return period
    return None


def _latest_period(periods: list[FinancialPeriod]) -> FinancialPeriod | None:
    sorted_periods = _sort_periods(periods)
    if not sorted_periods:
        return None
    return sorted_periods[-1]


def _financials_to_dataframe(financial_periods: list[FinancialPeriod]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period in _sort_periods(financial_periods):
        current_ratio = None
        if period.current_assets is not None and period.current_liabilities not in (None, 0):
            current_ratio = period.current_assets / period.current_liabilities

        revenue = period.revenue
        gross_profit = period.gross_profit
        ebit_like = period.ebit if period.ebit is not None else period.operating_income
        net_income = period.net_income

        rows.append(
            {
                "Period": _period_label(period),
                "Period End": period.period_end.isoformat(),
                "Revenue": _format_human_number(revenue, "$"),
                "Gross Profit": _format_human_number(gross_profit, "$"),
                "Gross Margin": _format_percent(
                    (gross_profit / revenue) if revenue not in (None, 0) and gross_profit is not None else None
                ),
                "EBIT": _format_human_number(ebit_like, "$"),
                "EBIT Margin": _format_percent(
                    (ebit_like / revenue) if revenue not in (None, 0) and ebit_like is not None else None
                ),
                "Net Income": _format_human_number(net_income, "$"),
                "Net Margin": _format_percent(
                    (net_income / revenue) if revenue not in (None, 0) and net_income is not None else None
                ),
                "Operating Cash Flow": _format_human_number(period.operating_cash_flow, "$"),
                "Free Cash Flow": _format_human_number(period.free_cash_flow, "$"),
                "Cash": _format_human_number(period.cash, "$"),
                "Debt": _format_human_number(period.total_debt, "$"),
                "Equity": _format_human_number(period.shareholders_equity, "$"),
                "Current Ratio": _format_ratio(current_ratio),
                "Shares Outstanding": _format_human_number(period.shares_outstanding),
            }
        )

    return pd.DataFrame(rows[::-1])


def _build_price_history_frame(price_history: list[PriceBar]) -> pd.DataFrame:
    rows = [
        {
            "Date": bar.date,
            "Close": bar.close,
            "Volume": bar.volume,
        }
        for bar in price_history
        if bar.close is not None
    ]
    return pd.DataFrame(rows)


def _build_trend_frame(periods: list[FinancialPeriod], period_name: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period in _sort_periods(periods):
        ebit_like = period.ebit if period.ebit is not None else period.operating_income
        revenue = period.revenue
        gross_profit = period.gross_profit
        net_income = period.net_income
        free_cash_flow = period.free_cash_flow

        rows.append(
            {
                "Label": _period_label(period),
                "Period Type": period_name,
                "Revenue": revenue,
                "Gross Profit": gross_profit,
                "EBIT": ebit_like,
                "Net Income": net_income,
                "Free Cash Flow": free_cash_flow,
            }
        )

    return pd.DataFrame(rows)


def _build_margin_frame(periods: list[FinancialPeriod]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period in _sort_periods(periods):
        revenue = period.revenue
        ebit_like = period.ebit if period.ebit is not None else period.operating_income

        if revenue in (None, 0):
            gross_margin = None
            ebit_margin = None
            net_margin = None
        else:
            gross_margin = (
                period.gross_profit / revenue if period.gross_profit is not None else None
            )
            ebit_margin = ebit_like / revenue if ebit_like is not None else None
            net_margin = period.net_income / revenue if period.net_income is not None else None

        rows.append(
            {
                "Label": _period_label(period),
                "Gross Margin": gross_margin,
                "EBIT Margin": ebit_margin,
                "Net Margin": net_margin,
            }
        )

    return pd.DataFrame(rows)


def _render_line_chart(
    data_frame: pd.DataFrame,
    x_field: str,
    y_fields: list[str],
    y_title: str,
    height: int = 320,
) -> None:
    if data_frame.empty:
        st.info("No chart data available.")
        return

    chart_frame = data_frame[[x_field, *y_fields]].melt(
        id_vars=[x_field],
        value_vars=y_fields,
        var_name="Metric",
        value_name="Value",
    ).dropna(subset=["Value"])

    if chart_frame.empty:
        st.info("No chart data available.")
        return

    spec = {
        "height": height,
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {
                "field": x_field,
                "type": "nominal",
                "sort": data_frame[x_field].tolist(),
                "axis": {"title": None, "labelAngle": 0},
            },
            "y": {
                "field": "Value",
                "type": "quantitative",
                "axis": _percent_axis(y_title) if y_title == "Margin" else _currency_axis(y_title),
            },
            "color": {"field": "Metric", "type": "nominal"},
            "tooltip": [
                {"field": x_field, "type": "nominal"},
                {"field": "Metric", "type": "nominal"},
                {"field": "Value", "type": "quantitative", "format": ",.2f"},
            ],
        },
    }

    st.vega_lite_chart(chart_frame, spec, width="stretch")


def _render_bar_chart(
    data_frame: pd.DataFrame,
    x_field: str,
    y_fields: list[str],
    y_title: str,
    height: int = 320,
) -> None:
    if data_frame.empty:
        st.info("No chart data available.")
        return

    chart_frame = data_frame[[x_field, *y_fields]].melt(
        id_vars=[x_field],
        value_vars=y_fields,
        var_name="Metric",
        value_name="Value",
    ).dropna(subset=["Value"])

    if chart_frame.empty:
        st.info("No chart data available.")
        return

    spec = {
        "height": height,
        "mark": {"type": "bar"},
        "encoding": {
            "x": {
                "field": x_field,
                "type": "nominal",
                "sort": data_frame[x_field].tolist(),
                "axis": {"title": None, "labelAngle": 0},
            },
            "xOffset": {"field": "Metric"},
            "y": {"field": "Value", "type": "quantitative", "axis": _currency_axis(y_title)},
            "color": {"field": "Metric", "type": "nominal"},
            "tooltip": [
                {"field": x_field, "type": "nominal"},
                {"field": "Metric", "type": "nominal"},
                {"field": "Value", "type": "quantitative", "format": ",.2f"},
            ],
        },
    }

    st.vega_lite_chart(chart_frame, spec, width="stretch")


def _build_revenue_bridge_frame(
    period: FinancialPeriod,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    operating_profit = period.ebit if period.ebit is not None else period.operating_income
    revenue = period.revenue or 0.0
    gross_profit = period.gross_profit or 0.0
    operating_profit_value = operating_profit or 0.0
    net_profit = period.net_income or 0.0
    taxes = -float(period.income_tax_expense or 0.0)
    other_income_expenses = net_profit - operating_profit_value - taxes

    steps = [
        ("Revenue", revenue, "summary"),
        ("Cost of Revenue", gross_profit - revenue, "delta"),
        ("Gross Profit", gross_profit, "summary"),
        ("Operating Expenses", operating_profit_value - gross_profit, "delta"),
        ("Operating Profit", operating_profit_value, "summary"),
        ("Taxes", taxes, "delta"),
        ("Other Income / Expenses", other_income_expenses, "delta"),
        ("Net Profits", net_profit, "summary"),
    ]

    current_total = 0.0
    rows: list[dict[str, object]] = []
    connectors: list[dict[str, object]] = []

    for index, (label, amount, step_type) in enumerate(steps):
        if step_type == "summary":
            start = 0.0
            end = amount
            current_total = amount
            category = "summary"
        else:
            next_total = current_total + amount
            start = min(current_total, next_total)
            end = max(current_total, next_total)
            current_total = next_total
            category = "positive" if amount >= 0 else "negative"

        rows.append(
            {
                "Order": index,
                "Step": label,
                "Amount": amount,
                "Start": start,
                "End": end,
                "Label": _format_human_number(amount, "$"),
                "Category": category,
            }
        )

        if index < len(steps) - 1:
            connectors.append(
                {
                    "FromStep": label,
                    "FromOrder": index,
                    "ToStep": steps[index + 1][0],
                    "ToOrder": index + 1,
                    "ConnectorValue": current_total,
                }
            )

    return pd.DataFrame(rows), pd.DataFrame(connectors)


def _render_header(bundle: MarketDataBundle) -> None:
    company_info = bundle.company_info
    if company_info is None:
        st.title("Financial Data")
        return

    company_name = company_info.company_name or company_info.ticker
    st.title(f"{company_name} ({company_info.ticker})")

    descriptors = [
        company_info.sector,
        company_info.industry,
        company_info.exchange,
        company_info.currency,
    ]
    st.caption(" | ".join(part for part in descriptors if part))


def _render_summary_metrics(bundle: MarketDataBundle) -> None:
    market_snapshot = bundle.market_snapshot
    annual_periods = _sort_periods(bundle.annual_financials)
    latest_annual = annual_periods[-1] if annual_periods else None
    previous_annual = annual_periods[-2] if len(annual_periods) >= 2 else None

    revenue_growth = (
        _growth_rate(latest_annual.revenue, previous_annual.revenue)
        if latest_annual and previous_annual
        else None
    )
    fcf_growth = (
        _growth_rate(latest_annual.free_cash_flow, previous_annual.free_cash_flow)
        if latest_annual and previous_annual
        else None
    )

    metrics = st.columns(5)
    metrics[0].metric(
        "Price",
        _format_currency(market_snapshot.current_price if market_snapshot else None),
    )
    metrics[1].metric(
        "Market Cap",
        _format_human_number(market_snapshot.market_cap if market_snapshot else None, "$"),
    )
    metrics[2].metric(
        "Latest Revenue",
        _format_human_number(latest_annual.revenue if latest_annual else None, "$"),
        delta=_format_percent(revenue_growth) if revenue_growth is not None else None,
    )
    metrics[3].metric(
        "Free Cash Flow",
        _format_human_number(latest_annual.free_cash_flow if latest_annual else None, "$"),
        delta=_format_percent(fcf_growth) if fcf_growth is not None else None,
    )
    metrics[4].metric(
        "Net Debt",
        _format_human_number(
            (
                (latest_annual.total_debt or 0.0) - (latest_annual.cash or 0.0)
                if latest_annual and (latest_annual.total_debt is not None or latest_annual.cash is not None)
                else None
            ),
            "$",
        ),
    )


def _render_company_snapshot(bundle: MarketDataBundle) -> None:
    company_info = bundle.company_info
    market_snapshot = bundle.market_snapshot
    latest_annual = _latest_period(bundle.annual_financials)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("Company Snapshot")
        st.write(f"**Ticker:** {_format_text(company_info.ticker if company_info else None)}")
        st.write(f"**Company:** {_format_text(company_info.company_name if company_info else None)}")
        st.write(f"**Sector:** {_format_text(company_info.sector if company_info else None)}")
        st.write(f"**Industry:** {_format_text(company_info.industry if company_info else None)}")
        st.write(f"**Exchange:** {_format_text(company_info.exchange if company_info else None)}")

    with col_right:
        st.subheader("Market Snapshot")
        st.write(f"**Enterprise Value:** {_format_human_number(market_snapshot.enterprise_value if market_snapshot else None, '$')}")
        st.write(f"**P/E:** {_format_ratio(market_snapshot.pe_ratio if market_snapshot else None)}")
        st.write(f"**P/B:** {_format_ratio(market_snapshot.pb_ratio if market_snapshot else None)}")
        st.write(f"**P/S:** {_format_ratio(market_snapshot.ps_ratio if market_snapshot else None)}")
        st.write(f"**Dividend Yield:** {_format_percent(market_snapshot.dividend_yield if market_snapshot else None)}")
        st.write(
            f"**52-Week Range:** "
            f"{_format_currency(market_snapshot.fifty_two_week_low if market_snapshot else None)}"
            f" to {_format_currency(market_snapshot.fifty_two_week_high if market_snapshot else None)}"
        )

    if latest_annual is not None:
        st.caption(
            "Latest annual period: "
            f"{latest_annual.period_end.isoformat()} | "
            f"Cash {_format_human_number(latest_annual.cash, '$')} | "
            f"Debt {_format_human_number(latest_annual.total_debt, '$')} | "
            f"Equity {_format_human_number(latest_annual.shareholders_equity, '$')}"
        )


def _render_price_chart(bundle: MarketDataBundle) -> None:
    st.subheader("Price History")
    price_frame = _build_price_history_frame(bundle.price_history)
    if price_frame.empty:
        st.info("No price history available.")
        return

    spec = {
        "height": 320,
        "mark": {"type": "line"},
        "encoding": {
            "x": {
                "field": "Date",
                "type": "temporal",
                "title": None,
                "axis": {"format": "%b %Y", "labelAngle": 0},
            },
            "y": {"field": "Close", "type": "quantitative", "title": "Price"},
            "tooltip": [
                {"field": "Date", "type": "temporal"},
                {"field": "Close", "type": "quantitative", "format": ",.2f"},
            ],
        },
    }
    st.vega_lite_chart(price_frame, spec, width="stretch")


def _render_trend_charts(bundle: MarketDataBundle) -> None:
    annual_frame = _build_trend_frame(bundle.annual_financials, "Annual")
    quarterly_frame = _build_trend_frame(bundle.quarterly_financials, "Quarterly")

    trend_left, trend_right = st.columns(2)

    with trend_left:
        st.subheader("Annual Scale")
        if annual_frame.empty:
            st.info("No annual financials available.")
        else:
            _render_line_chart(
                annual_frame,
                x_field="Label",
                y_fields=["Revenue", "Gross Profit", "EBIT", "Net Income"],
                y_title="USD",
            )

    with trend_right:
        st.subheader("Quarterly Operating View")
        if quarterly_frame.empty:
            st.info("No quarterly financials available.")
        else:
            _render_bar_chart(
                quarterly_frame,
                x_field="Label",
                y_fields=["Revenue", "Free Cash Flow"],
                y_title="USD",
            )

    st.subheader("Margin Trend")
    margin_frame = _build_margin_frame(bundle.annual_financials)
    if margin_frame.empty:
        st.info("No annual margin data available.")
    else:
        _render_line_chart(
            margin_frame,
            x_field="Label",
            y_fields=["Gross Margin", "EBIT Margin", "Net Margin"],
            y_title="Margin",
        )


def _render_revenue_bridge(bundle: MarketDataBundle) -> None:
    st.subheader("Revenue Bridge")
    bridge_period = _find_latest_complete_period(bundle.annual_financials)
    if bridge_period is None:
        st.info("No annual period has enough fields to build the revenue bridge yet.")
        return

    bridge_frame, connector_frame = _build_revenue_bridge_frame(bridge_period)
    step_order = bridge_frame["Step"].tolist()
    spec = {
        "height": 360,
        "layer": [
            {
                "data": {"values": connector_frame.to_dict(orient="records")},
                "mark": {
                    "type": "rule",
                    "strokeDash": [5, 5],
                    "strokeWidth": 1.5,
                    "color": "#94a3b8",
                },
                "encoding": {
                    "x": {
                        "field": "FromStep",
                        "type": "nominal",
                        "scale": {"domain": step_order},
                        "axis": {"title": None, "labelAngle": 0},
                    },
                    "x2": {"field": "ToStep"},
                    "y": {"field": "ConnectorValue", "type": "quantitative", "axis": _currency_axis("USD")},
                },
            },
            {
                "mark": {
                    "type": "bar",
                    "size": 48,
                    "cornerRadiusTopLeft": 4,
                    "cornerRadiusTopRight": 4,
                },
                "encoding": {
                    "x": {
                        "field": "Step",
                        "type": "nominal",
                        "scale": {"domain": step_order},
                        "axis": {"title": None, "labelAngle": 0},
                    },
                    "y": {"field": "Start", "type": "quantitative", "axis": _currency_axis("USD")},
                    "y2": {"field": "End"},
                    "color": {
                        "field": "Category",
                        "type": "nominal",
                        "scale": {
                            "domain": ["summary", "positive", "negative"],
                            "range": ["#2f6bff", "#23a26d", "#d94f45"],
                        },
                        "legend": None,
                    },
                    "tooltip": [
                        {"field": "Step", "type": "nominal"},
                        {"field": "Amount", "type": "quantitative", "format": ",.2f"},
                    ],
                },
            },
            {
                "mark": {"type": "text", "dy": -8, "fontSize": 12},
                "encoding": {
                    "x": {
                        "field": "Step",
                        "type": "nominal",
                        "scale": {"domain": step_order},
                    },
                    "y": {"field": "End", "type": "quantitative"},
                    "text": {"field": "Label", "type": "nominal"},
                },
            },
        ],
    }

    st.vega_lite_chart(bridge_frame, spec, width="stretch")
    st.caption(
        "This uses the latest annual period with complete statement data and shows how revenue "
        "moves through cost of revenue, gross profit, operating expenses, operating profit, "
        "taxes, other income or expenses, and net profits."
    )


def _render_data_tables(bundle: MarketDataBundle) -> None:
    annual_tab, quarterly_tab, raw_tab = st.tabs(["Annual", "Quarterly", "Raw Bundle"])

    with annual_tab:
        annual_frame = _financials_to_dataframe(bundle.annual_financials)
        if annual_frame.empty:
            st.info("No annual financials available.")
        else:
            st.dataframe(annual_frame, width="stretch", hide_index=True)

    with quarterly_tab:
        quarterly_frame = _financials_to_dataframe(bundle.quarterly_financials)
        if quarterly_frame.empty:
            st.info("No quarterly financials available.")
        else:
            st.dataframe(quarterly_frame, width="stretch", hide_index=True)

    with raw_tab:
        raw_bundle = {
            "company_info": asdict(bundle.company_info) if bundle.company_info else {},
            "market_snapshot": asdict(bundle.market_snapshot) if bundle.market_snapshot else {},
            "annual_financials": [asdict(period) for period in bundle.annual_financials],
            "quarterly_financials": [asdict(period) for period in bundle.quarterly_financials],
        }
        st.json(raw_bundle, expanded=False)


st.write("Review the market, financial, and trend data available for a ticker.")

with st.form("financial_data_form"):
    form_col1, form_col2, form_col3 = st.columns([2, 1, 1])
    with form_col1:
        ticker = st.text_input("Ticker", value="AAPL").strip().upper()
    with form_col2:
        refresh_cache = st.checkbox("Refresh cache", value=False)
    with form_col3:
        load_clicked = st.form_submit_button("Load Data", type="primary")

if load_clicked:
    st.session_state["financial_data_ticker"] = ticker
    st.session_state["financial_data_refresh_requested"] = refresh_cache


selected_ticker = st.session_state.get("financial_data_ticker", "AAPL")
selected_refresh = st.session_state.pop("financial_data_refresh_requested", False)

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

        _render_header(bundle)
        _render_summary_metrics(bundle)

        overview_tab, trends_tab, tables_tab = st.tabs(["Overview", "Trends", "Tables"])

        with overview_tab:
            _render_company_snapshot(bundle)
            _render_revenue_bridge(bundle)
            _render_price_chart(bundle)

        with trends_tab:
            _render_trend_charts(bundle)

        with tables_tab:
            _render_data_tables(bundle)

    except Exception as exc:
        st.error(f"Failed to load market data for {selected_ticker}: {exc}")
