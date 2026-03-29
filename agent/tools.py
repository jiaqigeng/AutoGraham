from __future__ import annotations

from typing import Any

from data.market.schemas import (
    CompanyInfo,
    FinancialPeriod,
    MarketDataBundle,
    MarketSnapshot,
)
from data.market.service import (
    get_company_info,
    get_financial_periods,
    get_market_data_bundle,
    get_market_snapshot,
)
from valuation.ddm.schemas import DDMAssumptions, DDMInput, DDMMarketData, DDMOutput
from valuation.ddm.service import run_ddm_valuation
from valuation.dcf.schemas import DCFAssumptions, DCFInput, DCFMarketData, DCFOutput
from valuation.dcf.service import run_dcf_valuation
from valuation.rim.schemas import RIMAssumptions, RIMInput, RIMMarketData, RIMOutput
from valuation.rim.service import run_rim_valuation


def load_market_data_bundle(
    ticker: str,
    refresh: bool = False,
) -> MarketDataBundle:
    """Load the top-level market data bundle for a ticker."""
    return get_market_data_bundle(ticker=ticker, refresh=refresh)


def load_company_info(
    ticker: str,
    refresh: bool = False,
) -> CompanyInfo | None:
    """Load company identity and metadata for a ticker."""
    return get_company_info(ticker=ticker, refresh=refresh)


def load_market_snapshot(
    ticker: str,
    refresh: bool = False,
) -> MarketSnapshot | None:
    """Load the latest market snapshot for a ticker."""
    return get_market_snapshot(ticker=ticker, refresh=refresh)


def load_annual_financials(
    ticker: str,
    refresh: bool = False,
) -> list[FinancialPeriod]:
    """Load annual financial periods for a ticker."""
    return get_financial_periods(
        ticker=ticker,
        period_type="annual",
        refresh=refresh,
    )


def load_quarterly_financials(
    ticker: str,
    refresh: bool = False,
) -> list[FinancialPeriod]:
    """Load quarterly financial periods for a ticker."""
    return get_financial_periods(
        ticker=ticker,
        period_type="quarterly",
        refresh=refresh,
    )


def run_dcf_tool(dcf_input: DCFInput) -> DCFOutput:
    """Run the app-facing DCF valuation tool."""
    return run_dcf_valuation(dcf_input)


def run_ddm_tool(ddm_input: DDMInput) -> DDMOutput:
    """Run the app-facing DDM valuation tool."""
    return run_ddm_valuation(ddm_input)


def run_rim_tool(rim_input: RIMInput) -> RIMOutput:
    """Run the app-facing RIM valuation tool."""
    return run_rim_valuation(rim_input)


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper()


def _sort_periods(periods: list[FinancialPeriod]) -> list[FinancialPeriod]:
    return sorted(periods, key=lambda period: period.period_end)


def _latest_period(periods: list[FinancialPeriod]) -> FinancialPeriod | None:
    if not periods:
        return None
    return _sort_periods(periods)[-1]


def _growth_rate(current_value: float | None, prior_value: float | None) -> float | None:
    if current_value is None or prior_value in (None, 0):
        return None
    return (current_value - prior_value) / abs(prior_value)


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
        "current_assets": period.current_assets,
        "current_liabilities": period.current_liabilities,
    }


