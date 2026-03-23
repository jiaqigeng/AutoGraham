from __future__ import annotations

import streamlit as st

from data import get_cached_stock_data
from ui_components import inject_global_styles, render_income_waterfall, render_metrics_header, render_page_hero, render_ticker_input


inject_global_styles()

render_page_hero(
	"",
	"Track the live quote, valuation multiples, and quarterly earnings bridge in the same polished workspace used across Valuation Lab and AI Analyst.",
	eyebrow="Live market dashboard",
	pills=["Quote snapshot", "Quarterly earnings bridge", "Consistent research UI"],
)

with st.container():
	st.markdown('<div class="ag-controls-card-anchor"></div>', unsafe_allow_html=True)
	ticker = render_ticker_input(label="Ticker symbol", default=st.session_state.get("selected_ticker", "AAPL"))

if not ticker:
	st.info("Enter a stock ticker to load the market view.")
	st.stop()

try:
	stock_data = get_cached_stock_data(ticker)
except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

render_metrics_header(stock_data.info, ticker=ticker)
render_income_waterfall(stock_data.quarterly_income_stmt, annual_income_stmt=stock_data.annual_income_stmt)
