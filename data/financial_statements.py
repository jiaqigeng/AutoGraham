from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go

from valuation.common import safe_number


def format_period_label(period_column, period_type: str = "Quarterly") -> str:
	if hasattr(period_column, "strftime"):
		label_prefix = "Year Ended" if period_type == "Annual" else "Quarter Ended"
		return f"{label_prefix}: {period_column.strftime('%b %d, %Y')}"
	return str(period_column)


def get_display_period_columns(
	income_stmt: pd.DataFrame,
	*,
	period_type: str = "Quarterly",
	limit: int | None = None,
) -> list:
	if income_stmt is None or len(getattr(income_stmt, "columns", [])) == 0:
		return []

	ordered_columns = list(sorted(income_stmt.columns, reverse=True))
	if period_type == "Annual":
		december_year_end_columns = [
			column for column in ordered_columns if not hasattr(column, "month") or (column.month == 12 and column.day == 31)
		]
		if december_year_end_columns:
			ordered_columns = december_year_end_columns

	if limit is not None:
		return ordered_columns[:limit]
	return ordered_columns


def build_calendar_year_income_statement(quarterly_income_stmt: pd.DataFrame, *, limit: int | None = None) -> pd.DataFrame:
	if quarterly_income_stmt is None or len(getattr(quarterly_income_stmt, "columns", [])) == 0:
		empty_frame = pd.DataFrame()
		empty_frame.attrs.update(getattr(quarterly_income_stmt, "attrs", {}))
		return empty_frame

	ordered = quarterly_income_stmt.copy()
	ordered = ordered[sorted(ordered.columns, reverse=True)]
	period_columns = list(ordered.columns)
	yearly_series: dict[pd.Timestamp, pd.Series] = {}

	for current_index, period_column in enumerate(period_columns):
		if not hasattr(period_column, "month") or period_column.month != 12 or current_index + 3 >= len(period_columns):
			continue

		trailing_columns = period_columns[current_index : current_index + 4]
		year_end_label = pd.Timestamp(year=period_column.year, month=12, day=31)
		if year_end_label in yearly_series:
			continue

		yearly_series[year_end_label] = ordered.loc[:, trailing_columns].fillna(0).sum(axis=1)

	if not yearly_series:
		empty_frame = pd.DataFrame()
		empty_frame.attrs.update(getattr(quarterly_income_stmt, "attrs", {}))
		return empty_frame

	yearly_frame = pd.DataFrame(yearly_series)
	yearly_frame = yearly_frame[sorted(yearly_frame.columns, reverse=True)]
	if limit is not None:
		yearly_frame = yearly_frame.iloc[:, :limit]
	yearly_frame.attrs.update(getattr(quarterly_income_stmt, "attrs", {}))
	return yearly_frame


def _series_value(period_series: pd.Series, aliases: list[str], default: float | None = None) -> float | None:
	for alias in aliases:
		if alias in period_series.index:
			value = period_series.get(alias)
			if pd.notna(value):
				return safe_number(value)
	return default


