from __future__ import annotations

import html

import streamlit as st

from data.normalization import format_compact_currency, format_percent, format_price, format_shares
from ui_components.valuation_result import render_formula_guide, render_result_cards, render_schedule
from workflows.manual_valuation import GROWTH_OPTIONS, MODEL_META, prepare_manual_valuation, run_manual_valuation


MODEL_FAMILY_OPTIONS = ["DCF", "DDM", "RIM"]
DCF_METHOD_OPTIONS = [
	"Free Cash Flow to Firm (FCFF) - Unlevered DCF",
	"Free Cash Flow to Equity (FCFE) - Levered DCF",
]


def _half_step(value: float) -> float:
	return round(float(value) * 2) / 2


def _percent_display_default(value: float) -> float:
	return _half_step(float(value) * 100)


def _render_valuation_shell_css() -> None:
	st.markdown(
		"""
		<style>
		div[data-testid="stVerticalBlock"]:has(> div div.valuation-dashboard-anchor) {
			margin-top: 0.5rem;
			padding: 1.45rem;
			border-radius: 32px;
			background:
				radial-gradient(circle at top right, rgba(14, 116, 144, 0.18), transparent 24%),
				radial-gradient(circle at bottom left, rgba(15, 118, 110, 0.12), transparent 22%),
				linear-gradient(180deg, rgba(255,255,255,0.96), rgba(241,245,249,0.94) 100%);
			border: 1px solid var(--ag-line-strong);
			box-shadow: 0 28px 60px rgba(15, 23, 42, 0.12);
			backdrop-filter: blur(14px);
		}

		div[data-testid="stVerticalBlock"]:has(> div div.valuation-dashboard-anchor) > div {
			gap: 1rem;
		}

		div[data-testid="stVerticalBlock"]:has(> div div.valuation-section-anchor) {
			padding: 1rem 1.1rem 1.1rem;
			border-radius: 24px;
			background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(248,250,252,0.9));
			border: 1px solid var(--ag-line);
			box-shadow:
				inset 0 1px 0 rgba(255,255,255,0.72),
				0 12px 28px rgba(15, 23, 42, 0.05);
		}

		div[data-testid="stVerticalBlock"]:has(> div div.valuation-section-anchor) > div {
			gap: 0.85rem;
		}

		.valuation-dashboard-anchor,
		.valuation-section-anchor {
			display: block;
			width: 0;
			height: 0;
			margin: 0;
			overflow: hidden;
		}

		.valuation-lab-metrics {
			grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
			margin: 0;
		}

		.valuation-lab-metric-copy {
			margin-top: 0.5rem;
			font-size: var(--ag-body-tight);
			line-height: 1.65;
			color: var(--ag-ink-soft);
		}

		.valuation-lab-caption {
			margin: 0;
			font-size: var(--ag-body-tight);
			line-height: 1.7;
			color: var(--ag-ink-soft);
		}

		.valuation-lab-section-copy {
			margin-bottom: 0.1rem;
		}

		.valuation-lab-subsection-gap {
			margin-top: 0.75rem;
		}

		div[data-testid="stSegmentedControl"] label p,
		div[data-testid="stNumberInput"] label p {
			font-size: 0.78rem;
			font-weight: 800;
			letter-spacing: 0.1em;
			text-transform: uppercase;
			color: var(--ag-muted);
		}

		div[data-testid="stSegmentedControl"] {
			padding: 0.35rem;
			border-radius: 22px;
			background: linear-gradient(180deg, rgba(248,250,252,0.96), rgba(255,255,255,0.9));
			border: 1px solid rgba(148, 163, 184, 0.22);
			box-shadow:
				inset 0 1px 0 rgba(255,255,255,0.8),
				0 10px 24px rgba(15, 23, 42, 0.05);
			overflow: hidden;
		}

		div[data-testid="stSegmentedControl"] > div {
			gap: 0.3rem;
		}

		div[data-testid="stSegmentedControl"] label {
			min-height: 2.7rem;
			border-radius: 16px !important;
			border: 1px solid transparent !important;
			background: rgba(255, 255, 255, 0.72) !important;
			box-shadow: inset 0 1px 0 rgba(255,255,255,0.84);
			transition:
				transform 160ms ease,
				background 160ms ease,
				border-color 160ms ease,
				box-shadow 160ms ease;
		}

		div[data-testid="stSegmentedControl"] label:hover {
			transform: translateY(-1px);
			background: rgba(255, 255, 255, 0.94) !important;
			border-color: rgba(56, 189, 248, 0.24) !important;
			box-shadow:
				inset 0 1px 0 rgba(255,255,255,0.9),
				0 8px 18px rgba(14, 116, 144, 0.08);
		}

		[data-testid="stSegmentedControl"] label[data-selected="true"],
		[data-testid="stSegmentedControl"] label:has(input:checked) {
			background: linear-gradient(135deg, #0f172a 0%, #0f766e 58%, #14b8a6 100%) !important;
			border-color: rgba(15, 118, 110, 0.35) !important;
			box-shadow:
				inset 0 1px 0 rgba(255,255,255,0.16),
				0 12px 24px rgba(15, 118, 110, 0.18);
			transform: translateY(-1px);
		}

		[data-testid="stSegmentedControl"] label p {
			color: var(--ag-ink-strong) !important;
			font-size: 0.9rem !important;
			font-weight: 700 !important;
			letter-spacing: -0.01em !important;
			text-transform: none !important;
			transition: color 160ms ease;
		}

		[data-testid="stSegmentedControl"] label[data-selected="true"] p,
		[data-testid="stSegmentedControl"] label:has(input:checked) p {
			color: #ffffff !important;
			font-weight: 800 !important;
		}

		[data-testid="stSegmentedControl"] label:focus-within,
		[data-testid="stSegmentedControl"] label:has(input:focus-visible) {
			outline: none !important;
			border-color: rgba(56, 189, 248, 0.34) !important;
			box-shadow:
				0 0 0 0.2rem rgba(56, 189, 248, 0.14),
				0 10px 22px rgba(14, 116, 144, 0.1) !important;
		}

		div[data-testid="stNumberInput"] input {
			min-height: 3rem;
			border-radius: 18px;
			border: 1px solid rgba(148, 163, 184, 0.24);
			background: rgba(255, 255, 255, 0.86);
			box-shadow:
				inset 0 1px 0 rgba(255,255,255,0.68),
				0 12px 30px rgba(15, 23, 42, 0.05);
			font-size: 1rem;
			font-weight: 700;
			color: var(--ag-ink-strong);
		}

		div[data-testid="stNumberInput"] input:focus {
			border-color: rgba(14, 116, 144, 0.38);
			box-shadow:
				0 0 0 0.22rem rgba(56, 189, 248, 0.14),
				0 12px 30px rgba(15, 23, 42, 0.05);
		}

		div[data-testid="stExpander"] {
			border: 1px solid var(--ag-line) !important;
			border-radius: 20px !important;
			background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,252,0.92)) !important;
			box-shadow:
				inset 0 1px 0 rgba(255,255,255,0.72),
				0 10px 26px rgba(15, 23, 42, 0.05);
			overflow: hidden;
		}

		div[data-testid="stExpander"] details {
			border: 0 !important;
			background: transparent !important;
		}

		div[data-testid="stExpander"] summary {
			font-weight: 800 !important;
			letter-spacing: -0.01em;
			color: var(--ag-ink-strong) !important;
		}
		</style>
		""",
		unsafe_allow_html=True,
	)

