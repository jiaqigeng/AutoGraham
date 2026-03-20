from __future__ import annotations

import streamlit as st

from data import get_cached_stock_data
from ui_components import inject_global_styles, render_ticker_input, render_valuation_lab


st.set_page_config(page_title="Valuation Lab", layout="wide")
inject_global_styles()

st.title("Valuation Lab")
ticker = render_ticker_input(default=st.session_state.get("selected_ticker", "AAPL"))
if not ticker:
	st.info("Enter a stock ticker to open the valuation lab.")
	st.stop()

try:
	stock_data = get_cached_stock_data(ticker)
except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

render_valuation_lab(stock_data)
