from __future__ import annotations

import math

import streamlit as st


def _safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		numeric_value = float(value)
	except (TypeError, ValueError):
		return 0.0
	if math.isnan(numeric_value):
		return 0.0
	return numeric_value


def _format_compact_currency(value: object) -> str:
	amount = _safe_number(value)
	if amount == 0:
		return "$0.00"
	prefix = "-" if amount < 0 else ""
	abs_amount = abs(amount)
	if abs_amount >= 1_000_000_000_000:
		return f"{prefix}${abs_amount / 1_000_000_000_000:,.2f}T"
	if abs_amount >= 1_000_000_000:
		return f"{prefix}${abs_amount / 1_000_000_000:,.2f}B"
	if abs_amount >= 1_000_000:
		return f"{prefix}${abs_amount / 1_000_000:,.2f}M"
	return f"{prefix}${abs_amount:,.2f}"


def _format_shares(value: object) -> str:
	shares = _safe_number(value)
	if shares <= 0:
		return "N/A"
	return f"{shares:,.0f}"


def _format_price(value: object) -> str:
	price = _safe_number(value)
	if price <= 0:
		return "N/A"
	return f"${price:,.2f}"


def render_dcf_calculator(info_dict) -> None:
	st.subheader("DCF Calculator (Two stage FCFE)")

	current_fcf = _safe_number(info_dict.get("freeCashflow", 0))
	shares_out = _safe_number(info_dict.get("sharesOutstanding", 0))
	current_price = _safe_number(info_dict.get("currentPrice", info_dict.get("regularMarketPrice", 0)))

	if current_fcf <= 0:
		st.warning("Current Free Cash Flow is negative or missing. DCF valuation is unreliable for this asset.")
		return

	if shares_out <= 0:
		st.warning("Shares outstanding is missing. DCF valuation cannot be calculated.")
		return

	col1, col2, col3, col4 = st.columns(4)
	with col1:
		projection_years = st.number_input("Projection Years", min_value=1, max_value=20, value=5, step=1)
	with col2:
		growth_rate = st.number_input("Growth Rate (%)", value=10.0, step=0.5) / 100
	with col3:
		cost_of_equity = st.number_input("Cost of Equity (%)", value=10.0, step=0.5) / 100
	with col4:
		terminal_growth_rate = st.number_input("Terminal Growth (%)", value=2.5, step=0.5) / 100

	projection_years = int(projection_years)
	if terminal_growth_rate >= cost_of_equity:
		st.warning("Terminal Growth Rate must be lower than the Cost of Equity.")
		return

	sum_discounted_fcf = 0.0
	for year in range(1, projection_years + 1):
		future_fcf = current_fcf * (1 + growth_rate) ** year
		discounted_fcf = future_fcf / (1 + cost_of_equity) ** year
		sum_discounted_fcf += discounted_fcf

	final_year_fcf = current_fcf * (1 + growth_rate) ** projection_years
	terminal_value = (final_year_fcf * (1 + terminal_growth_rate)) / (cost_of_equity - terminal_growth_rate)
	discounted_terminal_value = terminal_value / (1 + cost_of_equity) ** projection_years
	equity_value = sum_discounted_fcf + discounted_terminal_value
	fair_value = equity_value / shares_out

	if fair_value <= 0:
		st.warning("Calculated fair value is not positive. Review the assumptions and company fundamentals.")
		return

	margin_of_safety = ((fair_value - current_price) / fair_value) * 100 if current_price > 0 else None
	mos_color = "#10B981" if margin_of_safety is not None and margin_of_safety >= 0 else "#EF4444"

	result_col1, result_col2, result_col3 = st.columns(3)
	with result_col1:
		st.markdown(
			f"<div style='text-align: left; display: flex; flex-direction: column; align-items: flex-start; gap: 6px;'>"
			f"<div style='font-size: 0.875rem; color: rgb(49, 51, 63);'>Calculated Fair Value</div>"
			f"<div style='font-size: 1.5rem; font-weight: 600; color: rgb(49, 51, 63); line-height: 1.2;'>${fair_value:,.2f}</div>"
			f"</div>",
			unsafe_allow_html=True,
		)
	with result_col2:
		st.markdown(
			f"<div style='text-align: left; display: flex; flex-direction: column; align-items: flex-start; gap: 6px;'>"
			f"<div style='font-size: 0.875rem; color: rgb(49, 51, 63);'>Current Price</div>"
			f"<div style='font-size: 1.5rem; font-weight: 600; color: rgb(49, 51, 63); line-height: 1.2;'>${current_price:,.2f}</div>"
			f"</div>",
			unsafe_allow_html=True,
		)
	with result_col3:
		st.markdown(
			f"<div style='text-align: left; display: flex; flex-direction: column; align-items: flex-start; gap: 6px;'>"
			f"<div style='font-size: 0.875rem; color: rgb(49, 51, 63);'>Margin of Safety</div>"
			f"<div style='font-size: 1.5rem; font-weight: 600; color: {mos_color}; line-height: 1.2;'>{'N/A' if margin_of_safety is None else f'{margin_of_safety:.2f}%'} </div>"
			f"</div>",
			unsafe_allow_html=True,
		)

	st.write("")

	with st.expander("View Math & Formulas"):
		st.markdown(
			"""
			<div style="padding: 16px 18px; border-radius: 18px; background: linear-gradient(135deg, rgba(239,246,255,0.95), rgba(236,253,245,0.9)); border: 1px solid rgba(148,163,184,0.22); margin-bottom: 16px;">
			  <div style="font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 4px;">FCFE Formula Guide</div>
			  <div style="font-size: 0.96rem; color: #334155; line-height: 1.55;">This model discounts levered free cash flow directly to equity. The cards below show the exact variables and live values used in the FCFE calculation.</div>
			</div>
			""",
			unsafe_allow_html=True,
		)

		guide_top_1, guide_top_2, guide_top_3, guide_top_4 = st.columns(4)
		guide_top_1.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #2563eb;">FCF_0</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Starting free cash flow</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{_format_compact_currency(current_fcf)}</div>
			</div>
			""",
			unsafe_allow_html=True,
		)
		guide_top_2.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #2563eb;">n</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Projection years</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{projection_years} years</div>
			</div>
			""",
			unsafe_allow_html=True,
		)
		guide_top_3.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #2563eb;">g</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Growth rate</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{growth_rate * 100:.1f}%</div>
			</div>
			""",
			unsafe_allow_html=True,
		)
		guide_top_4.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #2563eb;">r</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Cost of equity</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{cost_of_equity * 100:.1f}%</div>
			</div>
			""",
			unsafe_allow_html=True,
		)

		st.write("")

		guide_bottom_1, guide_bottom_2, guide_bottom_3, guide_bottom_4 = st.columns(4)
		guide_bottom_1.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #10b981;">g_term</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Terminal growth rate</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{terminal_growth_rate * 100:.1f}%</div>
			</div>
			""",
			unsafe_allow_html=True,
		)
		guide_bottom_2.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #10b981;">Price</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Current market price</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{_format_price(current_price)}</div>
			</div>
			""",
			unsafe_allow_html=True,
		)
		guide_bottom_3.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #10b981;">Equity</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Present value of all FCFE</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{_format_compact_currency(equity_value)}</div>
			</div>
			""",
			unsafe_allow_html=True,
		)
		guide_bottom_4.markdown(
			f"""
			<div style="padding: 14px; border-radius: 16px; background: #f8fafc; border: 1px solid rgba(148,163,184,0.2); min-height: 118px;">
			  <div style="font-size: 0.78rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: #10b981;">TV (PV)</div>
			  <div style="font-size: 0.95rem; color: #334155; margin-top: 6px;">Discounted terminal value</div>
			  <div style="font-size: 1.15rem; font-weight: 700; color: #0f172a; margin-top: 10px;">{_format_compact_currency(discounted_terminal_value)}</div>
			</div>
			""",
			unsafe_allow_html=True,
		)

		st.markdown("### Core Formulas")
		st.caption("These are the four building blocks of the FCFE model, shown in the order they are applied.")
		st.write("")
		st.markdown("#### 1. Project Free Cash Flow to Equity")
		st.latex(r"FCF_t = FCF_0 \times (1 + g)^t")
		st.markdown("#### 2. Discount Each FCFE Back to Today")
		st.latex(r"PV(FCF_t) = \frac{FCF_t}{(1 + r)^t}")
		st.markdown("#### 3. Estimate and Discount Terminal Value")
		st.latex(r"TV = \frac{FCF_n \times (1 + g_{term})}{r - g_{term}}")
		st.write("")
		st.latex(r"PV(TV) = \frac{TV}{(1 + r)^n}")
		st.markdown("#### 4. Convert Discounted FCFE into Fair Value Per Share")
		st.latex(r"Equity\ Value = \sum_{t=1}^{n} PV(FCF_t) + PV(TV)")
		st.write("")
		st.latex(r"Fair\ Value\ Per\ Share = \frac{Equity\ Value}{Shares}")