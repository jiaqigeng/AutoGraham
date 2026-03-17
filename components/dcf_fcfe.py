from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.formatting import format_compact_currency, format_percent, format_price, format_shares
from utils.dcf_calculator import (
	ValuationResult,
	calculate_apv,
	calculate_ddm_h_model,
	calculate_ddm_single_stage,
	calculate_ddm_three_stage,
	calculate_ddm_two_stage,
	calculate_fcfe_single_stage,
	calculate_fcfe_three_stage,
	calculate_fcfe_two_stage,
	calculate_fcff_single_stage,
	calculate_fcff_three_stage,
	calculate_fcff_two_stage,
	calculate_rim,
	default_valuation_inputs,
)


MODEL_OPTIONS = [
	"Free Cash Flow to Firm (FCFF) - Unlevered DCF",
	"Free Cash Flow to Equity (FCFE) - Levered DCF",
	"Dividend Discount Model (DDM)",
	"Adjusted Present Value (APV)",
	"Residual Income Model (RIM)",
]

MODEL_META = {
	"Free Cash Flow to Firm (FCFF) - Unlevered DCF": {
		"short": "FCFF",
		"accent": "#0f766e",
		"eyebrow": "Unlevered enterprise lens",
		"description": "Values the operating business first, then bridges from enterprise value to equity after debt and cash.",
	},
	"Free Cash Flow to Equity (FCFE) - Levered DCF": {
		"short": "FCFE",
		"accent": "#0f766e",
		"eyebrow": "Direct equity cash flows",
		"description": "Discounts cash available to equity holders directly, which makes it useful when leverage is part of the story.",
	},
	"Dividend Discount Model (DDM)": {
		"short": "DDM",
		"accent": "#b45309",
		"eyebrow": "Distribution-based valuation",
		"description": "Frames value through dividend capacity and works best for mature payout-heavy businesses.",
	},
	"Adjusted Present Value (APV)": {
		"short": "APV",
		"accent": "#1d4ed8",
		"eyebrow": "Capital structure overlay",
		"description": "Separates operating value from financing side effects so tax shields can be inspected explicitly.",
	},
	"Residual Income Model (RIM)": {
		"short": "RIM",
		"accent": "#7c3aed",
		"eyebrow": "Balance-sheet anchored",
		"description": "Starts from book value and adds present value of future residual income above the cost of equity.",
	},
}

GROWTH_OPTIONS = ["Single-Stage (Stable)", "Two-Stage", "Three-Stage (Multi-stage decay)"]


