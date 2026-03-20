from __future__ import annotations

import streamlit as st

from data import get_cached_stock_data
from ui_components.header import inject_global_styles, render_income_waterfall, render_metrics_header, render_ticker_input


st.set_page_config(page_title="Market View", layout="wide")
inject_global_styles()

st.title("Market View")
ticker = render_ticker_input(default=st.session_state.get("selected_ticker", "AAPL"))
if not ticker:
	st.info("Enter a stock ticker to load the market view.")
	st.stop()

try:
	stock_data = get_cached_stock_data(ticker)
except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

render_metrics_header(stock_data.info)
render_income_waterfall(stock_data.quarterly_income_stmt)