def _build_missing_data_notes(
    company_info: CompanyInfo | None,
    market_snapshot: MarketSnapshot | None,
    annual_financials: list[FinancialPeriod],
    quarterly_financials: list[FinancialPeriod],
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
    notes.append("Transcript data is not available in this run.")
    notes.append("SEC filing data is not available in this run.")
    return notes


def load_valuation_context(ticker: str, refresh: bool = False) -> dict[str, Any]:
    """Load the local context needed for valuation, including company info, snapshot, recent financials, trends, and missing-data notes."""
    normalized_ticker = _normalize_ticker(ticker)
    company_info = load_company_info(normalized_ticker, refresh=refresh)
    market_snapshot = load_market_snapshot(normalized_ticker, refresh=refresh)
    annual_financials = load_annual_financials(normalized_ticker, refresh=refresh)
    quarterly_financials = load_quarterly_financials(normalized_ticker, refresh=refresh)

    annual_sorted = _sort_periods(annual_financials)
    quarterly_sorted = _sort_periods(quarterly_financials)
    latest_annual = _latest_period(annual_sorted)
    previous_annual = annual_sorted[-2] if len(annual_sorted) >= 2 else None

    return {
        "ticker": normalized_ticker,
        "company_info": _serialize_company_info(company_info),
        "market_snapshot": _serialize_market_snapshot(market_snapshot),
        "recent_annual_financials": [
            _serialize_financial_period(period) for period in annual_sorted[-5:]
        ],
        "recent_quarterly_financials": [
            _serialize_financial_period(period) for period in quarterly_sorted[-4:]
        ],
        "trend_summary": {
            "latest_annual_revenue_growth": (
                _growth_rate(latest_annual.revenue, previous_annual.revenue)
                if latest_annual and previous_annual
                else None
            ),
            "latest_annual_ebit_growth": (
                _growth_rate(latest_annual.ebit, previous_annual.ebit)
                if latest_annual and previous_annual
                else None
            ),
            "latest_annual_net_income_growth": (
                _growth_rate(latest_annual.net_income, previous_annual.net_income)
                if latest_annual and previous_annual
                else None
            ),
        },
        "missing_data_notes": _build_missing_data_notes(
            company_info=company_info,
            market_snapshot=market_snapshot,
            annual_financials=annual_financials,
            quarterly_financials=quarterly_financials,
        ),
    }


def load_context_source_data(ticker: str, refresh: bool = False) -> dict[str, Any]:
    """Load the raw normalized source data used to build the shared context bundle."""
    return load_valuation_context(ticker=ticker, refresh=refresh)


def load_dcf_market_seed(ticker: str, refresh: bool = False) -> dict[str, float | None]:
    """Load the exact source fields required to build a deterministic DCF input from local market data."""
    normalized_ticker = _normalize_ticker(ticker)
    market_snapshot = load_market_snapshot(normalized_ticker, refresh=refresh)
    annual_financials = load_annual_financials(normalized_ticker, refresh=refresh)
    latest = _latest_period(annual_financials)
    if latest is None:
        return {}

    current_revenue = latest.revenue
    current_ebit = latest.ebit if latest.ebit is not None else latest.operating_income
    shares_outstanding = (
        latest.shares_outstanding
        if latest.shares_outstanding is not None
        else (market_snapshot.shares_outstanding if market_snapshot else None)
    )

    if (
        current_revenue in (None, 0)
        or current_ebit is None
        or shares_outstanding in (None, 0)
        or latest.cash is None
        or latest.total_debt is None
    ):
        return {}

    return {
        "current_revenue": float(current_revenue),
        "current_ebit": float(current_ebit),
        "cash": float(latest.cash),
        "total_debt": float(latest.total_debt),
        "shares_outstanding": float(shares_outstanding),
        "current_price": market_snapshot.current_price if market_snapshot else None,
    }


def load_ddm_market_seed(ticker: str, refresh: bool = False) -> dict[str, float | None]:
    """Load the exact source fields required to build a deterministic DDM input from local market data."""
    normalized_ticker = _normalize_ticker(ticker)
    market_snapshot = load_market_snapshot(normalized_ticker, refresh=refresh)
    annual_financials = load_annual_financials(normalized_ticker, refresh=refresh)
    latest = _latest_period(annual_financials)
    if latest is None:
        return {}

    shares_outstanding = (
        latest.shares_outstanding
        if latest.shares_outstanding is not None
        else (market_snapshot.shares_outstanding if market_snapshot else None)
    )
    dividends_paid = latest.dividends_paid

    if shares_outstanding in (None, 0) or dividends_paid is None:
        return {}

    current_dividend_per_share = abs(float(dividends_paid)) / float(shares_outstanding)
    if current_dividend_per_share <= 0:
        return {}

    return {
        "current_dividend_per_share": current_dividend_per_share,
        "shares_outstanding": float(shares_outstanding),
        "current_price": market_snapshot.current_price if market_snapshot else None,
    }


def load_rim_market_seed(ticker: str, refresh: bool = False) -> dict[str, float | None]:
    """Load the exact source fields required to build a deterministic RIM input from local market data."""
    normalized_ticker = _normalize_ticker(ticker)
    market_snapshot = load_market_snapshot(normalized_ticker, refresh=refresh)
    annual_financials = load_annual_financials(normalized_ticker, refresh=refresh)
    latest = _latest_period(annual_financials)
    if latest is None:
        return {}

    shares_outstanding = (
        latest.shares_outstanding
        if latest.shares_outstanding is not None
        else (market_snapshot.shares_outstanding if market_snapshot else None)
    )
    shareholders_equity = latest.shareholders_equity

    if (
        shares_outstanding in (None, 0)
        or shareholders_equity is None
        or shareholders_equity <= 0
    ):
        return {}

    return {
        "current_book_value_per_share": float(shareholders_equity)
        / float(shares_outstanding),
        "shares_outstanding": float(shares_outstanding),
        "current_price": market_snapshot.current_price if market_snapshot else None,
    }


def _serialize_dcf_output(dcf_output: DCFOutput) -> dict[str, Any]:
    return {
        "selected_model": "dcf",
        "fair_value_per_share": dcf_output.fair_value_per_share,
        "current_price": dcf_output.current_price,
        "upside_downside_pct": dcf_output.upside_downside_pct,
        "enterprise_value": dcf_output.enterprise_value,
        "equity_value": dcf_output.equity_value,
        "terminal_value_pct_of_enterprise_value": dcf_output.terminal_value_pct_of_enterprise_value,
        "projection_years": len(dcf_output.projected_years),
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


def _serialize_ddm_output(ddm_output: DDMOutput) -> dict[str, Any]:
    return {
        "selected_model": "ddm",
        "fair_value_per_share": ddm_output.fair_value_per_share,
        "current_price": ddm_output.current_price,
        "upside_downside_pct": ddm_output.upside_downside_pct,
        "equity_value": ddm_output.equity_value,
        "terminal_value_pct_of_fair_value": ddm_output.terminal_value_pct_of_fair_value,
        "projection_years": len(ddm_output.projected_years),
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


def _serialize_rim_output(rim_output: RIMOutput) -> dict[str, Any]:
    return {
        "selected_model": "rim",
        "fair_value_per_share": rim_output.fair_value_per_share,
        "current_price": rim_output.current_price,
        "upside_downside_pct": rim_output.upside_downside_pct,
        "equity_value": rim_output.equity_value,
        "terminal_value_pct_of_fair_value": rim_output.terminal_value_pct_of_fair_value,
        "projection_years": len(rim_output.projected_years),
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


def _build_model_availability(
    ticker: str | None,
    refresh: bool,
) -> list[dict[str, Any]]:
    availability = {
        "dcf": {
            "name": "Discounted Cash Flow",
            "enabled": True,
            "reason": "DCF is implemented and available.",
        },
        "ddm": {
            "name": "Dividend Discount Model",
            "enabled": True,
            "reason": "DDM is implemented for dividend-paying businesses.",
        },
        "rim": {
            "name": "Residual Income Model",
            "enabled": True,
            "reason": "RIM is implemented for book-value and ROE-driven businesses.",
        },
    }

    if ticker is None:
        return [
            {"id": model_id, **data}
            for model_id, data in [
                ("dcf", availability["dcf"]),
                ("ddm", availability["ddm"]),
                ("rim", availability["rim"]),
            ]
        ]

    seeds = {
        "dcf": load_dcf_market_seed(ticker=ticker, refresh=refresh),
        "ddm": load_ddm_market_seed(ticker=ticker, refresh=refresh),
        "rim": load_rim_market_seed(ticker=ticker, refresh=refresh),
    }
    models: list[dict[str, Any]] = []
    for model_id in ["dcf", "ddm", "rim"]:
        seed = seeds[model_id]
        models.append(
            {
                "id": model_id,
                "name": availability[model_id]["name"],
                "enabled": availability[model_id]["enabled"],
                "reason": availability[model_id]["reason"],
                "input_data_available": bool(seed),
                "input_data_reason": (
                    "Required seed inputs are available for this ticker."
                    if seed
                    else "Required seed inputs are missing for this ticker."
                ),
            }
        )
    return models


def list_available_valuation_models(
    ticker: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """List the valuation models currently available to the application."""
    return {
        "ticker": _normalize_ticker(ticker) if ticker else None,
        "models": _build_model_availability(
            ticker=_normalize_ticker(ticker) if ticker else None,
            refresh=refresh,
        ),
    }


def run_dcf_valuation_tool(
    ticker: str,
    projection_years: int,
    revenue_growth_rates: list[float],
    ebit_margins: list[float],
    tax_rates: list[float],
    da_as_pct_revenue: list[float],
    capex_as_pct_revenue: list[float],
    nwc_as_pct_revenue: list[float],
    wacc: float,
    exit_multiple: float,
    refresh: bool = False,
) -> dict[str, Any]:
    """Run the DCF valuation tool from company-specific assumptions and return a serialized result."""
    market_seed = load_dcf_market_seed(ticker=ticker, refresh=refresh)
    if not market_seed:
        raise RuntimeError(
            "Required source fields for the DCF were missing from the latest annual data."
        )

    assumptions = DCFAssumptions(
        projection_years=int(projection_years),
        revenue_growth_rates=[float(value) for value in revenue_growth_rates],
        ebit_margins=[float(value) for value in ebit_margins],
        tax_rates=[float(value) for value in tax_rates],
        da_as_pct_revenue=[float(value) for value in da_as_pct_revenue],
        capex_as_pct_revenue=[float(value) for value in capex_as_pct_revenue],
        nwc_as_pct_revenue=[float(value) for value in nwc_as_pct_revenue],
        wacc=float(wacc),
        exit_multiple=float(exit_multiple),
    )

    dcf_input = DCFInput(
        market_data=DCFMarketData(
            current_revenue=float(market_seed["current_revenue"]),
            current_ebit=float(market_seed["current_ebit"]),
            tax_rate=float(tax_rates[0]),
            depreciation_amortization=float(market_seed["current_revenue"])
            * float(da_as_pct_revenue[0]),
            capex=float(market_seed["current_revenue"]) * float(capex_as_pct_revenue[0]),
            change_in_nwc=float(market_seed["current_revenue"])
            * float(nwc_as_pct_revenue[0]),
            cash=float(market_seed["cash"]),
            total_debt=float(market_seed["total_debt"]),
            shares_outstanding=float(market_seed["shares_outstanding"]),
            current_price=(
                float(market_seed["current_price"])
                if market_seed["current_price"] is not None
                else None
            ),
        ),
        assumptions=assumptions,
    )
    dcf_output = run_dcf_tool(dcf_input)
    return _serialize_dcf_output(dcf_output)


def run_ddm_valuation_tool(
    ticker: str,
    projection_years: int,
    dividend_growth_rates: list[float],
    cost_of_equity: float,
    terminal_growth_rate: float,
    refresh: bool = False,
) -> dict[str, Any]:
    """Run the DDM valuation tool from company-specific assumptions and return a serialized result."""
    market_seed = load_ddm_market_seed(ticker=ticker, refresh=refresh)
    if not market_seed:
        raise RuntimeError(
            "Required source fields for the DDM were missing from the latest annual data."
        )

    assumptions = DDMAssumptions(
        projection_years=int(projection_years),
        dividend_growth_rates=[float(value) for value in dividend_growth_rates],
        cost_of_equity=float(cost_of_equity),
        terminal_growth_rate=float(terminal_growth_rate),
    )

    ddm_input = DDMInput(
        market_data=DDMMarketData(
            current_dividend_per_share=float(market_seed["current_dividend_per_share"]),
            shares_outstanding=float(market_seed["shares_outstanding"]),
            current_price=(
                float(market_seed["current_price"])
                if market_seed["current_price"] is not None
                else None
            ),
        ),
        assumptions=assumptions,
    )
    ddm_output = run_ddm_tool(ddm_input)
    return _serialize_ddm_output(ddm_output)


def run_rim_valuation_tool(
    ticker: str,
    projection_years: int,
    return_on_equity: list[float],
    payout_ratios: list[float],
    cost_of_equity: float,
    terminal_return_on_equity: float,
    terminal_growth_rate: float,
    refresh: bool = False,
) -> dict[str, Any]:
    """Run the RIM valuation tool from company-specific assumptions and return a serialized result."""
    market_seed = load_rim_market_seed(ticker=ticker, refresh=refresh)
    if not market_seed:
        raise RuntimeError(
            "Required source fields for the RIM were missing from the latest annual data."
        )

    assumptions = RIMAssumptions(
        projection_years=int(projection_years),
        return_on_equity=[float(value) for value in return_on_equity],
        payout_ratios=[float(value) for value in payout_ratios],
        cost_of_equity=float(cost_of_equity),
        terminal_return_on_equity=float(terminal_return_on_equity),
        terminal_growth_rate=float(terminal_growth_rate),
    )

    rim_input = RIMInput(
        market_data=RIMMarketData(
            current_book_value_per_share=float(
                market_seed["current_book_value_per_share"]
            ),
            shares_outstanding=float(market_seed["shares_outstanding"]),
            current_price=(
                float(market_seed["current_price"])
                if market_seed["current_price"] is not None
                else None
            ),
        ),
        assumptions=assumptions,
    )
    rim_output = run_rim_tool(rim_input)
    return _serialize_rim_output(rim_output)


# TODO: Add transcript-loading tools here when the transcript data layer is ready.
# TODO: Add SEC/document tools here when the qualitative research layer is ready.
