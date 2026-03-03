"""
utils/dcf.py
------------
Discounted Cash Flow (DCF) valuation helpers for AutoGraham.

Provides functions to fetch the financial inputs needed for a DCF model
and to calculate intrinsic value based on user-supplied assumptions.
"""

import yfinance as yf
import pandas as pd


def get_stock_data(ticker: str) -> dict:
    """
    Fetch key financial data for a given ticker using yfinance.

    Returns a dict with:
        - info:               raw yfinance info dict
        - current_price
        - free_cash_flow      (TTM, in dollars)
        - shares_outstanding
        - total_debt
        - cash_and_equivalents
        - market_cap
    Returns an empty dict on error or invalid ticker.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Guard against missing or invalid tickers
        if not info or info.get("regularMarketPrice") is None:
            return {}

        cash_flow = stock.cashflow
        fcf = 0.0
        if cash_flow is not None and not cash_flow.empty and len(cash_flow.columns) > 0:
            cols = cash_flow.columns  # sorted newest -> oldest
            try:
                if "Free Cash Flow" in cash_flow.index:
                    fcf = float(cash_flow.loc["Free Cash Flow", cols[0]])
                elif "Operating Cash Flow" in cash_flow.index:
                    # Fallback: operating cash flow as a proxy
                    fcf = float(cash_flow.loc["Operating Cash Flow", cols[0]])
            except (KeyError, TypeError, ValueError):
                fcf = 0.0

        return {
            "info": info,
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "free_cash_flow": fcf,
            "shares_outstanding": info.get("sharesOutstanding", 0),
            "total_debt": info.get("totalDebt", 0),
            "cash_and_equivalents": info.get("totalCash", 0),
            "market_cap": info.get("marketCap", 0),
        }
    except Exception:
        return {}


def calculate_dcf(
    free_cash_flow: float,
    shares_outstanding: int,
    growth_rate: float,
    wacc: float,
    terminal_multiple: float,
    projection_years: int = 10,
    total_debt: float = 0.0,
    cash: float = 0.0,
) -> dict:
    """
    Calculate DCF intrinsic value per share.

    Parameters
    ----------
    free_cash_flow      : Most recent TTM free cash flow (dollars).
    shares_outstanding  : Shares outstanding.
    growth_rate         : Annual FCF growth rate (decimal, e.g. 0.10 for 10 %).
    wacc                : Weighted average cost of capital (decimal).
    terminal_multiple   : EV/FCF exit multiple applied in year `projection_years`.
    projection_years    : Number of years to project (default 10).
    total_debt          : Total debt (dollars) for net-debt adjustment.
    cash                : Cash & equivalents (dollars) for net-debt adjustment.

    Returns a dict with:
        - projected_fcfs      : list of projected annual FCFs
        - pv_fcfs             : list of present-valued FCFs
        - terminal_value      : PV of terminal value
        - intrinsic_value     : intrinsic enterprise value (dollars)
        - intrinsic_per_share : intrinsic equity value per share
    Returns empty dict on invalid inputs.
    """
    if shares_outstanding <= 0 or wacc <= 0:
        return {}

    projected_fcfs = []
    pv_fcfs = []

    for year in range(1, projection_years + 1):
        projected = free_cash_flow * (1 + growth_rate) ** year
        pv = projected / (1 + wacc) ** year
        projected_fcfs.append(projected)
        pv_fcfs.append(pv)

    # Terminal value based on exit multiple applied to year-N FCF
    terminal_fcf = projected_fcfs[-1]
    terminal_value_future = terminal_fcf * terminal_multiple
    terminal_value_pv = terminal_value_future / (1 + wacc) ** projection_years

    intrinsic_enterprise_value = sum(pv_fcfs) + terminal_value_pv

    # Equity value = EV - debt + cash
    equity_value = intrinsic_enterprise_value - total_debt + cash
    intrinsic_per_share = equity_value / shares_outstanding if shares_outstanding else 0

    return {
        "projected_fcfs": projected_fcfs,
        "pv_fcfs": pv_fcfs,
        "terminal_value": terminal_value_pv,
        "intrinsic_value": intrinsic_enterprise_value,
        "intrinsic_per_share": intrinsic_per_share,
    }


def get_dcf_projection_df(projected_fcfs: list, pv_fcfs: list) -> pd.DataFrame:
    """
    Build a tidy DataFrame of projected vs. present-valued FCFs for display.
    """
    years = list(range(1, len(projected_fcfs) + 1))
    return pd.DataFrame(
        {
            "Year": years,
            "Projected FCF ($M)": [v / 1e6 for v in projected_fcfs],
            "PV of FCF ($M)": [v / 1e6 for v in pv_fcfs],
        }
    ).set_index("Year")
