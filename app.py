import streamlit as st
from agent.llm_service import run_ai_analysis
from components.ai_report import render_ai_report
from components.dcf_fcfe import render_dcf_calculator
from components.header import render_metrics_header
from components.theme import inject_global_styles
from components.waterfall import render_waterfall_chart
from data.yf_api import fetch_stock_data


st.set_page_config(layout="wide")
inject_global_styles()



def _analysis_state_key(ticker: str) -> str:
	return f"ai_analysis::{ticker.strip().upper()}"

st.title("AutoGraham")
st.caption("Modular equity research workspace for financials, valuation, and future AI analysis.")

ticker = st.text_input("Stock ticker", value="").strip().upper()
if not ticker:
	st.info("Enter a stock ticker to load the dashboard.")
	st.stop()

try:
	stock_data = fetch_stock_data(ticker)

except Exception as exc:
	st.error(f"Unable to load data for {ticker}: {exc}")
	st.stop()

tab1, tab2, tab3 = st.tabs(["Financials Dashboard", "Valuation Lab", "AI Analyst"])

with tab1:
	render_metrics_header(stock_data.info)
	render_waterfall_chart(stock_data.quarterly_income_stmt)

with tab2:
	render_dcf_calculator(stock_data)

with tab3:
	st.subheader("AI Analyst")
	analysis_focus = st.text_area(
		"Analysis focus",
		value=(
			"Focus on competitive positioning, valuation gaps, profitability quality, "
			"and which stock offers the best margin of safety."
		),
		height=120,
		key="ai_analysis_focus",
	)

	if st.button("Run Competitor Analysis", key="run_competitor_analysis"):
		state_key = _analysis_state_key(ticker)
		st.session_state.pop(state_key, None)
		with st.spinner(f"Building investment memo for {ticker}..."):
			try:
				analysis_result = run_ai_analysis(
					ticker,
					stock_data,
					model_name=st.session_state.get("agent_model") or None,
					analysis_focus=analysis_focus,
				)
				st.session_state[state_key] = {"result": analysis_result, "error": None}
			except Exception as exc:
				st.session_state[state_key] = {"result": None, "error": str(exc)}

	analysis_state = st.session_state.get(_analysis_state_key(ticker), {})
	if analysis_state.get("error"):
		st.error(analysis_state["error"])

	if analysis_state.get("result"):
		analysis_result = analysis_state["result"]
		valuation_pick = analysis_result.get("valuation_pick")
		if not valuation_pick and analysis_result.get("valuation_pick_error"):
			st.warning(f"AI valuation model recommendation was unavailable: {analysis_result['valuation_pick_error']}")
		st.markdown(render_ai_report(analysis_result["memo_markdown"], valuation_pick=valuation_pick), unsafe_allow_html=True)
	else:
		st.info("Run the AI analyst to generate a competitor memo for the selected ticker.")
