from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

from data.financial_statements import (
	build_income_waterfall_figure,
	extract_quarter_metrics,
	format_period_label,
	get_display_period_columns,
)
from data.normalization import format_compact_currency, format_market_cap, format_percent, format_price, format_ratio
from valuation.common import safe_number


def inject_global_styles() -> None:
	css_path = Path(__file__).resolve().parents[1] / "assets" / "styles.css"
	if css_path.exists():
		st.markdown(f"<style>{css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


def render_ticker_input(label: str = "Stock ticker", default: str = "") -> str:
	current_value = st.session_state.get("selected_ticker", default)
	ticker = st.text_input(label, value=current_value).strip().upper()
	st.session_state["selected_ticker"] = ticker
	return ticker


def render_page_hero(
	title: str,
	description: str,
	*,
	eyebrow: str | None = None,
	status: str | None = None,
	pills: list[str] | None = None,
) -> None:
	title_markup = ""
	if title:
		title_markup = f'<h1 class="ag-page-hero-title">{escape(title)}</h1>'

	pills_markup = ""
	if pills:
		pills_markup = "".join(
			f'<span class="ag-page-hero-pill">{escape(pill)}</span>' for pill in pills if pill
		)
		pills_markup = f'<div class="ag-page-hero-pills">{pills_markup}</div>'

	status_markup = ""
	if status:
		status_markup = f'<div class="ag-page-hero-status">{escape(status)}</div>'

	eyebrow_markup = ""
	if eyebrow:
		eyebrow_markup = f'<div class="ag-page-hero-eyebrow">{escape(eyebrow)}</div>'

	st.markdown(
		(
			f'<section class="ag-page-hero">'
			f'<div class="ag-page-hero-orb ag-page-hero-orb-primary"></div>'
			f'<div class="ag-page-hero-orb ag-page-hero-orb-secondary"></div>'
			f'<div class="ag-page-hero-grid">'
			f'<div class="ag-page-hero-copy">'
			f"{eyebrow_markup}"
			f"{title_markup}"
			f'<p class="ag-page-hero-description">{escape(description)}</p>'
			f"{pills_markup}"
			f"</div>"
			f"{status_markup}"
			f"</div>"
			f"</section>"
		),
		unsafe_allow_html=True,
	)


def _render_market_context_chips(chips: list[str]) -> str:
	valid_chips = [chip.strip() for chip in chips if chip and chip.strip()]
	if not valid_chips:
		return ""
	chips_markup = "".join(f'<span class="market-view-chip">{escape(chip)}</span>' for chip in valid_chips)
	return f'<div class="market-view-chip-row">{chips_markup}</div>'


def _render_market_metric_cards(cards: list[tuple[str, str, str]], *, grid_class: str = "market-view-metrics") -> str:
	card_html = "".join(
		(
			'<div class="ai-dashboard-metric-card">'
			f'<div class="ai-dashboard-metric-label">{escape(label)}</div>'
			f'<div class="ai-dashboard-metric-value">{escape(value)}</div>'
			f'<div class="market-view-metric-copy">{escape(copy)}</div>'
			"</div>"
		)
		for label, value, copy in cards
	)
	return f'<div class="ai-dashboard-metrics {grid_class}">{card_html}</div>'


def _render_market_section_header(kicker: str, title: str, copy: str, *, chips: list[str] | None = None) -> str:
	copy_markup = f'<p class="market-view-section-copy">{escape(copy)}</p>' if copy else ""
	return (
		f'<div class="market-view-section-kicker">{escape(kicker)}</div>'
		f'<h2 class="market-view-section-title">{escape(title)}</h2>'
		f"{copy_markup}"
		f'{_render_market_context_chips(chips or [])}'
	)


def _build_income_summary_cards(income_stmt, selected_column, *, period_type: str = "Quarterly") -> list[tuple[str, str, str]]:
	metrics = extract_quarter_metrics(income_stmt, selected_column)
	revenue = metrics["revenue"]
	gross_profit = metrics["gross_profit"]
	gross_margin = metrics["gross_margin"]
	operating_margin = metrics["operating_margin"]
	net_margin = metrics["net_margin"]
	period_noun = "quarter" if period_type == "Quarterly" else "year"
	revenue_label = "Quarter Revenue" if period_type == "Quarterly" else "Year Revenue"
	return [
		(revenue_label, format_compact_currency(revenue) if revenue else "N/A", f"Reported sales for the selected {period_noun}."),
		("Gross Profit", format_compact_currency(gross_profit), "Revenue remaining after cost of revenue."),
		("Gross Margin", format_percent(gross_margin, allow_negative=True) if gross_margin is not None else "N/A", f"Gross profit divided by revenue for the {period_noun}."),
		("Operating Margin", format_percent(operating_margin, allow_negative=True) if operating_margin is not None else "N/A", f"Operating income divided by revenue for the {period_noun}."),
		("Net Margin", format_percent(net_margin, allow_negative=True) if net_margin is not None else "N/A", f"Net income divided by revenue for the {period_noun}."),
	]


def _format_dividend_yield(info_dict) -> str:
	current_price = safe_number(info_dict.get("currentPrice", info_dict.get("regularMarketPrice")))
	dividend_rate = safe_number(info_dict.get("dividendRate"))
	if dividend_rate > 0 and current_price > 0:
		return format_percent(dividend_rate / current_price)

	raw_dividend_yield = info_dict.get("dividendYield")
	if raw_dividend_yield is None:
		return "N/A"
	return format_percent(raw_dividend_yield)


def render_metrics_header(info_dict, *, ticker: str | None = None) -> None:
	company_name = info_dict.get("shortName") or info_dict.get("longName") or (ticker or "Selected company")
	symbol = (ticker or info_dict.get("symbol") or "").strip().upper()
	chips = [
		f"Ticker {symbol}" if symbol else "",
		info_dict.get("fullExchangeName") or info_dict.get("exchange"),
		info_dict.get("sector") or info_dict.get("industry"),
	]
	cards = [
		(
			"Current Price",
			format_price(info_dict.get("currentPrice", info_dict.get("regularMarketPrice", "N/A"))),
			"Live spot price pulled from the current market snapshot.",
		),
		("Market Cap", format_market_cap(info_dict.get("marketCap", "N/A")), "Equity value implied by the latest quote and share count."),
		("Trailing P/E", format_ratio(info_dict.get("trailingPE", "N/A")), "Price relative to trailing twelve-month earnings."),
		("Forward P/E", format_ratio(info_dict.get("forwardPE", "N/A")), "Price relative to analyst forward earnings estimates."),
		("EPS (TTM)", format_price(info_dict.get("trailingEps", "N/A")), "Trailing twelve-month earnings per share."),
		("Dividend Yield", _format_dividend_yield(info_dict), "Cash yield at the current market price."),
		("52 Week High", format_price(info_dict.get("fiftyTwoWeekHigh", "N/A")), "Highest price recorded over the past year."),
		("52 Week Low", format_price(info_dict.get("fiftyTwoWeekLow", "N/A")), "Lowest price recorded over the past year."),
	]

	with st.container():
		st.markdown('<div class="market-view-dashboard-anchor"></div>', unsafe_allow_html=True)
		st.markdown(
			(
				f"{_render_market_section_header('Market snapshot', company_name, 'Key quote, valuation, and return signals in the same card language used across the rest of the app.', chips=chips)}"
				f"{_render_market_metric_cards(cards)}"
			),
			unsafe_allow_html=True,
		)


def render_income_waterfall(quarterly_income_stmt, *, annual_income_stmt=None) -> None:
	if quarterly_income_stmt is None or quarterly_income_stmt.empty:
		st.warning("Quarterly income statement data is unavailable for this ticker.")
		return

	has_annual = len(get_display_period_columns(annual_income_stmt, period_type="Annual", limit=4)) > 0
	view_options = ["Quarterly", "Annually"] if has_annual else ["Quarterly"]

	with st.container():
		st.markdown('<div class="market-view-section-anchor"></div>', unsafe_allow_html=True)
		st.markdown(
			_render_market_section_header(
				"Income bridge",
				"Income Statement Waterfall",
				"",
			),
			unsafe_allow_html=True,
		)
		st.markdown('<div class="market-view-quarter-controls-gap"></div>', unsafe_allow_html=True)
		default_period_view = st.session_state.get("income_statement_period_type", view_options[0])
		if default_period_view not in view_options:
			default_period_view = view_options[0]

		period_col, select_col = st.columns([1.15, 0.85])
		with period_col:
			selected_period_type = st.segmented_control(
				"Period View",
				options=view_options,
				default=default_period_view,
				key="income_statement_period_type",
				width="stretch",
			)

		active_period_type = "Annual" if selected_period_type == "Annually" else "Quarterly"
		active_income_stmt = annual_income_stmt if active_period_type == "Annual" else quarterly_income_stmt
		active_columns = get_display_period_columns(
			active_income_stmt,
			period_type=active_period_type,
			limit=4,
		)
		if not active_columns:
			st.warning(f"{selected_period_type} income statement data is unavailable for this ticker.")
			return

		period_labels = [format_period_label(column, period_type=active_period_type) for column in active_columns]
		control_label = "Year" if active_period_type == "Annual" else "Quarter"
		select_key = "annual_period" if active_period_type == "Annual" else "quarterly_period"
		with select_col:
			selected_label = st.selectbox(control_label, period_labels, key=select_key)

		selected_column = active_columns[period_labels.index(selected_label)]
		st.markdown(
			_render_market_metric_cards(
				_build_income_summary_cards(active_income_stmt, selected_column, period_type=active_period_type),
				grid_class="market-view-summary-metrics",
			),
			unsafe_allow_html=True,
		)
		try:
			figure, _ = build_income_waterfall_figure(
				active_income_stmt,
				selected_column=selected_column,
				period_type=active_period_type,
			)
		except ValueError as exc:
			st.warning(str(exc))
			return
		st.plotly_chart(figure, use_container_width=True)
