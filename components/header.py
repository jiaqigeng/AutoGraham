from __future__ import annotations


def _safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		numeric_value = float(value)
	except (TypeError, ValueError):
		return 0.0
	if numeric_value != numeric_value:
		return 0.0
	return numeric_value


def _format_market_cap(value: object) -> str:
	market_cap = _safe_number(value)
	if market_cap <= 0:
		return "N/A"
	if market_cap >= 1_000_000_000_000:
		return f"${market_cap / 1_000_000_000_000:,.2f}T"
	if market_cap >= 1_000_000_000:
		return f"${market_cap / 1_000_000_000:,.2f}B"
	if market_cap >= 1_000_000:
		return f"${market_cap / 1_000_000:,.2f}M"
	return f"${market_cap:,.2f}"


def _format_price(value: object) -> str:
	price = _safe_number(value)
	if price <= 0:
		return "N/A"
	return f"${price:,.2f}"


def _format_ratio(value: object) -> str:
	ratio = _safe_number(value)
	if ratio <= 0:
		return "N/A"
	return f"{ratio:,.2f}"


def _format_eps(value: object) -> str:
	eps = _safe_number(value)
	if eps == 0:
		return "N/A"
	return f"${eps:,.2f}"


def _format_dividend_yield(value: object) -> str:
	if value == "N/A" or value is None:
		return "N/A"
	dividend_yield = _safe_number(value)
	if dividend_yield < 0:
		return "N/A"
	if dividend_yield > 0.25:
		dividend_yield = dividend_yield / 100
	return f"{dividend_yield:.2%}"


def render_metrics_header(info_dict) -> None:
	import streamlit as st

	overview_metrics = {
		"current_price": _format_price(info_dict.get("currentPrice", info_dict.get("regularMarketPrice", "N/A"))),
		"market_cap": _format_market_cap(info_dict.get("marketCap", "N/A")),
		"trailing_pe": _format_ratio(info_dict.get("trailingPE", "N/A")),
		"forward_pe": _format_ratio(info_dict.get("forwardPE", "N/A")),
		"trailing_eps": _format_eps(info_dict.get("trailingEps", "N/A")),
		"dividend_yield": _format_dividend_yield(info_dict.get("dividendYield", "N/A")),
		"fifty_two_week_high": _format_price(info_dict.get("fiftyTwoWeekHigh", "N/A")),
		"fifty_two_week_low": _format_price(info_dict.get("fiftyTwoWeekLow", "N/A")),
	}

	col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
	col1.metric(label="Current Price", value=overview_metrics["current_price"])
	col2.metric(label="Market Cap", value=overview_metrics["market_cap"])
	col3.metric(label="Trailing P/E", value=overview_metrics["trailing_pe"])
	col4.metric(label="Forward P/E", value=overview_metrics["forward_pe"])
	col5.metric(label="EPS (TTM)", value=overview_metrics["trailing_eps"])
	col6.metric(label="Div Yield", value=overview_metrics["dividend_yield"])
	col7.metric(label="52W High", value=overview_metrics["fifty_two_week_high"])
	col8.metric(label="52W Low", value=overview_metrics["fifty_two_week_low"])