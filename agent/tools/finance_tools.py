from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent
from typing import Any, Mapping

from data.company_profile import info_supports_analysis
from data.cache import get_cached_stock_data
from data.financial_statements import extract_latest_quarter_metrics
from data.normalization import format_compact_currency, format_percent, format_price, format_ratio
from valuation.common import default_valuation_inputs, safe_number

try:
	from langchain_core.tools import tool
except ImportError:
	def tool(*decorator_args, **decorator_kwargs):
		def decorator(func):
			return func

		if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
			return decorator(decorator_args[0])
		return decorator


@dataclass(frozen=True, slots=True)
class ValuationMetricsData:
	ticker: str
	current_price: float
	market_cap: float
	trailing_pe: float
	forward_pe: float
	trailing_eps: float
	dividend_yield: float | None


@dataclass(frozen=True, slots=True)
class IncomeStatementData:
	ticker: str
	period: str
	revenue: float
	gross_profit: float
	operating_income: float
	operating_expenses: float
	net_profit: float
	gross_margin: float | None
	operating_margin: float | None
	net_margin: float | None


@dataclass(frozen=True, slots=True)
class CashFlowHealthData:
	ticker: str
	free_cash_flow: float
	total_cash: float
	total_debt: float
	net_cash: float


@dataclass(frozen=True, slots=True)
class CompanyProfileData:
	ticker: str
	name: str
	sector: str
	industry: str
	summary: str


def resolve_stock_info(stock_data_or_info: Any) -> Mapping[str, Any]:
	"""Return the info mapping from either a stock bundle or a raw dict."""

	return getattr(stock_data_or_info, "info", stock_data_or_info) or {}


def build_company_snapshot(ticker: str, stock_data: Any | None = None) -> dict[str, Any]:
	"""Build a structured snapshot for broad research and parameter assembly."""

	stock_bundle = stock_data or get_cached_stock_data(ticker)
	info = resolve_stock_info(stock_bundle)
	defaults = default_valuation_inputs(
		info,
		annual_cashflow=getattr(stock_bundle, "annual_cashflow", None),
		annual_balance_sheet=getattr(stock_bundle, "annual_balance_sheet", None),
		annual_income_stmt=getattr(stock_bundle, "annual_income_stmt", None),
	)
	return {
		"ticker": ticker.strip().upper(),
		"company_name": str(info.get("longName") or info.get("shortName") or ticker.strip().upper()),
		"sector": str(info.get("sector") or "N/A"),
		"industry": str(info.get("industry") or "N/A"),
		"website": str(info.get("website") or ""),
		"current_price": defaults["current_price"],
		"market_cap": safe_number(info.get("marketCap")),
		"dividend_per_share": defaults["dividend_per_share"],
		"book_value_per_share": defaults["book_value_per_share"],
		"return_on_equity": defaults["return_on_equity"],
		"payout_ratio": defaults["payout_ratio"],
		"starting_fcff": defaults["starting_fcff"],
		"starting_fcfe": defaults["starting_fcfe"],
		"wacc": defaults["wacc"],
		"cost_of_equity": defaults["cost_of_equity"],
		"stable_growth": defaults["stable_growth"],
		"high_growth": defaults["high_growth"],
	}


def build_source_links(ticker: str, stock_data: Any | None = None) -> list[str]:
	"""Return a default source-link set from company metadata."""

	clean_ticker, stock_bundle = _load_stock_data(ticker, stock_data=stock_data)
	info = resolve_stock_info(stock_bundle)
	links = [f"https://finance.yahoo.com/quote/{clean_ticker}"]
	website = str(info.get("website") or "")
	if website:
		links.append(website)
	return links


def _unavailable_peer_message(ticker: str, reason: str) -> str:
	return (
		f"DATA_UNAVAILABLE for {ticker}: {reason} "
		"Exclude this ticker from the peer set and continue the analysis with other public competitors."
	)


def _clean_ticker(ticker: str) -> str:
	return ticker.strip().upper()


def _load_stock_data(ticker: str, stock_data: Any | None = None) -> tuple[str, Any]:
	clean_ticker = _clean_ticker(ticker)
	return clean_ticker, stock_data or get_cached_stock_data(clean_ticker)


