from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf


def _get_first_value(statement: pd.DataFrame, aliases: list[str]) -> Optional[float]:
	for alias in aliases:
		if alias in statement.index:
			value = statement.loc[alias].iloc[0]
			if pd.notna(value):
				return float(value)
	return None


def _format_period_label(period: object, period_type: str) -> str:
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
	stock = yf.Ticker(ticker)
	if period_type == "Quarterly":
		statement = stock.quarterly_financials
	else:
		statement = stock.financials

	if statement is None or statement.empty:
		raise ValueError("Income statement is unavailable for this ticker.")

	statement = statement.dropna(how="all")
	if statement.empty:
		raise ValueError("Income statement is unavailable for this ticker.")

	statement = statement.apply(pd.to_numeric, errors="coerce")
	formatted_columns = [_format_period_label(col, period_type) for col in statement.columns]
	statement.columns = formatted_columns

	return statement


def get_earnings_bridge(statement: pd.DataFrame, selected_period: str) -> dict:
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
	operating_expenses = max(gross_profit - operating_income, 0.0)
	net_income = _value_for_period(
		statement,
		selected_period,
		["Net Income", "Net Income Common Stockholders"],
		default=operating_income,
	)
	non_operating = operating_income - net_income

	return {
		"revenue": revenue,
		"revenue_items": revenue_items,
		"cost_of_revenue": cost_of_revenue,
		"gross_profit": gross_profit,
		"operating_expenses": operating_expenses,
		"operating_income": operating_income,
		"non_operating": non_operating,
		"net_income": net_income,
	}


def build_earnings_breakdown_sankey(bridge: dict, company_label: str, period_label: str):
	net_label = "Net Income" if bridge["net_income"] >= 0 else "Net Loss"
	non_op_label = "Interest/Tax/Other"
	if bridge["non_operating"] < 0:
		non_op_label = "Other Income/Tax Benefit"

	node_labels = [name for name, _ in bridge["revenue_items"]]
	node_labels.extend(
		[
			"Total Revenue",
			"Cost of Goods Sold",
			"Gross Profit",
			"Operating Expenses",
			"Operating Income",
			non_op_label,
			net_label,
		]
	)

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

	sources.extend(
		[
			index["Total Revenue"],
			index["Total Revenue"],
			index["Gross Profit"],
			index["Gross Profit"],
			index["Operating Income"],
			index["Operating Income"],
		]
	)
	targets.extend(
		[
			index["Cost of Goods Sold"],
			index["Gross Profit"],
			index["Operating Expenses"],
			index["Operating Income"],
			index[non_op_label],
			index[net_label],
		]
	)
	values.extend(
		[
			abs(bridge["cost_of_revenue"]),
			abs(bridge["gross_profit"]),
			abs(bridge["operating_expenses"]),
			abs(bridge["operating_income"]),
			abs(bridge["non_operating"]),
			abs(bridge["net_income"]),
		]
	)
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

	fig = go.Figure(
		data=[
			go.Sankey(
				node={"label": node_labels, "pad": 18, "thickness": 16, "color": node_colors},
				link={"source": sources, "target": targets, "value": values, "color": colors},
			)
		]
	)
	fig.update_layout(
		title=f"{company_label} Earnings Breakdown ({period_label})",
		margin={"t": 60, "l": 0, "r": 0, "b": 0},
	)
	return fig
