from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		numeric_value = float(value)
	except (TypeError, ValueError):
		return 0.0
	if numeric_value != numeric_value:
		return 0.0
	return numeric_value


def _metric_is_expense(metric_name: str) -> bool:
	return metric_name in {"cost_of_revenue", "operating_expenses", "taxes"}


def _format_period_label(period_column) -> str:
	if hasattr(period_column, "strftime"):
		return f"Quarter Ended: {period_column.strftime('%b %d, %Y')}"
	return str(period_column)


def _extract_period_metrics(income_stmt: pd.DataFrame, period_column) -> dict[str, float]:
	period_series = income_stmt[period_column].fillna(0)

	revenue = _safe_number(period_series.get("Total Revenue", 0))
	cost_of_revenue = -abs(_safe_number(period_series.get("Cost Of Revenue", 0)))
	operating_expenses = -abs(_safe_number(period_series.get("Operating Expense", 0)))
	taxes = -abs(_safe_number(period_series.get("Tax Provision", 0)))
	net_profit = _safe_number(period_series.get("Net Income", period_series.get("Net Income Common Stockholders", 0)))
	gross_profit = revenue + cost_of_revenue
	operating_profit = gross_profit + operating_expenses
	other_income_expense_net = net_profit - operating_profit - taxes

	return {
		"revenue": revenue,
		"cost_of_revenue": cost_of_revenue,
		"gross_profit": gross_profit,
		"operating_expenses": operating_expenses,
		"operating_profit": operating_profit,
		"other_income_expense_net": other_income_expense_net,
		"taxes": taxes,
		"net_profit": net_profit,
	}


def _find_prior_year_column(statement_columns: list, current_column):
	if not hasattr(current_column, "to_pydatetime"):
		return None

	target_year = current_column.year - 1
	matching_candidates = []

	for candidate_column in statement_columns:
		if candidate_column == current_column or not hasattr(candidate_column, "to_pydatetime"):
			continue
		if candidate_column.year != target_year:
			continue

		day_delta = abs((current_column - candidate_column).days)
		matching_candidates.append((candidate_column, day_delta))

		if candidate_column.month == current_column.month and candidate_column.day == current_column.day:
			return candidate_column

	if matching_candidates:
		closest_candidate, closest_delta = min(matching_candidates, key=lambda item: item[1])
		if abs(closest_delta - 365) <= 10:
			return closest_candidate

	return None


def _build_change_map(metrics_by_column: dict, period_columns: list, current_index: int, metric_name: str) -> dict[str, Optional[float]]:
	current_column = period_columns[current_index]
	prior_year_column = _find_prior_year_column(period_columns, current_column)
	prior_quarter_column = period_columns[current_index + 1] if current_index + 1 < len(period_columns) else None
	current_metrics = metrics_by_column[current_column]
	prior_year_metrics = metrics_by_column.get(prior_year_column)
	prior_quarter_metrics = metrics_by_column.get(prior_quarter_column)
	metric_value = current_metrics[metric_name]

	yoy = None
	if prior_year_metrics is not None and prior_year_metrics[metric_name] != 0:
		if _metric_is_expense(metric_name):
			yoy = ((abs(metric_value) - abs(prior_year_metrics[metric_name])) / abs(prior_year_metrics[metric_name])) * 100
		else:
			yoy = ((metric_value - prior_year_metrics[metric_name]) / abs(prior_year_metrics[metric_name])) * 100

	qoq = None
	if prior_quarter_metrics is not None and prior_quarter_metrics[metric_name] != 0:
		if _metric_is_expense(metric_name):
			qoq = ((abs(metric_value) - abs(prior_quarter_metrics[metric_name])) / abs(prior_quarter_metrics[metric_name])) * 100
		else:
			qoq = ((metric_value - prior_quarter_metrics[metric_name]) / abs(prior_quarter_metrics[metric_name])) * 100

	return {"yoy": yoy, "qoq": qoq}


def _format_change_badge(metric_name: str, pct_change: Optional[float]) -> str:
	if pct_change is None:
		return ""
	if _metric_is_expense(metric_name):
		if pct_change > 0:
			return f"<span style='color:#EF4444'>▼ +{pct_change:.1f}%</span>"
		if pct_change < 0:
			return f"<span style='color:#10B981'>▲ {pct_change:.1f}%</span>"
		return ""
	if pct_change > 0:
		return f"<span style='color:#10B981'>▲ +{pct_change:.1f}%</span>"
	if pct_change < 0:
		return f"<span style='color:#EF4444'>▼ {pct_change:.1f}%</span>"
	return ""


