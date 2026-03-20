from __future__ import annotations

import streamlit as st

from data.normalization import format_compact_currency, format_percent, format_price, format_shares
from ui_components.valuation_result import render_formula_guide, render_result_cards, render_schedule
from workflows.manual_valuation import GROWTH_OPTIONS, MODEL_META, MODEL_OPTIONS, prepare_manual_valuation, run_manual_valuation


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

		.valuation-hero-card { padding: 1.35rem; }
		.valuation-side-card {
			padding: 1.15rem;
			display: flex;
			flex-direction: column;
			justify-content: space-between;
		}

		.valuation-eyebrow, .valuation-section-label, .valuation-side-kicker, .valuation-metric-label {
			font-size: 0.74rem;
			letter-spacing: 0.12em;
			text-transform: uppercase;
			font-weight: 800;
		}

		.valuation-eyebrow { color: #0f766e; margin-bottom: 0.7rem; }
		.valuation-section-label, .valuation-metric-label { color: #64748b; margin-bottom: 0.4rem; }
		.valuation-side-kicker { color: #7c2d12; }

		.valuation-title {
			font-size: clamp(1.75rem, 1.3rem + 1.3vw, 2.65rem);
			line-height: 0.96;
			font-weight: 900;
			letter-spacing: -0.05em;
			color: var(--valuation-ink);
			margin: 0 0 0.85rem;
		}

		.valuation-body, .valuation-side-copy, .valuation-metric-copy {
			line-height: 1.65;
			color: var(--valuation-muted);
			margin: 0;
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

		.valuation-side-value, .valuation-metric-value {
			font-weight: 900;
			letter-spacing: -0.05em;
			color: var(--valuation-ink);
			line-height: 1.1;
		}

		.valuation-side-value { font-size: 2rem; margin: 0.35rem 0 0.4rem; }
		.valuation-metric-value { font-size: 1.5rem; }

		.valuation-note {
			padding: 0.95rem 1rem;
			margin-bottom: 0.7rem;
			background: rgba(255, 251, 235, 0.84);
			border-color: rgba(217, 119, 6, 0.18);
		}

		.valuation-note strong { color: #9a3412; }
		.valuation-note span { color: #7c2d12; }

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

		[data-testid="stSegmentedControl"] {
			padding: 0.3rem;
			border-radius: 22px;
			background: rgba(255, 255, 255, 0.72);
			border: 1px solid rgba(16, 32, 51, 0.08);
		}

		[data-testid="stSegmentedControl"] label[data-selected="true"] {
			background: linear-gradient(135deg, #102033, #0f766e) !important;
			box-shadow: 0 10px 25px rgba(15, 118, 110, 0.22);
		}

		[data-testid="stSegmentedControl"] label[data-selected="true"] p {
			color: #ffffff !important;
		}

		@media (max-width: 900px) {
			.valuation-hero, .valuation-results-grid { grid-template-columns: 1fr; }
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
		        <p class="valuation-side-copy">Switch methods without leaving the page. Each framework exposes only the assumptions that materially change the valuation logic.</p>
		      </div>
		    </div>
		  </div>
		</div>
		""",
		unsafe_allow_html=True,
	)


def _input_key(scope: str, prefix: str, field: str) -> str:
	return f"valuation_{scope}_{prefix}_{field}"


def _render_note_card(note: str) -> None:
	st.markdown(
		f"<div class='valuation-note'><strong>Input check:</strong> <span>{note}</span></div>",
		unsafe_allow_html=True,
	)


def _render_section_label(label: str) -> None:
	st.markdown(f"<div class='valuation-section-label'>{label}</div>", unsafe_allow_html=True)


def _render_locked_input_cards(items: list[tuple[str, str, str]]) -> None:
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


def _run(model_label: str, growth_stage: str | None, assumptions: dict[str, float]):
	model_code = MODEL_META[model_label]["code"]
	return run_manual_valuation(model_code, growth_stage, assumptions)


def _render_fcfe_inputs(defaults: dict[str, float], growth_stage: str, scope: str):
	prefix = "fcfe"
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Starting FCFE", format_compact_currency(defaults["starting_fcfe"]), "Latest Yahoo free cash flow to equity proxy."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("Current Price", format_price(defaults["current_price"]), "Latest market price from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	cost_of_equity = col1.number_input("Cost of Equity (%)", min_value=0.1, value=float(defaults["cost_of_equity"] * 100), step=0.5, key=_input_key(scope, prefix, "cost_of_equity")) / 100
	assumptions = dict(defaults, cost_of_equity=cost_of_equity)
	if growth_stage == "Single-Stage (Stable)":
		assumptions["stable_growth"] = col2.number_input("Stable Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return _run("Free Cash Flow to Equity (FCFE) - Levered DCF", growth_stage, assumptions)
	if growth_stage == "Two-Stage":
		assumptions["high_growth"] = col2.number_input("Stage 1 Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		assumptions["projection_years"] = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		assumptions["terminal_growth"] = st.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return _run("Free Cash Flow to Equity (FCFE) - Levered DCF", growth_stage, assumptions)
	assumptions["high_growth"] = col2.number_input("High Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
	assumptions["high_growth_years"] = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
	col4, col5 = st.columns(2)
	assumptions["transition_years"] = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
	assumptions["terminal_growth"] = col5.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
	return _run("Free Cash Flow to Equity (FCFE) - Levered DCF", growth_stage, assumptions)


def _render_fcff_inputs(defaults: dict[str, float], growth_stage: str, scope: str):
	prefix = "fcff"
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Starting FCFF", format_compact_currency(defaults["starting_fcff"]), "Unlevered FCFF proxy derived from Yahoo cash flow data."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("Current Price", format_price(defaults["current_price"]), "Latest market price from Yahoo Finance."),
			("Total Debt", format_compact_currency(defaults["total_debt"]), "Latest gross debt bridge used to move from enterprise value to equity value."),
			("Cash", format_compact_currency(defaults["cash"]), "Latest balance-sheet cash and short-term investments."),
		],
	)
	col1, col2, col3 = st.columns(3)
	wacc = col1.number_input("WACC (%)", min_value=0.1, value=float(defaults["wacc"] * 100), step=0.5, key=_input_key(scope, prefix, "wacc")) / 100
	assumptions = dict(defaults, wacc=wacc)
	if growth_stage == "Single-Stage (Stable)":
		assumptions["stable_growth"] = col2.number_input("Stable Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return _run("Free Cash Flow to Firm (FCFF) - Unlevered DCF", growth_stage, assumptions)
	if growth_stage == "Two-Stage":
		assumptions["high_growth"] = col2.number_input("Stage 1 Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		assumptions["projection_years"] = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		assumptions["terminal_growth"] = st.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return _run("Free Cash Flow to Firm (FCFF) - Unlevered DCF", growth_stage, assumptions)
	assumptions["high_growth"] = col2.number_input("High Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
	assumptions["high_growth_years"] = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
	col4, col5 = st.columns(2)
	assumptions["transition_years"] = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
	assumptions["terminal_growth"] = col5.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
	return _run("Free Cash Flow to Firm (FCFF) - Unlevered DCF", growth_stage, assumptions)


def _render_ddm_inputs(defaults: dict[str, float], growth_stage: str, scope: str):
	prefix = "ddm"
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Dividend / Share", format_price(defaults["dividend_per_share"]), "Latest annual dividend per share from Yahoo Finance."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("Current Price", format_price(defaults["current_price"]), "Latest market price from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	required_return = col1.number_input("Required Return (%)", min_value=0.1, value=float(defaults["cost_of_equity"] * 100), step=0.5, key=_input_key(scope, prefix, "required_return")) / 100
	assumptions = dict(defaults, required_return=required_return)
	if growth_stage == "Single-Stage (Stable)":
		assumptions["stable_growth"] = col2.number_input("Stable Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)
	if growth_stage == "Two-Stage":
		assumptions["high_growth"] = col2.number_input("Stage 1 Dividend Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		assumptions["projection_years"] = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		assumptions["terminal_growth"] = st.number_input("Terminal Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)
	if growth_stage == "Three-Stage (Multi-stage decay)":
		assumptions["high_growth"] = col2.number_input("High Dividend Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
		assumptions["high_growth_years"] = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
		col4, col5 = st.columns(2)
		assumptions["transition_years"] = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
		assumptions["terminal_growth"] = col5.number_input("Terminal Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
		return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)
	assumptions["half_life_years"] = col2.number_input("Extraordinary Growth Half-Life (Years)", min_value=0.5, value=float(defaults["projection_years"] / 2), step=0.5, key=_input_key(scope, prefix, "half_life_years"))
	assumptions["short_term_growth"] = col3.number_input("Short-Term Dividend Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "short_term_growth")) / 100
	assumptions["stable_growth"] = st.number_input("Stable Dividend Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "stable_growth_h")) / 100
	return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)


def _render_apv_inputs(defaults: dict[str, float], scope: str):
	prefix = "apv"
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Starting FCFF", format_compact_currency(defaults["starting_fcff"]), "Latest annual free cash flow proxy from Yahoo Finance."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("Current Price", format_price(defaults["current_price"]), "Latest market price from Yahoo Finance."),
			("Total Debt", format_compact_currency(defaults["total_debt"]), "Latest annual balance-sheet debt."),
			("Cash", format_compact_currency(defaults["cash"]), "Latest annual balance-sheet cash."),
			("Tax Rate", format_percent(defaults["tax_rate"]), "Latest effective or statement-derived tax rate."),
			("Cost of Debt", format_percent(defaults["cost_of_debt"]), "Debt cost used to discount APV tax shields."),
		],
	)
	col1, col2, col3, col4 = st.columns(4)
	assumptions = dict(defaults)
	assumptions["unlevered_cost"] = col1.number_input("Unlevered Cost of Capital (%)", min_value=0.1, value=float(defaults["unlevered_cost"] * 100), step=0.5, key=_input_key(scope, prefix, "unlevered_cost")) / 100
	assumptions["high_growth"] = col2.number_input("Stage 1 Growth (%)", value=float(defaults["high_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
	assumptions["projection_years"] = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	assumptions["terminal_growth"] = col4.number_input("Terminal Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return _run("Adjusted Present Value (APV)", None, assumptions)


def _render_rim_inputs(defaults: dict[str, float], scope: str):
	prefix = "rim"
	_render_locked_inputs(
		"Yahoo market inputs",
		[
			("Book Value / Share", format_price(defaults["book_value_per_share"]), "Latest book value per share from Yahoo Finance."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("ROE", format_percent(defaults["return_on_equity"]), "Latest return on equity from Yahoo Finance."),
			("Payout Ratio", format_percent(defaults["payout_ratio"]), "Latest payout ratio from Yahoo Finance."),
			("Current Price", format_price(defaults["current_price"]), "Latest market price from Yahoo Finance."),
		],
	)
	col1, col2, col3 = st.columns(3)
	assumptions = dict(defaults)
	assumptions["cost_of_equity"] = col1.number_input("Cost of Equity (%)", min_value=0.1, value=float(defaults["cost_of_equity"] * 100), step=0.5, key=_input_key(scope, prefix, "cost_of_equity")) / 100
	assumptions["projection_years"] = int(col2.number_input("Forecast Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	assumptions["terminal_growth"] = col3.number_input("Terminal Residual Growth (%)", value=float(defaults["stable_growth"] * 100), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return _run("Residual Income Model (RIM)", None, assumptions)


def render_valuation_lab(stock_data) -> None:
	_render_valuation_shell_css()
	context = prepare_manual_valuation(stock_data)
	scope = context["scope"]
	defaults = context["defaults"]

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
		_render_note_card("Yahoo Finance inputs loaded cleanly. Only valuation assumptions such as discount rates, growth rates, and forecast length are editable.")

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
	render_result_cards(result)
	st.caption(f"Selected model: {result.model_label}. Growth structure: {result.stage_label}.")
	_render_section_label("Model diagnostics")
	render_formula_guide(model, growth_stage, result)
	render_schedule(result)