def extract_quarter_metrics(income_stmt: pd.DataFrame, period_column) -> dict[str, object]:
	if income_stmt is None or income_stmt.empty:
		raise ValueError("Quarterly income statement data is unavailable.")
	if period_column not in income_stmt.columns:
		raise ValueError("Selected quarter is unavailable.")

	period_series = income_stmt[period_column].fillna(0)
	revenue = safe_number(_series_value(period_series, ["Total Revenue", "Revenue"], default=0.0))
	cost_of_revenue = abs(safe_number(_series_value(period_series, ["Cost Of Revenue", "Cost of Revenue"], default=0.0)))
	gross_profit_raw = _series_value(period_series, ["Gross Profit"])
	gross_profit = safe_number(gross_profit_raw if gross_profit_raw is not None else revenue - cost_of_revenue)

	operating_income_raw = _series_value(period_series, ["Operating Income", "EBIT"])
	operating_expenses_raw = _series_value(period_series, ["Operating Expense", "Operating Expenses"])
	if operating_income_raw is None and operating_expenses_raw is None:
		operating_income = 0.0
		operating_expenses = 0.0
	else:
		if operating_income_raw is None:
			operating_expenses = abs(safe_number(operating_expenses_raw))
			operating_income = gross_profit - operating_expenses
		elif operating_expenses_raw is None:
			operating_income = safe_number(operating_income_raw)
			operating_expenses = abs(gross_profit - operating_income)
		else:
			operating_income = safe_number(operating_income_raw)
			operating_expenses = abs(safe_number(operating_expenses_raw))

	net_profit_raw = _series_value(period_series, ["Net Income", "Net Income Common Stockholders"])
	net_profit = safe_number(net_profit_raw if net_profit_raw is not None else operating_income)

	return {
		"period": format_period_label(period_column),
		"revenue": revenue,
		"gross_profit": gross_profit,
		"operating_income": operating_income,
		"operating_expenses": operating_expenses,
		"net_profit": net_profit,
		"gross_margin": (gross_profit / revenue) if revenue else None,
		"operating_margin": (operating_income / revenue) if revenue else None,
		"net_margin": (net_profit / revenue) if revenue else None,
	}


def extract_latest_quarter_metrics(income_stmt: pd.DataFrame) -> dict[str, object]:
	if income_stmt is None or income_stmt.empty:
		raise ValueError("Quarterly income statement data is unavailable.")

	ordered = income_stmt[income_stmt.columns.sort_values(ascending=False)]
	latest_period = ordered.columns[0]
	return extract_quarter_metrics(ordered, latest_period)


def get_period_change_metrics(income_stmt: pd.DataFrame, period_column, metric_name: str) -> dict[str, Optional[float]]:
	if income_stmt is None or income_stmt.empty:
		raise ValueError("Quarterly income statement data is unavailable.")

	ordered = income_stmt.copy()
	ordered = ordered[sorted(ordered.columns, reverse=True)]
	period_columns = list(ordered.columns)
	if period_column not in period_columns:
		raise ValueError("Selected period is unavailable.")

	metrics_by_column = {column: _extract_period_metrics(ordered, column) for column in period_columns}
	current_index = period_columns.index(period_column)
	return _build_change_map(metrics_by_column, period_columns, current_index, metric_name)


def _metric_is_expense(metric_name: str) -> bool:
	return metric_name in {"cost_of_revenue", "operating_expenses", "taxes"}


def _extract_period_metrics(income_stmt: pd.DataFrame, period_column) -> dict[str, float]:
	period_series = income_stmt[period_column].fillna(0)

	revenue = safe_number(_series_value(period_series, ["Total Revenue", "Revenue"], default=0.0))
	cost_of_revenue = -abs(safe_number(_series_value(period_series, ["Cost Of Revenue", "Cost of Revenue"], default=0.0)))
	operating_expenses_raw = _series_value(period_series, ["Operating Expense", "Operating Expenses"])
	taxes = -abs(safe_number(period_series.get("Tax Provision", 0)))
	net_profit = safe_number(period_series.get("Net Income", period_series.get("Net Income Common Stockholders", 0)))
	gross_profit_raw = _series_value(period_series, ["Gross Profit"])
	gross_profit = safe_number(gross_profit_raw if gross_profit_raw is not None else revenue + cost_of_revenue)
	operating_income_raw = _series_value(period_series, ["Operating Income", "EBIT"])
	if operating_income_raw is None and operating_expenses_raw is None:
		operating_expenses = 0.0
		operating_profit = gross_profit
	elif operating_income_raw is None:
		operating_expenses = -abs(safe_number(operating_expenses_raw))
		operating_profit = gross_profit + operating_expenses
	elif operating_expenses_raw is None:
		operating_profit = safe_number(operating_income_raw)
		operating_expenses = operating_profit - gross_profit
	else:
		operating_expenses = -abs(safe_number(operating_expenses_raw))
		operating_profit = safe_number(operating_income_raw)
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
			return f"<span style='color:#EF4444'>+{pct_change:.1f}%</span>"
		if pct_change < 0:
			return f"<span style='color:#10B981'>{pct_change:.1f}%</span>"
		return ""
	if pct_change > 0:
		return f"<span style='color:#10B981'>+{pct_change:.1f}%</span>"
	if pct_change < 0:
		return f"<span style='color:#EF4444'>{pct_change:.1f}%</span>"
	return ""


