from __future__ import annotations

import pandas as pd
import streamlit as st

from data.normalization import format_compact_currency, format_percent, format_price
from valuation.types import ValuationResult


def render_result_cards(result: ValuationResult) -> None:
	margin_text = "N/A" if result.margin_of_safety is None else f"{result.margin_of_safety:.2f}%"
	present_value_label = "PV of Explicit Forecast" if result.discounted_terminal_value > 0 else "Core Present Value"
	third_label = "PV of Tax Shield" if result.tax_shield_value is not None else "Enterprise Value" if result.enterprise_value is not None else "Discounted Terminal Value"
	third_value = format_compact_currency(result.tax_shield_value if result.tax_shield_value is not None else result.enterprise_value if result.enterprise_value is not None else result.discounted_terminal_value)

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
		    <div class="valuation-metric-value">{format_price(result.current_price)}</div>
		    <div class="valuation-metric-copy">Spot market price used to compute the live gap versus fair value.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Margin of Safety</div>
		    <div class="valuation-metric-value">{margin_text}</div>
		    <div class="valuation-metric-copy">Positive means implied upside. Negative means the market is richer than your inputs.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Equity Value</div>
		    <div class="valuation-metric-value">{format_compact_currency(result.equity_value)}</div>
		    <div class="valuation-metric-copy">Total equity value produced after the model-specific bridge from operations to shareholders.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">{present_value_label}</div>
		    <div class="valuation-metric-value">{format_compact_currency(result.present_value_of_cash_flows)}</div>
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


def render_schedule(result: ValuationResult) -> None:
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


def render_formula_guide(model_label: str, growth_stage: str | None, result: ValuationResult) -> None:
	with st.expander("View Math & Formulas", expanded=False):
		st.markdown(f"**Model:** {model_label}")
		if growth_stage:
			st.markdown(f"**Growth assumption:** {growth_stage}")

		if model_label.startswith("Free Cash Flow to Equity"):
			st.latex(r"FCFE_t = FCFE_{t-1} \times (1 + g_t)")
			st.latex(r"Equity\ Value = \sum_{t=1}^{n}\frac{FCFE_t}{(1 + r)^t} + \frac{FCFE_n(1+g_{term})}{(r-g_{term})(1+r)^n}")
		elif model_label.startswith("Free Cash Flow to Firm"):
			st.latex(r"FCFF_t = FCFF_{t-1} \times (1 + g_t)")
			st.latex(r"Enterprise\ Value = \sum_{t=1}^{n}\frac{FCFF_t}{(1 + WACC)^t} + \frac{FCFF_n(1+g_{term})}{(WACC-g_{term})(1+WACC)^n}")
			st.latex(r"Equity\ Value = Enterprise\ Value - Debt + Cash")
		elif model_label.startswith("Dividend Discount Model") and growth_stage == "H-Model":
			st.latex(r"P_0 = \frac{D_0(1+g_L) + D_0H(g_S-g_L)}{r-g_L}")
		elif model_label.startswith("Dividend Discount Model"):
			st.latex(r"D_t = D_{t-1} \times (1 + g_t)")
			st.latex(r"P_0 = \sum_{t=1}^{n}\frac{D_t}{(1 + r)^t} + \frac{D_n(1+g_{term})}{(r-g_{term})(1+r)^n}")
		elif model_label.startswith("Adjusted Present Value"):
			st.latex(r"APV = PV\ of\ Unlevered\ Operations + PV\ of\ Financing\ Side\ Effects")
			st.latex(r"Equity\ Value = APV - Debt + Cash")
		elif model_label.startswith("Residual Income"):
			st.latex(r"EPS_t = ROE \times BV_{t-1}")
			st.latex(r"BV_t = BV_{t-1} + EPS_t - DPS_t")
			st.latex(r"RI_t = EPS_t - r \times BV_{t-1}")
			st.latex(r"Value_0 = BV_0 + \sum_{t=1}^{n}\frac{RI_t}{(1+r)^t} + \frac{RI_{n+1}}{(r-g_{term})(1+r)^n},\quad RI_{n+1}=RI_n(1+g_{term})")

		st.caption(
			f"Implied fair value per share: ${result.fair_value_per_share:,.2f}. "
			f"Explicit forecast PV: {format_compact_currency(result.present_value_of_cash_flows)}."
		)


def render_ai_summary(valuation_pick: dict[str, object]) -> None:
	st.markdown(
		f"""
		<div class="valuation-results-grid">
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">AI Model</div>
		    <div class="valuation-metric-value">{valuation_pick.get('selected_model', 'N/A')}</div>
		    <div class="valuation-metric-copy">{valuation_pick.get('growth_stage') or 'No growth-stage variant'}</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">AI Fair Value</div>
		    <div class="valuation-metric-value">{format_price(valuation_pick.get('fair_value_per_share'))}</div>
		    <div class="valuation-metric-copy">Deterministic Python result using AI-selected assumptions.</div>
		  </div>
		  <div class="valuation-metric-card">
		    <div class="valuation-metric-label">Margin of Safety</div>
		    <div class="valuation-metric-value">{format_percent((valuation_pick.get('margin_of_safety') or 0) / 100, allow_negative=True) if valuation_pick.get('margin_of_safety') is not None else 'N/A'}</div>
		    <div class="valuation-metric-copy">Computed after Python valuation ran.</div>
		  </div>
		</div>
		""",
		unsafe_allow_html=True,
	)