def _render_valuation_shell_css() -> None:
	st.markdown(
		"""
		<style>
		:root {
			--valuation-ink: #102033;
			--valuation-muted: #5b6b7f;
			--valuation-line: rgba(16, 32, 51, 0.10);
			--valuation-panel: rgba(255, 255, 255, 0.88);
			--valuation-panel-strong: rgba(255, 255, 255, 0.95);
			--valuation-shadow: 0 24px 60px rgba(15, 23, 42, 0.10);
		}

		.valuation-shell {
			padding: 1.4rem;
			border-radius: 28px;
			background:
				radial-gradient(circle at top left, rgba(15, 118, 110, 0.17), transparent 30%),
				radial-gradient(circle at top right, rgba(180, 83, 9, 0.15), transparent 28%),
				linear-gradient(180deg, rgba(250, 250, 249, 0.98), rgba(244, 247, 245, 0.98));
			border: 1px solid rgba(15, 23, 42, 0.08);
			box-shadow: var(--valuation-shadow);
			margin-bottom: 1rem;
		}

		.valuation-hero {
			display: grid;
			grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
			gap: 1rem;
			align-items: stretch;
			margin-bottom: 1rem;
		}

		.valuation-hero-card,
		.valuation-side-card,
		.valuation-note,
		.valuation-metric-card {
			border-radius: 24px;
			background: var(--valuation-panel);
			border: 1px solid var(--valuation-line);
			backdrop-filter: blur(8px);
		}

		.valuation-hero-card {
			padding: 1.35rem;
		}

		.valuation-side-card {
			padding: 1.15rem;
			display: flex;
			flex-direction: column;
			justify-content: space-between;
		}

		.valuation-eyebrow {
			font-size: 0.72rem;
			letter-spacing: 0.12em;
			text-transform: uppercase;
			font-weight: 800;
			color: #0f766e;
			margin-bottom: 0.7rem;
		}

		.valuation-title {
			font-size: clamp(1.75rem, 1.3rem + 1.3vw, 2.65rem);
			line-height: 0.96;
			font-weight: 900;
			letter-spacing: -0.05em;
			color: var(--valuation-ink);
			margin: 0 0 0.85rem;
		}

		.valuation-body {
			font-size: 1rem;
			line-height: 1.7;
			color: var(--valuation-muted);
			margin: 0;
			max-width: 40rem;
		}

		.valuation-tag-row {
			display: flex;
			flex-wrap: wrap;
			gap: 0.55rem;
			margin-top: 1rem;
		}

		.valuation-tag {
			display: inline-flex;
			align-items: center;
			padding: 0.48rem 0.8rem;
			border-radius: 999px;
			font-size: 0.82rem;
			font-weight: 800;
			color: var(--valuation-ink);
			background: rgba(255, 255, 255, 0.78);
			border: 1px solid rgba(16, 32, 51, 0.08);
		}

		.valuation-side-kicker {
			font-size: 0.74rem;
			letter-spacing: 0.12em;
			text-transform: uppercase;
			font-weight: 800;
			color: #7c2d12;
		}

		.valuation-side-value {
			font-size: 2rem;
			font-weight: 900;
			letter-spacing: -0.05em;
			color: var(--valuation-ink);
			margin: 0.35rem 0 0.4rem;
		}

		.valuation-side-copy {
			font-size: 0.93rem;
			line-height: 1.65;
			color: var(--valuation-muted);
			margin: 0;
		}

		.valuation-section-label {
			font-size: 0.74rem;
			letter-spacing: 0.12em;
			text-transform: uppercase;
			font-weight: 800;
			color: #64748b;
			margin: 0.15rem 0 0.55rem;
		}

		.valuation-note {
			padding: 0.95rem 1rem;
			margin-bottom: 0.7rem;
			background: rgba(255, 251, 235, 0.84);
			border-color: rgba(217, 119, 6, 0.18);
		}

		.valuation-note strong {
			color: #9a3412;
		}

		.valuation-note span {
			color: #7c2d12;
		}

		.valuation-results-grid {
			display: grid;
			grid-template-columns: repeat(3, minmax(0, 1fr));
			gap: 0.8rem;
			margin: 0.9rem 0 0.2rem;
		}

		.valuation-metric-card {
			padding: 1rem 1.05rem;
			background: var(--valuation-panel-strong);
		}

		.valuation-metric-label {
			font-size: 0.75rem;
			letter-spacing: 0.08em;
			text-transform: uppercase;
			font-weight: 800;
			color: #64748b;
			margin-bottom: 0.4rem;
		}

		.valuation-metric-value {
			font-size: 1.5rem;
			font-weight: 900;
			letter-spacing: -0.04em;
			color: var(--valuation-ink);
			line-height: 1.1;
		}

		.valuation-metric-copy {
			font-size: 0.88rem;
			line-height: 1.55;
			color: var(--valuation-muted);
			margin-top: 0.45rem;
		}

		[data-testid="stSegmentedControl"] {
			padding: 0.3rem;
			border-radius: 22px;
			background: rgba(255, 255, 255, 0.72);
			border: 1px solid rgba(16, 32, 51, 0.08);
		}

		[data-testid="stSegmentedControl"] [role="radiogroup"] {
			gap: 0.3rem;
		}

		[data-testid="stSegmentedControl"] label {
			border-radius: 16px !important;
			padding: 0.4rem 0.85rem !important;
			border: 0 !important;
			background: transparent !important;
		}

		[data-testid="stSegmentedControl"] label[data-selected="true"] {
			background: linear-gradient(135deg, #102033, #0f766e) !important;
			box-shadow: 0 10px 25px rgba(15, 118, 110, 0.22);
		}

		[data-testid="stSegmentedControl"] label[data-selected="true"] p {
			color: #ffffff !important;
		}

		[data-testid="stSegmentedControl"] p {
			font-size: 0.92rem !important;
			font-weight: 700 !important;
			color: var(--valuation-ink) !important;
		}

		[data-testid="stExpander"] {
			border-radius: 20px !important;
			border: 1px solid rgba(16, 32, 51, 0.08) !important;
			background: rgba(255, 255, 255, 0.72) !important;
		}

		[data-testid="stDataFrame"] {
			border-radius: 18px;
			overflow: hidden;
			border: 1px solid rgba(16, 32, 51, 0.08);
		}

		@media (max-width: 900px) {
			.valuation-hero {
				grid-template-columns: 1fr;
			}

			.valuation-results-grid {
				grid-template-columns: 1fr;
			}
		}
		</style>
		""",
		unsafe_allow_html=True,
	)


