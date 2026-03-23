from __future__ import annotations

import streamlit as st

from data import get_cached_stock_data
from ui_components import inject_global_styles, render_ai_report, render_page_hero, render_ticker_input
from workflows import run_ai_valuation


def _analysis_state_key(ticker: str) -> str:
	return f"ai_analysis::{ticker.strip().upper()}"


inject_global_styles()

render_page_hero(
	"",
	"Research the business, choose structured assumptions, and generate a deterministic valuation with an explainable narrative.",
	eyebrow="AI-guided valuation workflow",
	pills=["Explainable output", "Deterministic math", "Structured assumptions"],
)

with st.container():
	st.markdown('<div class="ag-controls-card-anchor"></div>', unsafe_allow_html=True)
	controls_col, action_col = st.columns([2.6, 1.0], vertical_alignment="bottom")
	with controls_col:
		ticker = render_ticker_input(label="Ticker symbol", default=st.session_state.get("selected_ticker", "AAPL"))
	with action_col:
		run_requested = st.button("Run AI Analyst", key="run_ai_analyst", type="primary", use_container_width=True)

if not ticker:
	st.info("Enter a stock ticker to run the AI analyst workflow.")
	st.stop()

try:
	stock_data = get_cached_stock_data(ticker)
except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

if run_requested:
	state_key = _analysis_state_key(ticker)
	st.session_state.pop(state_key, None)
	with st.spinner(f"Researching {ticker} and running the valuation workflow..."):
		try:
			result = run_ai_valuation(
				ticker,
				stock_data,
				model_name=st.session_state.get("agent_model") or None,
			)
			st.session_state[state_key] = {"result": result, "error": None}
		except Exception as exc:
			st.session_state[state_key] = {"result": None, "error": str(exc)}

analysis_state = st.session_state.get(_analysis_state_key(ticker), {})
if analysis_state.get("error"):
	st.error(analysis_state["error"])

if analysis_state.get("result"):
	result = analysis_state["result"]
	st.markdown(
		render_ai_report(
			result.get("memo_markdown", ""),
			ticker=result.get("ticker") or ticker,
			company_name=result.get("company_name"),
			model_selection=result.get("model_selection"),
			parameter_payload=result.get("parameter_payload"),
			valuation_pick=result.get("valuation_pick"),
			explanation_markdown=result.get("explanation_markdown"),
			source_links=result.get("source_links"),
			confidence=result.get("confidence"),
		),
		unsafe_allow_html=True,
	)