def _load_supported_equity_info(
	ticker: str,
	*,
	stock_data: Any | None = None,
) -> tuple[str, Any, Mapping[str, Any]]:
	clean_ticker, stock_bundle = _load_stock_data(ticker, stock_data=stock_data)
	info = resolve_stock_info(stock_bundle)
	if not info_supports_analysis(info):
		raise ValueError("Yahoo Finance does not expose a valid equity profile for this ticker.")
	return clean_ticker, stock_bundle, info


def get_valuation_metrics_data(ticker: str, stock_data: Any | None = None) -> ValuationMetricsData:
	"""Fetch structured valuation metrics for a publicly traded company."""

	try:
		clean_ticker, _, info = _load_supported_equity_info(
			ticker,
			stock_data=stock_data,
		)
	except ValueError:
		raise
	except Exception as exc:
		raise ValueError(f"Unable to load valuation data from Yahoo Finance ({exc}).") from exc

	return ValuationMetricsData(
		ticker=clean_ticker,
		current_price=safe_number(info.get("currentPrice", info.get("regularMarketPrice"))),
		market_cap=safe_number(info.get("marketCap")),
		trailing_pe=safe_number(info.get("trailingPE")),
		forward_pe=safe_number(info.get("forwardPE")),
		trailing_eps=safe_number(info.get("trailingEps")),
		dividend_yield=info.get("dividendYield"),
	)


def format_valuation_metrics_text(metrics: ValuationMetricsData) -> str:
	"""Render structured valuation metrics into an LLM-friendly text block."""

	return dedent(
		f"""
		Valuation Metrics for {metrics.ticker}:
		- Current Price: {format_price(metrics.current_price)}
		- Market Cap: {format_compact_currency(metrics.market_cap)}
		- Trailing P/E: {format_ratio(metrics.trailing_pe)}
		- Forward P/E: {format_ratio(metrics.forward_pe)}
		- Trailing EPS: {format_price(metrics.trailing_eps)}
		- Dividend Yield: {format_percent(metrics.dividend_yield) if metrics.dividend_yield is not None else 'N/A'}
		"""
	).strip()


def get_income_statement_data(ticker: str, stock_data: Any | None = None) -> IncomeStatementData:
	"""Fetch structured latest quarterly income-statement metrics for a company."""

	try:
		clean_ticker, stock_bundle = _load_stock_data(ticker, stock_data=stock_data)
		metrics = extract_latest_quarter_metrics(stock_bundle.quarterly_income_stmt)
	except Exception as exc:
		raise ValueError(str(exc)) from exc

	return IncomeStatementData(
		ticker=clean_ticker,
		period=str(metrics["period"]),
		revenue=safe_number(metrics["revenue"]),
		gross_profit=safe_number(metrics["gross_profit"]),
		operating_income=safe_number(metrics["operating_income"]),
		operating_expenses=safe_number(metrics["operating_expenses"]),
		net_profit=safe_number(metrics["net_profit"]),
		gross_margin=metrics["gross_margin"],
		operating_margin=metrics["operating_margin"],
		net_margin=metrics["net_margin"],
	)


def format_income_statement_text(metrics: IncomeStatementData) -> str:
	"""Render structured income-statement metrics into an LLM-friendly text block."""

	return dedent(
		f"""
		Latest Quarterly Income Statement for {metrics.ticker} ({metrics.period}):
		- Revenue: {format_compact_currency(metrics.revenue)}
		- Gross Profit: {format_compact_currency(metrics.gross_profit)}
		- Operating Income: {format_compact_currency(metrics.operating_income)}
		- Operating Expenses: {format_compact_currency(metrics.operating_expenses)}
		- Net Profit: {format_compact_currency(metrics.net_profit)}
		- Gross Margin: {f"{metrics.gross_margin:.2%}" if metrics.gross_margin is not None else 'N/A'}
		- Operating Margin: {f"{metrics.operating_margin:.2%}" if metrics.operating_margin is not None else 'N/A'}
		- Net Margin: {f"{metrics.net_margin:.2%}" if metrics.net_margin is not None else 'N/A'}
		"""
	).strip()