def _render_hero(model: str, growth_stage: str | None) -> None:
	meta = MODEL_META[model]
	stage_label = growth_stage or meta["short"]
	st.markdown(
		f"""
		<div class="valuation-shell">
		  <div class="valuation-hero">
		    <div class="valuation-hero-card">
		      <div class="valuation-eyebrow">{meta['eyebrow']}</div>
		      <h2 class="valuation-title">Valuation Lab</h2>
		      <p class="valuation-body">{meta['description']} Build a clean downside-upside view by pairing the right framework with a matching growth structure.</p>
		      <div class="valuation-tag-row">
		        <span class="valuation-tag">Model: {meta['short']}</span>
		        <span class="valuation-tag">Stage: {stage_label}</span>
		        <span class="valuation-tag">Live market inputs</span>
		      </div>
		    </div>
		    <div class="valuation-side-card">
		      <div>
		        <div class="valuation-side-kicker">Selected framework</div>
		        <div class="valuation-side-value">{meta['short']}</div>
		        <p class="valuation-side-copy">Switch methods without leaving the tab. Each framework exposes only the assumptions that materially change the valuation logic.</p>
		      </div>
		      <div class="valuation-tag-row">
		        <span class="valuation-tag">Transparent formulas</span>
		        <span class="valuation-tag">Editable assumptions</span>
		      </div>
		    </div>
		  </div>
		</div>
		""",
		unsafe_allow_html=True,
	)


def _render_note_card(note: str) -> None:
	st.markdown(
		f"<div class='valuation-note'><strong>Input check:</strong> <span>{note}</span></div>",
		unsafe_allow_html=True,
	)


def _render_section_label(label: str) -> None:
	st.markdown(f"<div class='valuation-section-label'>{label}</div>", unsafe_allow_html=True)


def _render_model_summary_strip(model: str, growth_stage: str | None) -> None:
	meta = MODEL_META[model]
	stage = growth_stage or "Standalone framework"
	st.markdown(
		f"""
		<div class="valuation-tag-row" style="margin: 0.15rem 0 1rem;">
		  <span class="valuation-tag">{meta['short']}</span>
		  <span class="valuation-tag">{stage}</span>
		  <span class="valuation-tag">Editable live assumptions</span>
		  <span class="valuation-tag">Formula trace</span>
		</div>
		""",
		unsafe_allow_html=True,
	)


def _render_locked_input_cards(items: list[tuple[str, str, str]]) -> None:
	if not items:
		return
	card_html = "".join(
		(
			"<div class='valuation-metric-card'>"
			f"<div class='valuation-metric-label'>{label}</div>"
			f"<div class='valuation-metric-value'>{value}</div>"
			f"<div class='valuation-metric-copy'>{copy}</div>"
			"</div>"
		)
		for label, value, copy in items
	)
	st.markdown(f"<div class='valuation-results-grid'>{card_html}</div>", unsafe_allow_html=True)


