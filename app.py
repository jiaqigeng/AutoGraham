from __future__ import annotations

import streamlit as st

from ui_components.header import inject_global_styles, render_ticker_input


st.set_page_config(page_title="AutoGraham", layout="wide")
inject_global_styles()

st.title("AutoGraham")
st.caption("Python + Streamlit equity valuation workspace with deterministic valuation math and an AI-guided analyst flow.")

ticker = render_ticker_input(default="AAPL")
if ticker:
	st.success(f"Active ticker: {ticker}")
else:
	st.info("Enter a stock ticker, then open Market View, Valuation Lab, or AI Analyst from the page navigation.")

st.markdown(
	"""
	### Workspace Structure
	- `Market View` focuses on finance data visualization.
	- `Valuation Lab` keeps the valuation math deterministic in Python.
	- `AI Analyst` lets the agent research, choose structured assumptions, run Python valuation functions, and explain the result.
	"""
)
