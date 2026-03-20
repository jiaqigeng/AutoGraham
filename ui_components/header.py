from __future__ import annotations

from pathlib import Path

import streamlit as st

from data.financial_statements import build_income_waterfall_figure, format_period_label
from data.normalization import format_market_cap, format_percent, format_price, format_ratio


def inject_global_styles() -> None:
	css_path = Path(__file__).resolve().parents[1] / "assets" / "styles.css"
	if css_path.exists():
		st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def render_ticker_input(label: str = "Stock ticker", default: str = "") -> str:
	current_value = st.session_state.get("selected_ticker", default)
	ticker = st.text_input(label, value=current_value).strip().upper()
	st.session_state["selected_ticker"] = ticker
	return ticker


def render_metrics_header(info_dict) -> None:
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


def render_income_waterfall(income_stmt) -> None:
	if income_stmt is None or income_stmt.empty:
		st.warning("Quarterly income statement data is unavailable for this ticker.")
		return

	ordered_columns = list(sorted(income_stmt.columns, reverse=True))
	period_labels = [format_period_label(column) for column in ordered_columns]
	selected_label = st.selectbox("Quarter", period_labels, key="quarterly_period")
	selected_column = ordered_columns[period_labels.index(selected_label)]
	figure, _ = build_income_waterfall_figure(income_stmt, selected_column=selected_column)
	st.plotly_chart(figure, use_container_width=True)