def get_cash_flow_health_data(ticker: str, stock_data: Any | None = None) -> CashFlowHealthData:
	"""Fetch structured cash-flow and balance-sheet safety metrics for a company."""

	try:
		clean_ticker, _, info = _load_supported_equity_info(
			ticker,
			stock_data=stock_data,
		)
	except ValueError:
		raise
	except Exception as exc:
		raise ValueError(f"Unable to load cash flow data from Yahoo Finance ({exc}).") from exc

	total_cash = safe_number(info.get("totalCash"))
	total_debt = safe_number(info.get("totalDebt"))
	return CashFlowHealthData(
		ticker=clean_ticker,
		free_cash_flow=safe_number(info.get("freeCashflow")),
		total_cash=total_cash,
		total_debt=total_debt,
		net_cash=total_cash - total_debt,
	)


def format_cash_flow_health_text(metrics: CashFlowHealthData) -> str:
	"""Render structured cash-flow health metrics into an LLM-friendly text block."""

	return dedent(
		f"""
		Cash Flow Health for {metrics.ticker}:
		- Free Cash Flow (FCFE): {format_compact_currency(metrics.free_cash_flow)}
		- Total Cash: {format_compact_currency(metrics.total_cash)}
		- Total Debt: {format_compact_currency(metrics.total_debt)}
		- Net Cash / (Debt): {format_compact_currency(metrics.net_cash)}
		"""
	).strip()


def get_company_profile_data(ticker: str, stock_data: Any | None = None) -> CompanyProfileData:
	"""Fetch a structured compact business-profile summary for broad research."""

	try:
		clean_ticker, _, info = _load_supported_equity_info(
			ticker,
			stock_data=stock_data,
		)
	except ValueError:
		raise
	except Exception as exc:
		raise ValueError(f"Unable to load company profile ({exc}).") from exc

	return CompanyProfileData(
		ticker=clean_ticker,
		name=str(info.get("longName") or info.get("shortName") or clean_ticker),
		sector=str(info.get("sector") or "N/A"),
		industry=str(info.get("industry") or "N/A"),
		summary=str(info.get("longBusinessSummary") or "N/A"),
	)


def format_company_profile_text(profile: CompanyProfileData) -> str:
	"""Render structured company-profile data into an LLM-friendly text block."""

	return dedent(
		f"""
		Company Profile for {profile.ticker}:
		- Name: {profile.name}
		- Sector: {profile.sector}
		- Industry: {profile.industry}
		- Summary: {profile.summary[:1200]}
		"""
	).strip()


@tool
def get_valuation_metrics(ticker: str) -> str:
	"""Fetch valuation metrics for a publicly traded company."""

	try:
		return format_valuation_metrics_text(get_valuation_metrics_data(ticker))
	except ValueError as exc:
		return _unavailable_peer_message(_clean_ticker(ticker), str(exc))


@tool
def get_income_statement(ticker: str) -> str:
	"""Fetch the latest quarterly income statement metrics for a company."""

	try:
		return format_income_statement_text(get_income_statement_data(ticker))
	except ValueError as exc:
		return _unavailable_peer_message(_clean_ticker(ticker), str(exc))


@tool
def get_cash_flow_health(ticker: str) -> str:
	"""Fetch cash flow and balance sheet safety metrics for a company."""

	try:
		return format_cash_flow_health_text(get_cash_flow_health_data(ticker))
	except ValueError as exc:
		return _unavailable_peer_message(_clean_ticker(ticker), str(exc))


@tool
def get_company_profile_text(ticker: str) -> str:
	"""Fetch a compact business-profile summary for broad research."""

	try:
		return format_company_profile_text(get_company_profile_data(ticker))
	except ValueError as exc:
		return _unavailable_peer_message(_clean_ticker(ticker), str(exc))


__all__ = [
	"CashFlowHealthData",
	"CompanyProfileData",
	"IncomeStatementData",
	"ValuationMetricsData",
	"build_company_snapshot",
	"build_source_links",
	"format_cash_flow_health_text",
	"format_company_profile_text",
	"format_income_statement_text",
	"format_valuation_metrics_text",
	"get_cash_flow_health",
	"get_cash_flow_health_data",
	"get_company_profile_data",
	"get_company_profile_text",
	"get_income_statement",
	"get_income_statement_data",
	"get_valuation_metrics",
	"get_valuation_metrics_data",
	"resolve_stock_info",
]
