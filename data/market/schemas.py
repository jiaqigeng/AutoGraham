from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class CompanyInfo:
    """Basic company identity and metadata."""

    ticker: str
    company_name: str | None = None
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    currency: str | None = None


@dataclass(slots=True)
class MarketSnapshot:
    """Current market-related snapshot data."""

    current_price: float | None = None
    market_cap: float | None = None
    enterprise_value: float | None = None
    shares_outstanding: float | None = None
    beta: float | None = None
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    dividend_yield: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None


@dataclass(slots=True)
class PriceBar:
    """One row of historical price data."""

    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None


@dataclass(slots=True)
class FinancialPeriod:
    """One period-centered financial record for display and valuation."""

    period_end: date
    period_type: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None

    revenue: float | None = None
    gross_profit: float | None = None
    ebit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    depreciation_amortization: float | None = None
    interest_expense: float | None = None
    income_tax_expense: float | None = None
    dividends_paid: float | None = None

    capex: float | None = None
    change_in_nwc: float | None = None
    operating_cash_flow: float | None = None
    free_cash_flow: float | None = None

    cash: float | None = None
    total_debt: float | None = None
    shareholders_equity: float | None = None
    shares_outstanding: float | None = None
    current_assets: float | None = None
    current_liabilities: float | None = None


@dataclass(slots=True)
class MarketDataBundle:
    """Top-level shared market data object returned by the market service."""

    company_info: CompanyInfo | None = None
    market_snapshot: MarketSnapshot | None = None
    price_history: list[PriceBar] = field(default_factory=list)
    annual_financials: list[FinancialPeriod] = field(default_factory=list)
    quarterly_financials: list[FinancialPeriod] = field(default_factory=list)
