from __future__ import annotations

from utils.formatting import format_market_cap, format_percent, format_price, format_ratio


def render_metrics_header(info_dict) -> None:
	import streamlit as st

	overview_metrics = {
		"current_price": format_price(info_dict.get("currentPrice", info_dict.get("regularMarketPrice", "N/A"))),
		"market_cap": format_market_cap(info_dict.get("marketCap", "N/A")),
		"trailing_pe": format_ratio(info_dict.get("trailingPE", "N/A")),
		"forward_pe": format_ratio(info_dict.get("forwardPE", "N/A")),
		"trailing_eps": format_price(info_dict.get("trailingEps", "N/A")),
		"dividend_yield": format_percent(info_dict.get("dividendYield", "N/A")),
		"fifty_two_week_high": format_price(info_dict.get("fiftyTwoWeekHigh", "N/A")),
		"fifty_two_week_low": format_price(info_dict.get("fiftyTwoWeekLow", "N/A")),
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