def _render_section_intro(title: str, body: str | None = None, extra_class: str = "") -> None:
	class_attr = f"ai-dashboard-panel-title {extra_class}".strip()
	st.markdown(f"<div class='{class_attr}'>{html.escape(title)}</div>", unsafe_allow_html=True)
	if body:
		st.markdown(
			f"<p class='ai-dashboard-panel-copy valuation-lab-section-copy'>{html.escape(body)}</p>",
			unsafe_allow_html=True,
		)


def _input_key(scope: str, prefix: str, field: str) -> str:
	return f"valuation_{scope}_{prefix}_{field}"


def _render_locked_input_cards(items: list[tuple[str, str, str]]) -> None:
	card_html = "".join(
		(
			"<div class='ai-dashboard-metric-card'>"
			f"<div class='ai-dashboard-metric-label'>{html.escape(label)}</div>"
			f"<div class='ai-dashboard-metric-value'>{html.escape(value)}</div>"
			f"<div class='valuation-lab-metric-copy'>{html.escape(copy)}</div>"
			"</div>"
		)
		for label, value, copy in items
	)
	st.markdown(f"<div class='ai-dashboard-metrics valuation-lab-metrics'>{card_html}</div>", unsafe_allow_html=True)


def _render_locked_inputs(label: str, items: list[tuple[str, str, str]]) -> None:
	_render_section_intro(label, "Pulled from Yahoo Finance and locked for this valuation run.")
	_render_locked_input_cards(items)


