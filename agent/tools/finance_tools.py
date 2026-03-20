from __future__ import annotations

from textwrap import dedent
from typing import Any, Mapping

from data.company_profile import info_supports_analysis
from data.financial_statements import extract_latest_quarter_metrics
from data.market_data import fetch_stock_data
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


def resolve_stock_info(stock_data_or_info: Any) -> Mapping[str, Any]:
	"""Return the info mapping from either a stock bundle or a raw dict."""

	return getattr(stock_data_or_info, "info", stock_data_or_info) or {}


def build_company_snapshot(ticker: str, stock_data: Any | None = None) -> dict[str, Any]:
	"""Build a structured snapshot for broad research and parameter assembly."""

	stock_bundle = stock_data or fetch_stock_data(ticker.strip().upper())
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

	snapshot = build_company_snapshot(ticker, stock_data)
	links = [f"https://finance.yahoo.com/quote/{snapshot['ticker']}"]
	if snapshot.get("website"):
		links.append(str(snapshot["website"]))
	return links


def _unavailable_peer_message(ticker: str, reason: str) -> str:
	return (
		f"DATA_UNAVAILABLE for {ticker}: {reason} "
		"Exclude this ticker from the peer set and continue the analysis with other public competitors."
	)


@tool
def get_valuation_metrics(ticker: str) -> str:
	"""Fetch valuation metrics for a publicly traded company."""

	clean_ticker = ticker.strip().upper()
	try:
		stock_data = fetch_stock_data(clean_ticker)
		info = stock_data.info
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, f"Unable to load valuation data from Yahoo Finance ({exc}).")

	if not info_supports_analysis(info):
		return _unavailable_peer_message(clean_ticker, "Yahoo Finance does not expose a valid equity profile for this ticker.")

	return dedent(
		f"""
		Valuation Metrics for {clean_ticker}:
		- Current Price: {format_price(info.get('currentPrice', info.get('regularMarketPrice')))}
		- Market Cap: {format_compact_currency(info.get('marketCap'))}
		- Trailing P/E: {format_ratio(info.get('trailingPE'))}
		- Forward P/E: {format_ratio(info.get('forwardPE'))}
		- Trailing EPS: {format_price(info.get('trailingEps'))}
		- Dividend Yield: {format_percent(info.get('dividendYield')) if info.get('dividendYield') is not None else 'N/A'}
		"""
	).strip()


@tool
def get_income_statement(ticker: str) -> str:
	"""Fetch the latest quarterly income statement metrics for a company."""

	clean_ticker = ticker.strip().upper()
	try:
		metrics = extract_latest_quarter_metrics(fetch_stock_data(clean_ticker).quarterly_income_stmt)
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, str(exc))

	return dedent(
		f"""
		Latest Quarterly Income Statement for {clean_ticker} ({metrics['period']}):
		- Revenue: {format_compact_currency(metrics['revenue'])}
		- Gross Profit: {format_compact_currency(metrics['gross_profit'])}
		- Operating Expenses: {format_compact_currency(metrics['operating_expenses'])}
		- Net Profit: {format_compact_currency(metrics['net_profit'])}
		- Gross Margin: {f"{metrics['gross_margin']:.2%}" if metrics['gross_margin'] is not None else 'N/A'}
		- Net Margin: {f"{metrics['net_margin']:.2%}" if metrics['net_margin'] is not None else 'N/A'}
		"""
	).strip()


@tool
def get_cash_flow_health(ticker: str) -> str:
	"""Fetch cash flow and balance sheet safety metrics for a company."""

	clean_ticker = ticker.strip().upper()
	try:
		stock_data = fetch_stock_data(clean_ticker)
		info = stock_data.info
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, f"Unable to load cash flow data from Yahoo Finance ({exc}).")

	if not info_supports_analysis(info):
		return _unavailable_peer_message(clean_ticker, "Yahoo Finance does not expose a valid equity profile for this ticker.")

	net_cash = safe_number(info.get("totalCash")) - safe_number(info.get("totalDebt"))
	return dedent(
		f"""
		Cash Flow Health for {clean_ticker}:
		- Free Cash Flow (FCFE): {format_compact_currency(info.get('freeCashflow'))}
		- Total Cash: {format_compact_currency(info.get('totalCash'))}
		- Total Debt: {format_compact_currency(info.get('totalDebt'))}
		- Net Cash / (Debt): {format_compact_currency(net_cash)}
		"""
	).strip()


@tool
def get_company_profile_text(ticker: str) -> str:
	"""Fetch a compact business-profile summary for broad research."""

	clean_ticker = ticker.strip().upper()
	try:
		info = fetch_stock_data(clean_ticker).info
	except Exception as exc:
		return _unavailable_peer_message(clean_ticker, f"Unable to load company profile ({exc}).")
	if not info_supports_analysis(info):
		return _unavailable_peer_message(clean_ticker, "Yahoo Finance does not expose a valid equity profile for this ticker.")
	return dedent(
		f"""
		Company Profile for {clean_ticker}:
		- Name: {info.get('longName') or info.get('shortName') or clean_ticker}
		- Sector: {info.get('sector') or 'N/A'}
		- Industry: {info.get('industry') or 'N/A'}
		- Summary: {str(info.get('longBusinessSummary') or 'N/A')[:1200]}
		"""
	).strip()
