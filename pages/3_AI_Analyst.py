from __future__ import annotations

import streamlit as st

from data import get_cached_stock_data
from ui_components import inject_global_styles, render_ai_report, render_ticker_input
from ui_components.valuation_result import render_ai_summary
from workflows import run_ai_valuation


def _analysis_state_key(ticker: str) -> str:
	return f"ai_analysis::{ticker.strip().upper()}"


st.set_page_config(page_title="AI Analyst", layout="wide")
inject_global_styles()

st.title("AI Analyst")
ticker = render_ticker_input(default=st.session_state.get("selected_ticker", "AAPL"))
if not ticker:
	st.info("Enter a stock ticker to run the AI analyst workflow.")
	st.stop()

try:
	stock_data = get_cached_stock_data(ticker)
except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

analysis_focus = st.text_area(
	"Analysis focus",
	value=(
		"Focus on competitive positioning, valuation gaps, profitability quality, "
		"and which stock offers the best margin of safety."
	),
	height=120,
	key="ai_analysis_focus",
)

if st.button("Run AI Analyst", key="run_ai_analyst"):
	state_key = _analysis_state_key(ticker)
	st.session_state.pop(state_key, None)
	with st.spinner(f"Researching {ticker} and running the valuation workflow..."):
		try:
			result = run_ai_valuation(
				ticker,
				stock_data,
				model_name=st.session_state.get("agent_model") or None,
				analysis_focus=analysis_focus,
			)
			st.session_state[state_key] = {"result": result, "error": None}
		except Exception as exc:
			st.session_state[state_key] = {"result": None, "error": str(exc)}

analysis_state = st.session_state.get(_analysis_state_key(ticker), {})
if analysis_state.get("error"):
	st.error(analysis_state["error"])

if analysis_state.get("result"):
	result = analysis_state["result"]
	if result.get("valuation_pick"):
		render_ai_summary(result["valuation_pick"])
	st.markdown(
		render_ai_report(
			result.get("memo_markdown", ""),
			valuation_pick=result.get("valuation_pick"),
			explanation_markdown=result.get("explanation_markdown"),
		),
		unsafe_allow_html=True,
	)
else:
	st.info("Run the AI analyst to generate research, structured assumptions, a deterministic valuation, and an explanation.")
