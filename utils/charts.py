"""
utils/charts.py
---------------
Plotly chart helpers for AutoGraham.

Provides:
  - Historical P/E and P/B multiple reversion chart
  - Economic moat radar chart
  - DCF waterfall / projection bar chart
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import yfinance as yf


def get_historical_multiples(ticker: str, years: int = 5) -> pd.DataFrame:
    """
    Fetch historical annual P/E and P/B ratios for a given ticker.

    yfinance does not provide point-in-time P/E history directly, so we
    approximate it using closing prices and trailing EPS from the income
    statement / balance sheet.

    Returns a DataFrame with columns ['Date', 'P/E', 'P/B'] indexed by Date,
    or an empty DataFrame on error.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # --- Price history ---
        history = stock.history(period=f"{years}y", interval="1mo")
        if history.empty:
            return pd.DataFrame()

        prices = history["Close"].resample("YE").last()

        # --- EPS history from annual income statement ---
        income = stock.income_stmt
        balance = stock.balance_sheet

        rows = []
        for date, price in prices.items():
            year = date.year
            # Find the matching fiscal year column (or nearest)
            pe = None
            pb = None
            if income is not None and not income.empty:
                matching_cols = [c for c in income.columns if c.year == year]
                col = matching_cols[0] if matching_cols else None
                if col is not None and "Net Income" in income.index:
                    net_income = income.loc["Net Income", col]
                    shares = info.get("sharesOutstanding", 0)
                    if shares and net_income:
                        eps = net_income / shares
                        if eps > 0:
                            pe = price / eps

            if balance is not None and not balance.empty:
                matching_cols = [c for c in balance.columns if c.year == year]
                col = matching_cols[0] if matching_cols else None
                if col is not None:
                    equity = None
                    for label in ("Stockholders Equity", "Total Stockholders Equity",
                                  "Common Stock Equity"):
                        if label in balance.index:
                            equity = balance.loc[label, col]
                            break
                    shares = info.get("sharesOutstanding", 0)
                    if equity and shares:
                        bvps = equity / shares
                        if bvps > 0:
                            pb = price / bvps

            rows.append({"Date": date, "P/E": pe, "P/B": pb})

        df = pd.DataFrame(rows).set_index("Date")
        return df
    except Exception:
        return pd.DataFrame()


def plot_historical_multiples(df: pd.DataFrame, current_pe: float | None,
                               current_pb: float | None, ticker: str) -> go.Figure:
    """
    Plot historical P/E and P/B ratios vs. the current ratio.

    Parameters
    ----------
    df          : DataFrame from get_historical_multiples().
    current_pe  : Current trailing P/E from yfinance info.
    current_pb  : Current P/B from yfinance info.
    ticker      : Ticker symbol (used in title).

    Returns a Plotly Figure.
    """
    fig = go.Figure()

    if df.empty:
        fig.add_annotation(text="Historical data unavailable",
                           xref="paper", yref="paper", x=0.5, y=0.5,
                           showarrow=False, font=dict(size=16))
        return fig

    if "P/E" in df.columns and df["P/E"].notna().any():
        fig.add_trace(go.Scatter(
            x=df.index, y=df["P/E"],
            mode="lines+markers",
            name="Historical P/E",
            line=dict(color="#4C9BE8", width=2),
        ))
    if "P/B" in df.columns and df["P/B"].notna().any():
        fig.add_trace(go.Scatter(
            x=df.index, y=df["P/B"],
            mode="lines+markers",
            name="Historical P/B",
            line=dict(color="#F4A261", width=2),
            yaxis="y2",
        ))

    # Add horizontal reference lines for current values
    if current_pe:
        fig.add_hline(y=current_pe, line_dash="dash", line_color="#4C9BE8",
                      annotation_text=f"Current P/E: {current_pe:.1f}",
                      annotation_position="top right")
    if current_pb:
        fig.add_hline(y=current_pb, line_dash="dash", line_color="#F4A261",
                      annotation_text=f"Current P/B: {current_pb:.1f}",
                      annotation_position="bottom right")

    fig.update_layout(
        title=f"{ticker} — Historical Valuation Multiples (5-Year)",
        xaxis_title="Year",
        yaxis_title="P/E Ratio",
        yaxis2=dict(title="P/B Ratio", overlaying="y", side="right"),
        legend=dict(orientation="h", y=-0.2),
        hovermode="x unified",
        template="plotly_dark",
        height=420,
    )
    return fig


def plot_moat_radar(scores: dict, company_name: str) -> go.Figure:
    """
    Create a radar (spider) chart for economic moat dimensions.

    Parameters
    ----------
    scores       : Dict mapping dimension → score (1-5).
    company_name : Used in the chart title.
    """
    dimensions = list(scores.keys())
    values = list(scores.values())

    # Close the polygon by repeating the first value
    dimensions_closed = dimensions + [dimensions[0]]
    values_closed = values + [values[0]]

    fig = go.Figure(go.Scatterpolar(
        r=values_closed,
        theta=dimensions_closed,
        fill="toself",
        fillcolor="rgba(76, 155, 232, 0.25)",
        line=dict(color="#4C9BE8", width=2),
        name=company_name,
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5]),
        ),
        showlegend=False,
        title=f"{company_name} — Economic Moat Radar",
        template="plotly_dark",
        height=420,
    )
    return fig


def plot_dcf_bar(projected_fcfs: list, pv_fcfs: list) -> go.Figure:
    """
    Bar chart comparing projected FCFs vs. their present values over the projection horizon.
    """
    years = [f"Year {i+1}" for i in range(len(projected_fcfs))]
    projected_m = [v / 1e6 for v in projected_fcfs]
    pv_m = [v / 1e6 for v in pv_fcfs]

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Projected FCF ($M)", x=years, y=projected_m,
                          marker_color="#4C9BE8"))
    fig.add_trace(go.Bar(name="PV of FCF ($M)", x=years, y=pv_m,
                          marker_color="#F4A261"))

    fig.update_layout(
        barmode="group",
        title="DCF — Projected vs. Present Value of Free Cash Flows",
        xaxis_title="Year",
        yaxis_title="Free Cash Flow ($M)",
        legend=dict(orientation="h", y=-0.2),
        template="plotly_dark",
        height=400,
    )
    return fig