def _render_locked_inputs(label: str, items: list[tuple[str, str, str]]) -> None:
	_render_section_label(label)
	st.caption("These company inputs are locked to the latest Yahoo Finance data and are not user-editable.")
	_render_locked_input_cards(items)


def _format_compact_currency(value: object) -> str:
	return format_compact_currency(value)


def _format_shares(value: object) -> str:
	return format_shares(value)


def _format_price(value: object) -> str:
	return format_price(value)


def _format_percent(value: object) -> str:
	return format_percent(value, allow_negative=True)


def _input_key(scope: str, prefix: str, field: str) -> str:
	return f"valuation_{scope}_{prefix}_{field}"


def _render_result_cards(result: ValuationResult) -> None:
	margin_text = "N/A" if result.margin_of_safety is None else f"{result.margin_of_safety:.2f}%"
	present_value_label = "PV of Explicit Forecast" if result.discounted_terminal_value > 0 else "Core Present Value"
	third_label = "PV of Tax Shield" if result.tax_shield_value is not None else "Enterprise Value" if result.enterprise_value is not None else "Discounted Terminal Value"
	third_value = _format_compact_currency(result.tax_shield_value if result.tax_shield_value is not None else result.enterprise_value if result.enterprise_value is not None else result.discounted_terminal_value)

	st.markdown(
		f"""
		<div class="valuation-results-grid">
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Fair Value / Share</div>
		    <div class="valuation-metric-value">${result.fair_value_per_share:,.2f}</div>
		    <div class="valuation-metric-copy">Intrinsic value per share implied by the selected framework.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Current Price</div>
		    <div class="valuation-metric-value">{_format_price(result.current_price)}</div>
		    <div class="valuation-metric-copy">Spot market price used to compute the live gap versus fair value.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Margin of Safety</div>
		    <div class="valuation-metric-value">{margin_text}</div>
		    <div class="valuation-metric-copy">Positive means implied upside. Negative means the current market is richer than your inputs.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Equity Value</div>
		    <div class="valuation-metric-value">{_format_compact_currency(result.equity_value)}</div>
		    <div class="valuation-metric-copy">Total equity value produced after the model-specific bridge from operations to shareholders.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">{present_value_label}</div>
		    <div class="valuation-metric-value">{_format_compact_currency(result.present_value_of_cash_flows)}</div>
		    <div class="valuation-metric-copy">Present value contribution from forecasted cash flows or residual earnings before the final bridge.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">{third_label}</div>
		    <div class="valuation-metric-value">{third_value}</div>
		    <div class="valuation-metric-copy">The last major value driver to sanity-check before trusting the output.</div>
		  </div>
		</div>
		""",
		unsafe_allow_html=True,
	)


def _render_schedule(result: ValuationResult) -> None:
	if not result.schedule:
		return
	with st.expander("Projection schedule", expanded=False):
		schedule_frame = pd.DataFrame(result.schedule)
		for column in schedule_frame.columns:
			if schedule_frame[column].dtype.kind in {"f", "i"} and column != "Year":
				if "Rate" in column or column == "ROE":
					schedule_frame[column] = schedule_frame[column].map(lambda value: f"{value * 100:.2f}%")
				else:
					schedule_frame[column] = schedule_frame[column].map(lambda value: f"${value:,.2f}")
		st.dataframe(schedule_frame, use_container_width=True, hide_index=True)