def _run(model_label: str, growth_stage: str | None, assumptions: dict[str, float]):
	model_code = MODEL_META[model_label]["code"]
	return run_manual_valuation(model_code, growth_stage, assumptions)


def _render_fcfe_inputs(defaults: dict[str, float], growth_stage: str, scope: str):
	prefix = "fcfe"
	_render_locked_inputs(
		"Yahoo Inputs",
		[
			("Starting FCFE", format_compact_currency(defaults["starting_fcfe"]), "Latest Yahoo free cash flow to equity proxy."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
		],
	)
	_render_section_intro("User Inputs", "Only the assumptions that materially change the valuation are editable here.", extra_class="valuation-lab-subsection-gap")
	col1, col2, col3, col4 = st.columns(4)
	assumptions = dict(defaults)
	assumptions["cost_of_equity"] = col1.number_input("Cost of Equity (%)", min_value=0.1, value=_percent_display_default(defaults["cost_of_equity"]), step=0.5, key=_input_key(scope, prefix, "cost_of_equity")) / 100
	assumptions["growth_rate"] = col2.number_input("FCFE Growth Rate (%)", value=_percent_display_default(defaults["high_growth"]), step=0.5, key=_input_key(scope, prefix, "growth_rate")) / 100
	assumptions["projection_years"] = int(col3.number_input("Projection Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	assumptions["terminal_growth"] = col4.number_input("Terminal Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return _run("Free Cash Flow to Equity (FCFE) - Levered DCF", None, assumptions)


def _render_fcff_inputs(defaults: dict[str, float], growth_stage: str, scope: str):
	prefix = "fcff"
	_render_locked_inputs(
		"Yahoo Inputs",
		[
			("Starting FCFF", format_compact_currency(defaults["starting_fcff"]), "Unlevered FCFF proxy derived from Yahoo cash flow data."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("Total Debt", format_compact_currency(defaults["total_debt"]), "Latest gross debt bridge used to move from enterprise value to equity value."),
			("Cash", format_compact_currency(defaults["cash"]), "Latest balance-sheet cash and short-term investments."),
		],
	)
	_render_section_intro("User Inputs", "Only the assumptions that materially change the valuation are editable here.", extra_class="valuation-lab-subsection-gap")
	col1, col2, col3, col4 = st.columns(4)
	assumptions = dict(defaults)
	assumptions["wacc"] = col1.number_input("WACC (%)", min_value=0.1, value=_percent_display_default(defaults["wacc"]), step=0.5, key=_input_key(scope, prefix, "wacc")) / 100
	assumptions["growth_rate"] = col2.number_input("FCFF Growth Rate (%)", value=_percent_display_default(defaults["high_growth"]), step=0.5, key=_input_key(scope, prefix, "growth_rate")) / 100
	assumptions["projection_years"] = int(col3.number_input("Projection Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	assumptions["terminal_growth"] = col4.number_input("Terminal Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return _run("Free Cash Flow to Firm (FCFF) - Unlevered DCF", None, assumptions)


def _render_ddm_inputs(defaults: dict[str, float], growth_stage: str, scope: str):
	prefix = "ddm"
	_render_locked_inputs(
		"Yahoo Inputs",
		[
			("Dividend / Share", format_price(defaults["dividend_per_share"]), "Latest annual dividend per share from Yahoo Finance."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
		],
	)
	_render_section_intro("User Inputs", "Only the assumptions that materially change the valuation are editable here.", extra_class="valuation-lab-subsection-gap")
	assumptions = dict(defaults)
	if growth_stage == "Single-Stage (Stable)":
		col1, col2 = st.columns(2)
		assumptions["required_return"] = col1.number_input("Required Return (%)", min_value=0.1, value=_percent_display_default(defaults["cost_of_equity"]), step=0.5, key=_input_key(scope, prefix, "required_return")) / 100
		assumptions["stable_growth"] = col2.number_input("Stable Dividend Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "stable_growth")) / 100
		return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)
	if growth_stage == "Two-Stage":
		col1, col2, col3, col4 = st.columns(4)
		assumptions["required_return"] = col1.number_input("Required Return (%)", min_value=0.1, value=_percent_display_default(defaults["cost_of_equity"]), step=0.5, key=_input_key(scope, prefix, "required_return_two")) / 100
		assumptions["high_growth"] = col2.number_input("Stage 1 Dividend Growth (%)", value=_percent_display_default(defaults["high_growth"]), step=0.5, key=_input_key(scope, prefix, "high_growth")) / 100
		assumptions["projection_years"] = int(col3.number_input("Stage 1 Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
		assumptions["terminal_growth"] = col4.number_input("Terminal Dividend Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
		return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)
	if growth_stage == "Three-Stage (Multi-stage decay)":
		col1, col2, col3 = st.columns(3)
		assumptions["required_return"] = col1.number_input("Required Return (%)", min_value=0.1, value=_percent_display_default(defaults["cost_of_equity"]), step=0.5, key=_input_key(scope, prefix, "required_return_three")) / 100
		assumptions["high_growth"] = col2.number_input("High Dividend Growth (%)", value=_percent_display_default(defaults["high_growth"]), step=0.5, key=_input_key(scope, prefix, "high_growth_three")) / 100
		assumptions["high_growth_years"] = int(col3.number_input("High Growth Years", min_value=1, max_value=20, value=int(defaults["high_growth_years"]), step=1, key=_input_key(scope, prefix, "high_growth_years")))
		col4, col5 = st.columns(2)
		assumptions["transition_years"] = int(col4.number_input("Fade Years", min_value=1, max_value=20, value=int(defaults["transition_years"]), step=1, key=_input_key(scope, prefix, "transition_years")))
		assumptions["terminal_growth"] = col5.number_input("Terminal Dividend Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "terminal_growth_three")) / 100
		return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)
	col1, col2, col3, col4 = st.columns(4)
	assumptions["required_return"] = col1.number_input("Required Return (%)", min_value=0.1, value=_percent_display_default(defaults["cost_of_equity"]), step=0.5, key=_input_key(scope, prefix, "required_return_h")) / 100
	assumptions["half_life_years"] = col2.number_input("Extraordinary Growth Half-Life (Years)", min_value=0.5, value=_half_step(float(defaults["projection_years"]) / 2), step=0.5, key=_input_key(scope, prefix, "half_life_years"))
	assumptions["short_term_growth"] = col3.number_input("Short-Term Dividend Growth (%)", value=_percent_display_default(defaults["high_growth"]), step=0.5, key=_input_key(scope, prefix, "short_term_growth")) / 100
	assumptions["stable_growth"] = col4.number_input("Stable Dividend Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "stable_growth_h")) / 100
	return _run("Dividend Discount Model (DDM)", growth_stage, assumptions)


def _render_rim_inputs(defaults: dict[str, float], scope: str):
	prefix = "rim"
	_render_locked_inputs(
		"Yahoo Inputs",
		[
			("Book Value / Share", format_price(defaults["book_value_per_share"]), "Latest book value per share from Yahoo Finance."),
			("Shares Outstanding", format_shares(defaults["shares_outstanding"]), "Current share-count proxy used for per-share valuation."),
			("ROE", format_percent(defaults["return_on_equity"]), "Latest return on equity from Yahoo Finance."),
			("Payout Ratio", format_percent(defaults["payout_ratio"]), "Latest payout ratio from Yahoo Finance."),
		],
	)
	_render_section_intro("User Inputs", "Only the assumptions that materially change the valuation are editable here.", extra_class="valuation-lab-subsection-gap")
	col1, col2, col3 = st.columns(3)
	assumptions = dict(defaults)
	assumptions["cost_of_equity"] = col1.number_input("Cost of Equity (%)", min_value=0.1, value=_percent_display_default(defaults["cost_of_equity"]), step=0.5, key=_input_key(scope, prefix, "cost_of_equity")) / 100
	assumptions["projection_years"] = int(col2.number_input("Forecast Years", min_value=1, max_value=20, value=int(defaults["projection_years"]), step=1, key=_input_key(scope, prefix, "projection_years")))
	assumptions["terminal_growth"] = col3.number_input("Terminal Residual Growth (%)", value=_percent_display_default(defaults["stable_growth"]), step=0.5, key=_input_key(scope, prefix, "terminal_growth")) / 100
	return _run("Residual Income Model (RIM)", None, assumptions)


def render_valuation_lab(stock_data) -> None:
	_render_valuation_shell_css()
	context = prepare_manual_valuation(stock_data)
	scope = context["scope"]
	defaults = context["defaults"]

	with st.container():
		st.markdown('<div class="valuation-dashboard-anchor"></div>', unsafe_allow_html=True)

		with st.container():
			st.markdown('<div class="valuation-section-anchor"></div>', unsafe_allow_html=True)
			_render_section_intro(
				"Fair Value Estimation",
				"Pick the framework first, then adjust only the forecast assumptions that change the valuation logic.",
			)
			model_family = st.segmented_control(
				"Valuation model",
				options=MODEL_FAMILY_OPTIONS,
				default="DCF",
				key=f"valuation_family_{scope}",
				width="stretch",
			)

			if model_family == "DCF":
				model = st.segmented_control(
					"DCF approach",
					options=DCF_METHOD_OPTIONS,
					default=DCF_METHOD_OPTIONS[0],
					format_func=lambda option: MODEL_META[option]["short"],
					key=f"valuation_model_{scope}",
					width="stretch",
				)
			elif model_family == "DDM":
				model = "Dividend Discount Model (DDM)"
			else:
				model = "Residual Income Model (RIM)"

			growth_stage: str | None = None
			if model == "Dividend Discount Model (DDM)":
				growth_options = list(GROWTH_OPTIONS)
				growth_options.append("H-Model")
				growth_stage = st.segmented_control(
					"Growth stage assumption",
					options=growth_options,
					default=growth_options[1] if "Two-Stage" in growth_options else growth_options[0],
					key=f"growth_stage_{scope}_{model}",
					width="stretch",
				)

		with st.container():
			st.markdown('<div class="valuation-section-anchor"></div>', unsafe_allow_html=True)
			_render_section_intro("Assumption Builder")
			try:
				if model == "Free Cash Flow to Equity (FCFE) - Levered DCF":
					result = _render_fcfe_inputs(defaults, growth_stage or "Simple DCF", scope)
				elif model == "Free Cash Flow to Firm (FCFF) - Unlevered DCF":
					result = _render_fcff_inputs(defaults, growth_stage or "Simple DCF", scope)
				elif model == "Dividend Discount Model (DDM)":
					result = _render_ddm_inputs(defaults, growth_stage or "Two-Stage", scope)
				else:
					result = _render_rim_inputs(defaults, scope)
			except ValueError as exc:
				st.warning(str(exc))
				return

		if result.fair_value_per_share <= 0:
			st.warning("Calculated fair value is not positive. Review the assumptions and company fundamentals.")
			return

		with st.container():
			st.markdown('<div class="valuation-section-anchor"></div>', unsafe_allow_html=True)
			_render_section_intro(
				"Valuation Output",
				"Compare the live market price, estimated fair value, and implied margin of safety.",
			)
			render_result_cards(result)

		with st.container():
			st.markdown('<div class="valuation-section-anchor"></div>', unsafe_allow_html=True)
			_render_section_intro(
				"Model Diagnostics",
				"Open the schedules and formulas below to audit the valuation math without leaving the page.",
			)
			render_formula_guide(model, growth_stage, result)
			render_schedule(result)