def _format_chart_value(
	metric_name: str,
	value: float,
	value_suffix: str,
	changes: dict[str, Optional[float]],
	*,
	period_type: str = "Quarterly",
) -> str:
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
	if period_type == "Quarterly":
		qoq_badge = _format_change_badge(metric_name, changes["qoq"])
		if qoq_badge:
			change_lines.append(f"QoQ: {qoq_badge}")

	if not change_lines:
		return amount_text
	return amount_text + "<br>" + "<br>".join(change_lines)


def build_income_waterfall_figure(
	income_stmt: pd.DataFrame,
	selected_column=None,
	*,
	period_type: str = "Quarterly",
) -> tuple[go.Figure, list[str]]:
	if income_stmt is None or income_stmt.empty:
		raise ValueError("Quarterly income statement data is unavailable for this ticker.")

	ordered = income_stmt.copy()
	ordered = ordered[sorted(ordered.columns, reverse=True)]
	period_columns = list(ordered.columns)
	if not period_columns:
		raise ValueError("No quarterly periods are available for this ticker.")

	if selected_column is None:
		selected_column = period_columns[0]

	metrics_by_column = {column: _extract_period_metrics(ordered, column) for column in period_columns}
	selected_index = period_columns.index(selected_column)
	metrics = metrics_by_column[selected_column]
	changes = {
		metric_name: _build_change_map(metrics_by_column, period_columns, selected_index, metric_name)
		for metric_name in metrics
	}

	revenue_raw = safe_number(metrics["revenue"])
	if revenue_raw <= 0:
		raise ValueError(f"{format_period_label(selected_column, period_type=period_type)} revenue is not positive, so a waterfall cannot be built.")

	raw_metrics = [safe_number(metrics[name]) for name in metrics]
	max_abs_value = max(abs(value) for value in raw_metrics)
	value_divisor = 1_000_000_000 if max_abs_value >= 1_000_000_000 else 1_000_000
	value_suffix = "B" if value_divisor == 1_000_000_000 else "M"
	scaled_metrics = {key: value / value_divisor for key, value in metrics.items()}

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
		float(scaled_metrics["revenue"]),
		float(scaled_metrics["cost_of_revenue"]),
		0.0,
		float(scaled_metrics["operating_expenses"]),
		0.0,
		float(scaled_metrics["other_income_expense_net"]),
		float(scaled_metrics["taxes"]),
		0.0,
	]
	custom_text = [
		_format_chart_value("revenue", scaled_metrics["revenue"], value_suffix, changes["revenue"], period_type=period_type),
		_format_chart_value("cost_of_revenue", scaled_metrics["cost_of_revenue"], value_suffix, changes["cost_of_revenue"], period_type=period_type),
		_format_chart_value("gross_profit", scaled_metrics["gross_profit"], value_suffix, changes["gross_profit"], period_type=period_type),
		_format_chart_value("operating_expenses", scaled_metrics["operating_expenses"], value_suffix, changes["operating_expenses"], period_type=period_type),
		_format_chart_value("operating_profit", scaled_metrics["operating_profit"], value_suffix, changes["operating_profit"], period_type=period_type),
		_format_chart_value("other_income_expense_net", scaled_metrics["other_income_expense_net"], value_suffix, changes["other_income_expense_net"], period_type=period_type),
		_format_chart_value("taxes", scaled_metrics["taxes"], value_suffix, changes["taxes"], period_type=period_type),
		_format_chart_value("net_profit", scaled_metrics["net_profit"], value_suffix, changes["net_profit"], period_type=period_type),
	]
	min_y_value = min(y_values)
	max_y_value = max(y_values)
	lower_bound = min_y_value * 1.3 if min_y_value < 0 else min_y_value * 0.7
	upper_bound = max_y_value * 1.3 if max_y_value > 0 else max_y_value * 0.7
	if lower_bound == upper_bound:
		lower_bound, upper_bound = -1.0, 1.0

	ticker = ordered.attrs.get("ticker", "Ticker")
	period_descriptor = "Annual" if period_type == "Annual" else "Quarterly"
	figure = go.Figure(
		go.Waterfall(
			name=ticker,
			orientation="v",
			measure=["absolute", "relative", "total", "relative", "total", "relative", "relative", "total"],
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
	figure.update_layout(
		title={"text": f"<b>{ticker}</b> {period_descriptor} Revenue to Net Profit Bridge", "x": 0.02, "xanchor": "left", "y": 0.94},
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
		xaxis={"tickfont": {"size": 14, "color": "#334155"}, "automargin": True, "showgrid": False, "showline": False, "zeroline": False, "fixedrange": True},
		yaxis={"tickfont": {"size": 13, "color": "#475569"}, "automargin": True, "gridcolor": "rgba(148,163,184,0.18)", "gridwidth": 1, "zeroline": True, "zerolinecolor": "rgba(15,23,42,0.22)", "zerolinewidth": 1, "fixedrange": True},
		hoverlabel={"bgcolor": "white", "bordercolor": "rgba(148,163,184,0.35)", "font": {"color": "#0f172a", "family": "Avenir Next, Helvetica Neue, sans-serif"}},
		uniformtext={"minsize": 12, "mode": "show"},
	)
	figure.update_yaxes(range=[lower_bound, upper_bound])
	figure.update_traces(cliponaxis=False)
	return figure, [format_period_label(column, period_type=period_type) for column in period_columns]


def _format_legacy_period_label(period: object, period_type: str) -> str:
	if not hasattr(period, "year"):
		return str(period)
	if period_type == "Quarterly" and hasattr(period, "month"):
		quarter = ((period.month - 1) // 3) + 1
		return f"Q{quarter} {period.year}"
	return f"FY {period.year}"


def _value_for_period(statement: pd.DataFrame, selected_period: str, aliases: list[str], default: float = 0.0) -> float:
	for alias in aliases:
		if alias in statement.index:
			value = statement.at[alias, selected_period]
			if pd.notna(value):
				return float(value)
	return float(default)


def get_income_statement_data(ticker: str, period_type: str = "Annual") -> pd.DataFrame:
	import yfinance as yf

	stock = yf.Ticker(ticker)
	statement = stock.quarterly_financials if period_type == "Quarterly" else stock.financials
	if statement is None or statement.empty:
		raise ValueError("Income statement is unavailable for this ticker.")
	statement = statement.dropna(how="all")
	if statement.empty:
		raise ValueError("Income statement is unavailable for this ticker.")
	statement = statement.apply(pd.to_numeric, errors="coerce")
	statement.columns = [_format_legacy_period_label(col, period_type) for col in statement.columns]
	return statement


def get_earnings_bridge(statement: pd.DataFrame, selected_period: str) -> dict[str, object]:
	if selected_period not in statement.columns:
		raise ValueError("Selected period is unavailable.")

	series = statement[selected_period].dropna()
	revenue = _value_for_period(statement, selected_period, ["Total Revenue", "Revenue"])
	if revenue <= 0:
		raise ValueError("Revenue data is unavailable for selected period.")

	revenue_items = []
	for line_item, value in series.items():
		if line_item in {"Total Revenue", "Revenue"}:
			continue
		name = str(line_item).lower()
		if ("revenue" in name or "sales" in name) and float(value) > 0:
			revenue_items.append((str(line_item), float(value)))

	revenue_items.sort(key=lambda row: abs(row[1]), reverse=True)
	revenue_items = revenue_items[:6]
	reported_components_total = sum(value for _, value in revenue_items)
	if not revenue_items:
		revenue_items = [("Reported Revenue", revenue)]
		reported_components_total = revenue
	if reported_components_total < revenue:
		revenue_items.append(("Other Revenue", revenue - reported_components_total))

	cost_of_revenue = abs(_value_for_period(statement, selected_period, ["Cost Of Revenue", "Cost of Revenue"]))
	gross_profit = _value_for_period(statement, selected_period, ["Gross Profit"], default=revenue - cost_of_revenue)
	operating_income = _value_for_period(statement, selected_period, ["Operating Income", "EBIT"], default=0.0)
	if operating_income == 0.0 and "EBITDA" in statement.index:
		operating_income = float(statement.at["EBITDA", selected_period])
	net_income = _value_for_period(statement, selected_period, ["Net Income", "Net Income Common Stockholders"], default=operating_income)

	return {
		"revenue": revenue,
		"revenue_items": revenue_items,
		"cost_of_revenue": cost_of_revenue,
		"gross_profit": gross_profit,
		"operating_expenses": max(gross_profit - operating_income, 0.0),
		"operating_income": operating_income,
		"non_operating": operating_income - net_income,
		"net_income": net_income,
	}


def build_earnings_breakdown_sankey(bridge: dict[str, object], company_label: str, period_label: str):
	net_label = "Net Income" if bridge["net_income"] >= 0 else "Net Loss"
	non_op_label = "Interest/Tax/Other" if bridge["non_operating"] >= 0 else "Other Income/Tax Benefit"
	node_labels = [name for name, _ in bridge["revenue_items"]]
	node_labels.extend(["Total Revenue", "Cost of Goods Sold", "Gross Profit", "Operating Expenses", "Operating Income", non_op_label, net_label])
	index = {label: i for i, label in enumerate(node_labels)}

	sources = []
	targets = []
	values = []
	colors = []
	for label, value in bridge["revenue_items"]:
		sources.append(index[label])
		targets.append(index["Total Revenue"])
		values.append(abs(value))
		colors.append("rgba(31,119,180,0.35)")

	sources.extend([index["Total Revenue"], index["Total Revenue"], index["Gross Profit"], index["Gross Profit"], index["Operating Income"], index["Operating Income"]])
	targets.extend([index["Cost of Goods Sold"], index["Gross Profit"], index["Operating Expenses"], index["Operating Income"], index[non_op_label], index[net_label]])
	values.extend([abs(bridge["cost_of_revenue"]), abs(bridge["gross_profit"]), abs(bridge["operating_expenses"]), abs(bridge["operating_income"]), abs(bridge["non_operating"]), abs(bridge["net_income"])])
	colors.extend(
		[
			"rgba(214,39,40,0.35)",
			"rgba(44,160,44,0.35)",
			"rgba(214,39,40,0.35)",
			"rgba(44,160,44,0.35)",
			"rgba(255,127,14,0.35)",
			"rgba(44,160,44,0.35)" if bridge["net_income"] >= 0 else "rgba(214,39,40,0.35)",
		]
	)

	node_colors = []
	for label in node_labels:
		if label in {"Total Revenue", "Gross Profit", "Operating Income", net_label}:
			node_colors.append("#2ca02c" if label != "Total Revenue" else "#1f77b4")
		elif label in {"Cost of Goods Sold", "Operating Expenses"}:
			node_colors.append("#d62728")
		elif label == non_op_label:
			node_colors.append("#ff7f0e")
		else:
			node_colors.append("#1f77b4")

	figure = go.Figure(
		data=[
			go.Sankey(
				node={"label": node_labels, "pad": 18, "thickness": 16, "color": node_colors},
				link={"source": sources, "target": targets, "value": values, "color": colors},
			)
		]
	)
	figure.update_layout(title=f"{company_label} Earnings Breakdown ({period_label})", margin={"t": 60, "l": 0, "r": 0, "b": 0})
	return figure
