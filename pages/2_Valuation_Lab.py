from __future__ import annotations

import streamlit as st

from data import get_cached_stock_data
from ui_components import inject_global_styles, render_page_hero, render_ticker_input, render_valuation_lab


inject_global_styles()

render_page_hero(
	"",
	"Choose a valuation framework, tune the few assumptions that matter, and compare intrinsic value against the live market price.",
	eyebrow="Deterministic valuation workspace",
	pills=["Manual assumption builder", "Live Yahoo inputs", "Framework-by-framework analysis"],
)

with st.container():
	st.markdown('<div class="ag-controls-card-anchor"></div>', unsafe_allow_html=True)
	ticker = render_ticker_input(label="Ticker symbol", default=st.session_state.get("selected_ticker", "AAPL"))

if not ticker:
	st.info("Enter a stock ticker to open the valuation lab.")
	st.stop()

try:
	stock_data = get_cached_stock_data(ticker)
except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

render_valuation_lab(stock_data)
