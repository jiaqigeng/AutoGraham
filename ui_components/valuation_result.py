from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from data.normalization import format_compact_currency, format_percent, format_price
from valuation.types import ValuationResult


def render_result_cards(result: ValuationResult) -> None:
	margin_text = "N/A" if result.margin_of_safety is None else f"{result.margin_of_safety:.2f}%"
	margin_tone = "is-positive" if (result.margin_of_safety or 0) > 0 else "is-negative" if (result.margin_of_safety or 0) < 0 else ""
	cards = [
		("Current Price", format_price(result.current_price), "Spot market price used to compute the live gap versus fair value.", ""),
		("Fair Value / Share", f"${result.fair_value_per_share:,.2f}", "Intrinsic value per share implied by the selected framework.", ""),
		("Margin of Safety", margin_text, "Positive means implied upside. Negative means the market is richer than your inputs.", margin_tone),
	]
	card_html = "".join(
		(
			f"<div class='ai-dashboard-metric-card {tone}'>"
			f"<div class='ai-dashboard-metric-label'>{html.escape(label)}</div>"
			f"<div class='ai-dashboard-metric-value'>{html.escape(value)}</div>"
			f"<div class='valuation-lab-metric-copy'>{html.escape(copy)}</div>"
			"</div>"
		)
		for label, value, copy, tone in cards
	)

	st.markdown(
		f"<div class='ai-dashboard-metrics valuation-lab-metrics'>{card_html}</div>",
		unsafe_allow_html=True,
	)


def render_schedule(result: ValuationResult) -> None:
	if not result.schedule:
		return
	with st.expander("Projection schedule", expanded=False):
		schedule_frame = pd.DataFrame(result.schedule)
		for column in schedule_frame.columns:
			if schedule_frame[column].dtype.kind in {"f", "i"} and column != "Year":
				if "Rate" in column or "Margin" in column or "Weight" in column or column == "ROE":
					schedule_frame[column] = schedule_frame[column].map(lambda value: f"{value * 100:.2f}%")
				elif "Factor" in column or column == "Beta":
					schedule_frame[column] = schedule_frame[column].map(lambda value: f"{value:,.4f}")
				else:
					schedule_frame[column] = schedule_frame[column].map(lambda value: f"${value:,.2f}")
		st.dataframe(schedule_frame, width="stretch", hide_index=True)


def render_formula_guide(model_label: str, growth_stage: str | None, result: ValuationResult) -> None:
	with st.expander("View Math & Formulas", expanded=False):
		st.markdown(f"**Model:** {model_label}")
		if growth_stage:
			st.markdown(f"**Growth assumption:** {growth_stage}")

		if model_label.startswith("Free Cash Flow to Equity"):
			st.markdown("Simple FCFE DCF used in Valuation Lab:")
			st.latex(r"FCFE_t = FCFE_{t-1} \times (1 + g)")
			st.latex(r"FCFE_1 = Current\ FCFE \times (1 + g)")
			st.latex(r"PV(FCFE_t) = \frac{FCFE_t}{(1 + r)^t}")
			st.latex(r"TV = \frac{FCFE_N(1+g_{term})}{r-g_{term}}")
			st.latex(r"Equity\ Value = \sum_{t=1}^{N}\frac{FCFE_t}{(1 + r)^t} + \frac{TV}{(1+r)^N}")
			st.latex(r"Fair\ Value\ Per\ Share = \frac{Equity\ Value}{Shares\ Outstanding}")
		elif model_label.startswith("Free Cash Flow to Firm"):
			st.markdown("Simple FCFF DCF used in Valuation Lab:")
			st.latex(r"FCFF_t = FCFF_{t-1} \times (1 + g)")
			st.latex(r"FCFF_1 = Current\ FCFF \times (1 + g)")
			st.latex(r"PV(FCFF_t) = \frac{FCFF_t}{(1 + WACC)^t}")
			st.latex(r"TV = \frac{FCFF_N(1+g_{term})}{WACC-g_{term}}")
			st.latex(r"Enterprise\ Value = \sum_{t=1}^{N}\frac{FCFF_t}{(1 + WACC)^t} + \frac{TV}{(1+WACC)^N}")
			st.latex(r"Equity\ Value = Enterprise\ Value - Debt + Cash")
			st.latex(r"Fair\ Value\ Per\ Share = \frac{Equity\ Value}{Shares\ Outstanding}")
		elif model_label.startswith("Dividend Discount Model") and growth_stage == "H-Model":
			st.latex(r"P_0 = \frac{D_0(1+g_L) + D_0H(g_S-g_L)}{r-g_L}")
		elif model_label.startswith("Dividend Discount Model"):
			st.latex(r"D_t = D_{t-1} \times (1 + g_t)")
			st.latex(r"P_0 = \sum_{t=1}^{n}\frac{D_t}{(1 + r)^t} + \frac{D_n(1+g_{term})}{(r-g_{term})(1+r)^n}")
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
	margin_value = format_percent((valuation_pick.get("margin_of_safety") or 0) / 100, allow_negative=True) if valuation_pick.get("margin_of_safety") is not None else "N/A"
	margin_raw = valuation_pick.get("margin_of_safety")
	try:
		margin_number = float(margin_raw) if margin_raw is not None else 0.0
	except (TypeError, ValueError):
		margin_number = 0.0
	margin_tone = "is-positive" if margin_number > 0 else "is-negative" if margin_number < 0 else ""
	cards = [
		("AI Model", str(valuation_pick.get("selected_model", "N/A")), str(valuation_pick.get("growth_stage") or "No growth-stage variant"), ""),
		("AI Fair Value", format_price(valuation_pick.get("fair_value_per_share")), "Deterministic Python result using AI-selected assumptions.", ""),
		("Margin of Safety", margin_value, "Computed after Python valuation ran.", margin_tone),
	]
	card_html = "".join(
		(
			f"<div class='ai-dashboard-metric-card {tone}'>"
			f"<div class='ai-dashboard-metric-label'>{html.escape(label)}</div>"
			f"<div class='ai-dashboard-metric-value'>{html.escape(value)}</div>"
			f"<div class='valuation-lab-metric-copy'>{html.escape(copy)}</div>"
			"</div>"
		)
		for label, value, copy, tone in cards
	)
	st.markdown(
		f"<div class='ai-dashboard-metrics valuation-lab-metrics'>{card_html}</div>",
		unsafe_allow_html=True,
	)