def _format_chart_value(metric_name: str, value: float, value_suffix: str, changes: dict[str, Optional[float]]) -> str:
	rounded_value = round(value, 2)
	if rounded_value == 0:
		return ""
	if _metric_is_expense(metric_name):
		amount_text = f"$-{abs(rounded_value):,.2f}{value_suffix}"
	else:
		amount_text = f"${rounded_value:,.2f}{value_suffix}"

	change_lines = []
	yoy_badge = _format_change_badge(metric_name, changes["yoy"])
	if yoy_badge:
		change_lines.append(f"YoY: {yoy_badge}")
	qoq_badge = _format_change_badge(metric_name, changes["qoq"])
	if qoq_badge:
		change_lines.append(f"QoQ: {qoq_badge}")

	if not change_lines:
		return amount_text
	return amount_text + "<br>" + "<br>".join(change_lines)


def render_waterfall_chart(income_stmt) -> None:
	if income_stmt is None or income_stmt.empty:
		st.warning("Quarterly income statement data is unavailable for this ticker.")
		return

	income_stmt = income_stmt.copy()
	income_stmt = income_stmt[sorted(income_stmt.columns, reverse=True)]
	period_columns = list(income_stmt.columns)
	if not period_columns:
		st.warning("No quarterly periods are available for this ticker.")
		return

	period_labels = [_format_period_label(column) for column in period_columns]
	selected_label = st.selectbox("Quarter", period_labels, key="quarterly_period")
	selected_index = period_labels.index(selected_label)
	selected_column = period_columns[selected_index]

	metrics_by_column = {
		column: _extract_period_metrics(income_stmt, column)
		for column in period_columns
	}
	metrics = metrics_by_column[selected_column]
	changes = {
		metric_name: _build_change_map(metrics_by_column, period_columns, selected_index, metric_name)
		for metric_name in metrics
	}

	revenue_raw = _safe_number(metrics["revenue"])
	if revenue_raw <= 0:
		st.warning(f"{selected_label} revenue is not positive, so a waterfall cannot be built.")
		return

	raw_metrics = [
		_safe_number(metrics["revenue"]),
		_safe_number(metrics["cost_of_revenue"]),
		_safe_number(metrics["gross_profit"]),
		_safe_number(metrics["operating_expenses"]),
		_safe_number(metrics["operating_profit"]),
		_safe_number(metrics["other_income_expense_net"]),
		_safe_number(metrics["taxes"]),
		_safe_number(metrics["net_profit"]),
	]
	max_abs_value = max(abs(value) for value in raw_metrics)
	value_divisor = 1_000_000_000 if max_abs_value >= 1_000_000_000 else 1_000_000
	value_suffix = "B" if value_divisor == 1_000_000_000 else "M"

	revenue = metrics["revenue"] / value_divisor
	cost_of_revenue = metrics["cost_of_revenue"] / value_divisor
	gross_profit = metrics["gross_profit"] / value_divisor
	operating_expenses = metrics["operating_expenses"] / value_divisor
	operating_profit = metrics["operating_profit"] / value_divisor
	other_income_expense_net = metrics["other_income_expense_net"] / value_divisor
	taxes = metrics["taxes"] / value_divisor
	net_profit = metrics["net_profit"] / value_divisor

	x_labels = [
		"Revenue",
		"Cost of Revenue",
		"Gross Profit",
		"Operating Expenses",
		"Operating Profit",
		"Other Income/Expense Net (Plug)",
		"Taxes",
		"Net Profit",
	]
	y_values = [
		float(revenue),
		float(cost_of_revenue),
		0.0,
		float(operating_expenses),
		0.0,
		float(other_income_expense_net),
		float(taxes),
		0.0,
	]
	measures = ["absolute", "relative", "total", "relative", "total", "relative", "relative", "total"]
	custom_text = [
		_format_chart_value("revenue", revenue, value_suffix, changes["revenue"]),
		_format_chart_value("cost_of_revenue", cost_of_revenue, value_suffix, changes["cost_of_revenue"]),
		_format_chart_value("gross_profit", gross_profit, value_suffix, changes["gross_profit"]),
		_format_chart_value("operating_expenses", operating_expenses, value_suffix, changes["operating_expenses"]),
		_format_chart_value("operating_profit", operating_profit, value_suffix, changes["operating_profit"]),
		_format_chart_value("other_income_expense_net", other_income_expense_net, value_suffix, changes["other_income_expense_net"]),
		_format_chart_value("taxes", taxes, value_suffix, changes["taxes"]),
		_format_chart_value("net_profit", net_profit, value_suffix, changes["net_profit"]),
	]

	min_y_value = min(y_values)
	max_y_value = max(y_values)
	lower_bound = min_y_value * 1.3 if min_y_value < 0 else min_y_value * 0.7
	upper_bound = max_y_value * 1.3 if max_y_value > 0 else max_y_value * 0.7
	if lower_bound == upper_bound:
		lower_bound = -1.0
		upper_bound = 1.0

	ticker = income_stmt.attrs.get("ticker", "Ticker")
	fig = go.Figure(
		go.Waterfall(
			name=ticker,
			orientation="v",
			measure=measures,
			x=x_labels,
			y=y_values,
			text=custom_text,
			textposition="outside",
			textfont={"size": 13, "color": "#334155", "family": "Avenir Next, Helvetica Neue, sans-serif"},
			insidetextfont={"size": 13, "color": "#ffffff", "family": "Avenir Next, Helvetica Neue, sans-serif"},
			outsidetextfont={"size": 13, "color": "#334155", "family": "Avenir Next, Helvetica Neue, sans-serif"},
			hovertemplate="%{x}<br>%{text}<extra></extra>",
			cliponaxis=False,
			connector={"mode": "spanning", "line": {"dash": "dot", "color": "rgb(99, 102, 241)", "width": 1.6}},
			increasing={"marker": {"color": "#0EA5A3", "line": {"color": "rgba(255,255,255,0.88)", "width": 0}}},
			decreasing={"marker": {"color": "#F05D5E", "line": {"color": "rgba(255,255,255,0.88)", "width": 0}}},
			totals={"marker": {"color": "rgba(37, 99, 235, 0.88)", "line": {"color": "rgba(255,255,255,0.92)", "width": 0}}},
		)
	)

	fig.update_layout(
		title={
			"text": f"<b>{ticker}</b> Quarterly Revenue to Net Profit Bridge",
			"x": 0.02,
			"xanchor": "left",
			"y": 0.94,
		},
		title_font={"size": 24, "color": "#0f172a", "family": "Avenir Next, Helvetica Neue, sans-serif"},
		yaxis_title=f"USD ({'Billions' if value_suffix == 'B' else 'Millions'})",
		showlegend=False,
		template="plotly_white",
		height=700,
		margin={"t": 140, "b": 90, "l": 40, "r": 40},
		font={"size": 15, "color": "#0f172a", "family": "Avenir Next, Helvetica Neue, sans-serif"},
		waterfallgap=0.28,
		paper_bgcolor="rgba(248,250,252,0.96)",
		plot_bgcolor="rgba(255,255,255,0)",
		xaxis={
			"tickfont": {"size": 14, "color": "#334155"},
			"automargin": True,
			"showgrid": False,
			"showline": False,
			"zeroline": False,
			"fixedrange": True,
		},
		yaxis={
			"tickfont": {"size": 13, "color": "#475569"},
			"automargin": True,
			"gridcolor": "rgba(148,163,184,0.18)",
			"gridwidth": 1,
			"zeroline": True,
			"zerolinecolor": "rgba(15,23,42,0.22)",
			"zerolinewidth": 1,
			"fixedrange": True,
		},
		hoverlabel={"bgcolor": "white", "bordercolor": "rgba(148,163,184,0.35)", "font": {"color": "#0f172a", "family": "Avenir Next, Helvetica Neue, sans-serif"}},
		uniformtext={"minsize": 12, "mode": "show"},
	)
	fig.update_yaxes(range=[lower_bound, upper_bound])
	fig.update_traces(cliponaxis=False)

	st.plotly_chart(fig, use_container_width=True)