def _render_formula_guide(model: str, growth_stage: str | None, result: ValuationResult) -> None:
	with st.expander("View Math & Formulas", expanded=False):
		st.markdown(f"**Model:** {model}")
		if growth_stage:
			st.markdown(f"**Growth assumption:** {growth_stage}")

		if model.startswith("Free Cash Flow to Equity"):
			st.latex(r"FCFE_t = FCFE_{t-1} \times (1 + g_t)")
			st.latex(r"Equity\ Value = \sum_{t=1}^{n}\frac{FCFE_t}{(1 + r)^t} + \frac{FCFE_n(1+g_{term})}{(r-g_{term})(1+r)^n}")
		elif model.startswith("Free Cash Flow to Firm"):
			st.latex(r"FCFF_t = FCFF_{t-1} \times (1 + g_t)")
			st.latex(r"Enterprise\ Value = \sum_{t=1}^{n}\frac{FCFF_t}{(1 + WACC)^t} + \frac{FCFF_n(1+g_{term})}{(WACC-g_{term})(1+WACC)^n}")
			st.latex(r"Equity\ Value = Enterprise\ Value - Debt + Cash")
		elif model.startswith("Dividend Discount Model") and growth_stage == "H-Model":
			st.latex(r"P_0 = \frac{D_0(1+g_L) + D_0H(g_S-g_L)}{r-g_L}")
		elif model.startswith("Dividend Discount Model"):
			st.latex(r"D_t = D_{t-1} \times (1 + g_t)")
			st.latex(r"P_0 = \sum_{t=1}^{n}\frac{D_t}{(1 + r)^t} + \frac{D_n(1+g_{term})}{(r-g_{term})(1+r)^n}")
		elif model.startswith("Adjusted Present Value"):
			st.latex(r"APV = PV\ of\ Unlevered\ Operations + PV\ of\ Financing\ Side\ Effects")
			st.latex(r"Equity\ Value = APV - Debt + Cash")
		elif model.startswith("Residual Income"):
			st.latex(r"Residual\ Income_t = EPS_t - r \times BV_{t-1}")
			st.latex(r"Value_0 = BV_0 + \sum_{t=1}^{n}\frac{RI_t}{(1+r)^t} + \frac{RI_n(1+g_{term})}{(r-g_{term})(1+r)^n}")

		st.caption(
			f"Implied fair value per share: ${result.fair_value_per_share:,.2f}. "
			f"Explicit forecast PV: {_format_compact_currency(result.present_value_of_cash_flows)}."
		)


