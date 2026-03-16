import streamlit as st
from agent.llm_service import run_competitor_analysis
from components.ai_report import render_ai_report
from components.dcf_fcfe import render_dcf_calculator
from components.header import render_metrics_header
from components.waterfall import render_waterfall_chart
from data.yf_api import fetch_stock_data


st.set_page_config(layout="wide")

st.markdown(
	"""
	<style>
	[data-testid="stMarkdownContainer"] h1,
	[data-testid="stMarkdownContainer"] h2,
	[data-testid="stMarkdownContainer"] h3 {
		color: #0f172a;
		letter-spacing: -0.02em;
	}

	[data-testid="stMarkdownContainer"] h1,
	[data-testid="stMarkdownContainer"] h2 {
		padding-top: 0.35rem;
		border-bottom: 1px solid rgba(148, 163, 184, 0.28);
		padding-bottom: 0.3rem;
	}

	[data-testid="stMarkdownContainer"] p,
	[data-testid="stMarkdownContainer"] li {
		font-size: 0.98rem;
		line-height: 1.7;
		color: #334155;
	}

	[data-testid="stMarkdownContainer"] table {
		width: 100%;
		border-collapse: collapse;
		margin: 1rem 0 1.25rem;
		background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.98));
		border: 1px solid rgba(148, 163, 184, 0.22);
		border-radius: 14px;
		overflow: hidden;
	}

	[data-testid="stMarkdownContainer"] th {
		background: #e2e8f0;
		color: #0f172a;
		font-weight: 700;
	}

	[data-testid="stMarkdownContainer"] th,
	[data-testid="stMarkdownContainer"] td {
		padding: 0.75rem 0.9rem;
		border-bottom: 1px solid rgba(148, 163, 184, 0.16);
		text-align: left;
	}

	.ai-report-shell {
		margin-top: 0.35rem;
		padding: 1.25rem;
		border-radius: 24px;
		background:
			radial-gradient(circle at top right, rgba(14, 165, 233, 0.12), transparent 24%),
			linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,252,0.98));
		border: 1px solid rgba(148, 163, 184, 0.18);
		box-shadow: 0 22px 40px rgba(15, 23, 42, 0.08);
	}

	.ai-report-header {
		padding: 0.25rem 0 1rem;
		margin-bottom: 1rem;
		border-bottom: 1px solid rgba(148, 163, 184, 0.18);
	}

	.ai-report-kicker {
		font-size: 0.76rem;
		font-weight: 800;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: #0f766e;
		margin-bottom: 0.45rem;
	}

	.ai-report-title {
		margin: 0;
		font-size: clamp(1.5rem, 1.15rem + 1vw, 2.2rem);
		line-height: 1.1;
		font-weight: 800;
		letter-spacing: -0.03em;
		color: #0f172a;
		border: 0 !important;
		padding: 0 !important;
	}

	.ai-report-subtitle {
		margin: 0.7rem 0 0;
		max-width: 52rem;
		font-size: 1rem;
		line-height: 1.7;
		color: #475569;
	}

	.ai-report-peer-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		margin-top: 1rem;
	}

	.ai-report-peer-label {
		font-size: 0.82rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #64748b;
	}

	.ai-report-peer-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.ai-report-chip {
		display: inline-flex;
		align-items: center;
		padding: 0.42rem 0.7rem;
		border-radius: 999px;
		background: rgba(14, 165, 233, 0.1);
		border: 1px solid rgba(14, 165, 233, 0.18);
		font-size: 0.88rem;
		font-weight: 700;
		color: #0f172a;
	}

	.ai-report-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 1rem;
	}

	.ai-report-section {
		display: grid;
		grid-template-columns: 56px minmax(0, 1fr);
		gap: 0.9rem;
		padding: 1rem;
		border-radius: 20px;
		background: rgba(255, 255, 255, 0.82);
		border: 1px solid rgba(148, 163, 184, 0.18);
		backdrop-filter: blur(6px);
	}

	.ai-report-section-index {
		display: flex;
		align-items: flex-start;
		justify-content: center;
		padding-top: 0.2rem;
		font-size: 0.86rem;
		font-weight: 800;
		letter-spacing: 0.08em;
		color: #0891b2;
	}

	.ai-report-section-body {
		min-width: 0;
	}

	.ai-report-section-title {
		margin: 0 0 0.7rem;
		font-size: 1.15rem;
		line-height: 1.25;
		font-weight: 800;
		letter-spacing: -0.02em;
		color: #0f172a;
	}

	.ai-report-paragraph {
		margin: 0 0 0.8rem;
		font-size: 0.98rem;
		line-height: 1.8;
		color: #334155;
	}

	.ai-report-list {
		margin: 0.2rem 0 0.85rem;
		padding-left: 1.15rem;
		color: #334155;
	}

	.ai-report-list li {
		margin-bottom: 0.45rem;
		padding-left: 0.2rem;
		line-height: 1.7;
	}

	.ai-report-inline-code {
		padding: 0.12rem 0.42rem;
		border-radius: 8px;
		background: rgba(15, 23, 42, 0.06);
		font-size: 0.88em;
		color: #0f172a;
	}

	.ai-report-table-wrap {
		overflow-x: auto;
		margin: 0.25rem 0 0.9rem;
	}

	.ai-report-table {
		width: 100%;
		min-width: 420px;
		border-collapse: collapse;
		background: rgba(248, 250, 252, 0.75);
		border: 1px solid rgba(148, 163, 184, 0.18);
		border-radius: 16px;
		overflow: hidden;
	}

	.ai-report-table th {
		background: rgba(226, 232, 240, 0.88);
		font-size: 0.8rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: #334155;
	}

	.ai-report-table td {
		font-size: 0.94rem;
		color: #1e293b;
	}

	.ai-report-fallback {
		padding-top: 0.25rem;
	}

	@media (max-width: 768px) {
		.ai-report-shell {
			padding: 1rem;
			border-radius: 20px;
		}

		.ai-report-grid {
			grid-template-columns: 1fr;
		}

		.ai-report-section {
			grid-template-columns: 1fr;
			gap: 0.4rem;
		}

		.ai-report-section-index {
			justify-content: flex-start;
		}
	}
	</style>
	""",
	unsafe_allow_html=True,
)

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

tab1, tab2, tab3 = st.tabs(["Financials Dashboard", "DCF Valuation", "AI Analyst"])

with tab1:
	render_metrics_header(stock_data.info)
	render_waterfall_chart(stock_data.quarterly_income_stmt)

with tab2:
	render_dcf_calculator(stock_data.info)

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
		st.session_state.pop("ai_analysis_error", None)
		with st.spinner(f"Building investment memo for {ticker}..."):
			try:
				analysis_result = run_competitor_analysis(
					ticker,
					model_name=st.session_state.get("agent_model") or None,
					analysis_focus=analysis_focus,
				)
				st.session_state["ai_analysis_result"] = analysis_result
			except Exception as exc:
				st.session_state.pop("ai_analysis_result", None)
				st.session_state["ai_analysis_error"] = str(exc)

	if st.session_state.get("ai_analysis_error"):
		st.error(st.session_state["ai_analysis_error"])

	if st.session_state.get("ai_analysis_result"):
		st.markdown(render_ai_report(st.session_state["ai_analysis_result"]), unsafe_allow_html=True)
	else:
		st.info("Run the AI analyst to generate a competitor memo for the selected ticker.")