def _render_fcfe_inputs(defaults: dict[str, float], growth_stage: str, scope: str) -> ValuationResult:
	prefix = "fcfe"
	current_fcfe = defaults["starting_fcfe"]
	shares_outstanding = defaults["shares_outstanding"]
	current_price = defaults["current_price"]
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Starting FCFE", _format_compact_currency(current_fcfe), "Latest Yahoo free cash flow to equity proxy."),
			("Shares Outstanding", _format_shares(shares_outstanding), "Current share-count proxy used for per-share valuation, sourced from market cap divided by price when available."),
			("Current Price", _format_price(current_price), "Latest market price from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	cost_of_equity = col1.number_input("Cost of Equity (%)", min_value=0.1, value=float(defaults["cost_of_equity"] * 100), step=0.5, key=_input_key(scope, prefix, "cost_of_equity")) / 100

	if growth_stage == "Single-Stage (Stable)":
		stable_growth = col2.number_input("Stable Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return calculate_fcfe_single_stage(current_fcfe, shares_outstanding, cost_of_equity, stable_growth, current_price)

	if growth_stage == "Two-Stage":
		high_growth = col2.number_input("Stage 1 Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		projection_years = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		terminal_growth = st.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return calculate_fcfe_two_stage(current_fcfe, shares_outstanding, high_growth, projection_years, cost_of_equity, terminal_growth, current_price)

	high_growth = col2.number_input("High Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
	high_growth_years = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
	col4, col5 = st.columns(2)
	transition_years = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
	terminal_growth = col5.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
	return calculate_fcfe_three_stage(current_fcfe, shares_outstanding, high_growth, high_growth_years, transition_years, cost_of_equity, terminal_growth, current_price)


def _render_fcff_inputs(defaults: dict[str, float], growth_stage: str, scope: str) -> ValuationResult:
	prefix = "fcff"
	current_fcff = defaults["starting_fcff"]
	shares_outstanding = defaults["shares_outstanding"]
	current_price = defaults["current_price"]
	total_debt = defaults["total_debt"]
	cash = defaults["cash"]
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Starting FCFF", _format_compact_currency(current_fcff), "Unlevered FCFF proxy derived from Yahoo cash flow data, including an after-tax interest add-back when needed."),
			("Shares Outstanding", _format_shares(shares_outstanding), "Current share-count proxy used for per-share valuation, sourced from market cap divided by price when available."),
			("Current Price", _format_price(current_price), "Latest market price from Yahoo Finance."),
			("Total Debt", _format_compact_currency(total_debt), "Latest gross debt bridge used to move from enterprise value to equity value."),
			("Cash", _format_compact_currency(cash), "Latest annual balance-sheet cash and short-term investments from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	wacc = col1.number_input("WACC (%)", min_value=0.1, value=float(defaults["wacc"] * 100), step=0.5, key=_input_key(scope, prefix, "wacc")) / 100

	if growth_stage == "Single-Stage (Stable)":
		stable_growth = col2.number_input("Stable Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return calculate_fcff_single_stage(current_fcff, shares_outstanding, wacc, stable_growth, total_debt, cash, current_price)

	if growth_stage == "Two-Stage":
		high_growth = col2.number_input("Stage 1 Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		projection_years = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		terminal_growth = st.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return calculate_fcff_two_stage(current_fcff, shares_outstanding, high_growth, projection_years, wacc, terminal_growth, total_debt, cash, current_price)

	high_growth = col2.number_input("High Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
	high_growth_years = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
	col4, col5 = st.columns(2)
	transition_years = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
	terminal_growth = col5.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
	return calculate_fcff_three_stage(current_fcff, shares_outstanding, high_growth, high_growth_years, transition_years, wacc, terminal_growth, total_debt, cash, current_price)


def _render_ddm_inputs(defaults: dict[str, float], growth_stage: str, scope: str) -> ValuationResult:
	prefix = "ddm"
	dividend_per_share = defaults["dividend_per_share"]
	shares_outstanding = defaults["shares_outstanding"]
	current_price = defaults["current_price"]
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Dividend / Share", _format_price(dividend_per_share), "Latest annual dividend per share from Yahoo Finance."),
			("Shares Outstanding", _format_shares(shares_outstanding), "Current share-count proxy used for per-share valuation, sourced from market cap divided by price when available."),
			("Current Price", _format_price(current_price), "Latest market price from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	required_return = col1.number_input("Required Return (%)", min_value=0.1, value=float(defaults["cost_of_equity"] * 100), step=0.5, key=_input_key(scope, prefix, "required_return")) / 100

	if growth_stage == "Single-Stage (Stable)":
		stable_growth = col2.number_input("Stable Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return calculate_ddm_single_stage(dividend_per_share, shares_outstanding, required_return, stable_growth, current_price)

	if growth_stage == "Two-Stage":
		high_growth = col2.number_input("Stage 1 Dividend Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		projection_years = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		terminal_growth = st.number_input("Terminal Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return calculate_ddm_two_stage(dividend_per_share, shares_outstanding, high_growth, projection_years, required_return, terminal_growth, current_price)

	if growth_stage == "Three-Stage (Multi-stage decay)":
		high_growth = col2.number_input("High Dividend Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
		high_growth_years = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
		col4, col5 = st.columns(2)
		transition_years = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
		terminal_growth = col5.number_input("Terminal Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
		return calculate_ddm_three_stage(dividend_per_share, shares_outstanding, high_growth, high_growth_years, transition_years, required_return, terminal_growth, current_price)

	half_life_years = col2.number_input("Extraordinary Growth Half-Life (Years)", min_value=0.5, value=float(defaults["projection_years"] / 2), step=0.5, key=_input_key(scope, prefix, "half_life_years"))
	short_term_growth = col3.number_input("Short-Term Dividend Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "short_term_growth")) / 100
	stable_growth = st.number_input("Stable Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth_h")) / 100
	return calculate_ddm_h_model(dividend_per_share, shares_outstanding, short_term_growth, stable_growth, half_life_years, required_return, current_price)


def _render_apv_inputs(defaults: dict[str, float], scope: str) -> ValuationResult:
	prefix = "apv"
	current_fcff = defaults["starting_fcff"]
	shares_outstanding = defaults["shares_outstanding"]
	current_price = defaults["current_price"]
	total_debt = defaults["total_debt"]
	cash = defaults["cash"]
	tax_rate = defaults["tax_rate"]
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Starting FCFF", _format_compact_currency(current_fcff), "Latest annual free cash flow from Yahoo Finance, falling back to operating cash flow minus capex when needed."),
			("Shares Outstanding", _format_shares(shares_outstanding), "Current share-count proxy used for per-share valuation, sourced from market cap divided by price when available."),
			("Current Price", _format_price(current_price), "Latest market price from Yahoo Finance."),
			("Total Debt", _format_compact_currency(total_debt), "Latest annual balance-sheet debt from Yahoo Finance."),
			("Cash", _format_compact_currency(cash), "Latest annual balance-sheet cash and short-term investments from Yahoo Finance."),
			("Tax Rate", _format_percent(tax_rate), "Latest effective or statement-derived tax rate from Yahoo Finance."),
			("Cost of Debt", _format_percent(defaults["cost_of_debt"]), "Latest Yahoo-derived debt cost used to discount APV tax shields."),
		],
	)
	col1, col2, col3, col4 = st.columns(4)
	unlevered_cost = col1.number_input("Unlevered Cost of Capital (%)", min_value=0.1, value=float(defaults["unlevered_cost"] * 100), step=0.5, key=_input_key(scope, prefix, "unlevered_cost")) / 100
	high_growth = col2.number_input("Stage 1 Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
	projection_years = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	terminal_growth = col4.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return calculate_apv(current_fcff, shares_outstanding, high_growth, projection_years, unlevered_cost, terminal_growth, total_debt, cash, tax_rate, defaults["cost_of_debt"], current_price)


def _render_rim_inputs(defaults: dict[str, float], scope: str) -> ValuationResult:
	prefix = "rim"
	book_value_per_share = defaults["book_value_per_share"]
	shares_outstanding = defaults["shares_outstanding"]
	return_on_equity = defaults["return_on_equity"]
	current_price = defaults["current_price"]
	payout_ratio = defaults["payout_ratio"]
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Book Value / Share", _format_price(book_value_per_share), "Latest book value per share from Yahoo Finance."),
			("Shares Outstanding", _format_shares(shares_outstanding), "Current share-count proxy used for per-share valuation, sourced from market cap divided by price when available."),
			("ROE", _format_percent(return_on_equity), "Latest return on equity from Yahoo Finance."),
			("Payout Ratio", _format_percent(payout_ratio), "Latest payout ratio from Yahoo Finance."),
			("Current Price", _format_price(current_price), "Latest market price from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	cost_of_equity = col1.number_input("Cost of Equity (%)", min_value=0.1, value=float(defaults["cost_of_equity"] * 100), step=0.5, key=_input_key(scope, prefix, "cost_of_equity")) / 100
	projection_years = int(col2.number_input("Forecast Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	terminal_growth = col3.number_input("Terminal Residual Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return calculate_rim(book_value_per_share, shares_outstanding, return_on_equity, cost_of_equity, payout_ratio, projection_years, terminal_growth, current_price)


def render_dcf_calculator(info_dict) -> None:
	_render_valuation_shell_css()
	company_info = getattr(info_dict, "info", info_dict)
	annual_cashflow = getattr(info_dict, "annual_cashflow", None)
	annual_balance_sheet = getattr(info_dict, "annual_balance_sheet", None)
	annual_income_stmt = getattr(info_dict, "annual_income_stmt", None)
	frame_ticker = getattr(annual_cashflow, "attrs", {}).get("ticker", "ticker")
	scope = str(company_info.get("symbol") or company_info.get("shortName") or frame_ticker).strip().upper().replace(" ", "_")

	defaults = default_valuation_inputs(
		company_info,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)
	model = st.segmented_control(
		"Valuation model",
		options=MODEL_OPTIONS,
		default="Free Cash Flow to Firm (FCFF) - Unlevered DCF",
		format_func=lambda option: MODEL_META[option]["short"],
		key=f"valuation_model_{scope}",
		width="stretch",
	)

	growth_stage: str | None = None
	if model in {
		"Free Cash Flow to Firm (FCFF) - Unlevered DCF",
		"Free Cash Flow to Equity (FCFE) - Levered DCF",
		"Dividend Discount Model (DDM)",
	}:
		growth_options = list(GROWTH_OPTIONS)
		if model == "Dividend Discount Model (DDM)":
			growth_options.append("H-Model")
		growth_stage = st.segmented_control(
			"Growth stage assumption",
			options=growth_options,
			default=growth_options[1] if "Two-Stage" in growth_options else growth_options[0],
			key=f"growth_stage_{scope}_{model}",
			width="stretch",
		)

	_render_hero(model, growth_stage)
	_render_model_summary_strip(model, growth_stage)
	_render_section_label("Data quality flags")
	default_notes = []
	if defaults["starting_fcfe"] <= 0:
		default_notes.append("Yahoo Finance did not provide a usable positive FCFE input. FCFE-based models may not be reliable for this ticker.")
	if defaults["starting_fcff"] <= 0:
		default_notes.append("Yahoo Finance did not provide a usable unlevered FCFF proxy after adjusting cash flow inputs. FCFF-based models may not be reliable for this ticker.")
	if defaults["dividend_per_share"] <= 0:
		default_notes.append("Yahoo Finance does not show a positive annual dividend per share. DDM requires dividend data to work.")
	if defaults["book_value_per_share"] <= 0:
		default_notes.append("Yahoo Finance does not show a usable book value per share. Residual income valuation may not be reliable for this ticker.")
	for note in default_notes:
		_render_note_card(note)
	if not default_notes:
		st.markdown(
			"<div class='valuation-note'><strong>Input check:</strong> <span>Yahoo Finance inputs loaded cleanly. Only valuation assumptions such as discount rates, growth rates, and forecast length are editable.</span></div>",
			unsafe_allow_html=True,
		)

	_render_section_label("Assumption builder")

	try:
		if model == "Free Cash Flow to Equity (FCFE) - Levered DCF":
			result = _render_fcfe_inputs(defaults, growth_stage or "Two-Stage", scope)
		elif model == "Free Cash Flow to Firm (FCFF) - Unlevered DCF":
			result = _render_fcff_inputs(defaults, growth_stage or "Two-Stage", scope)
		elif model == "Dividend Discount Model (DDM)":
			result = _render_ddm_inputs(defaults, growth_stage or "Two-Stage", scope)
		elif model == "Adjusted Present Value (APV)":
			result = _render_apv_inputs(defaults, scope)
		else:
			result = _render_rim_inputs(defaults, scope)
	except ValueError as exc:
		st.warning(str(exc))
		return

	if result.fair_value_per_share <= 0:
		st.warning("Calculated fair value is not positive. Review the assumptions and company fundamentals.")
		return

	_render_section_label("Valuation output")
	_render_result_cards(result)

	st.caption(f"Selected model: {result.model_label}. Growth structure: {result.stage_label}.")

	if model.startswith("Free Cash Flow to Firm") or model.startswith("Adjusted Present Value"):
		st.caption(
			f"FCFF default source: {_format_compact_currency(defaults['starting_fcff'])}. "
			f"Debt: {_format_compact_currency(defaults['total_debt'])}. Cash: {_format_compact_currency(defaults['cash'])}."
		)
	elif model.startswith("Free Cash Flow to Equity"):
		st.caption(f"FCFE default source: {_format_compact_currency(defaults['starting_fcfe'])}.")
	elif model.startswith("Dividend Discount Model"):
		st.caption(f"Dividend default source: {_format_price(defaults['dividend_per_share'])} per share.")
	else:
		st.caption(
			f"Book value default: {_format_price(defaults['book_value_per_share'])} per share. "
			f"ROE default: {_format_percent(defaults['return_on_equity'])}."
		)

	_render_section_label("Model diagnostics")
	_render_formula_guide(model, growth_stage, result)
	_render_schedule(result)
