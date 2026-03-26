from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent.schemas import CandidateFact
from agent.storage import get_sqlite_financial_facts
from agent.subagents.research.common import (
	base_candidate_facts,
	build_analysis_artifact,
	clean_period_label,
	dedupe_links,
	fmt_money,
	fmt_percent,
	fmt_price,
)
from agent.tools.finance_tools import build_company_snapshot, build_source_links
from valuation.common import safe_number


def _metric_rows(
	facts_by_metric: Mapping[str, list[dict[str, Any]]],
	metric_name: str,
	*,
	exclude_latest_period: bool = True,
) -> list[dict[str, Any]]:
	rows = list(facts_by_metric.get(metric_name, []))
	if exclude_latest_period:
		rows = [row for row in rows if row.get("period") not in ("", "latest")]
	return rows


def _historical_margin_rows(facts_by_metric: Mapping[str, list[dict[str, Any]]], *, max_items: int = 5) -> list[dict[str, Any]]:
	revenue_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "revenue")}
	operating_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "operating_income")}
	net_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "net_income")}
	gross_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "gross_profit")}
	margin_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "gross_margin")}
	periods = sorted((period for period in revenue_rows.keys() if period), reverse=True)
	items: list[dict[str, Any]] = []
	for period in periods:
		revenue_value = revenue_rows[period].get("value")
		revenue = safe_number(revenue_value) if revenue_value is not None else None
		if revenue in (None, 0):
			continue
		gross_margin_row = margin_rows.get(period, {})
		gross_margin_value = gross_margin_row.get("value") if isinstance(gross_margin_row, Mapping) else None
		gross_margin = safe_number(gross_margin_value) if gross_margin_value is not None else None
		if gross_margin is None:
			gross_profit_row = gross_rows.get(period, {})
			gross_profit_value = gross_profit_row.get("value") if isinstance(gross_profit_row, Mapping) else None
			gross_profit = safe_number(gross_profit_value) if gross_profit_value is not None else None
			gross_margin = (gross_profit / revenue) if gross_profit is not None else None
		operating_row = operating_rows.get(period, {})
		operating_value = operating_row.get("value") if isinstance(operating_row, Mapping) else None
		operating_income = safe_number(operating_value) if operating_value is not None else None
		net_row = net_rows.get(period, {})
		net_value = net_row.get("value") if isinstance(net_row, Mapping) else None
		net_income = safe_number(net_value) if net_value is not None else None
		items.append(
			{
				"period": str(period),
				"revenue": revenue,
				"gross_margin": gross_margin,
				"operating_margin": (operating_income / revenue) if operating_income is not None else None,
				"net_margin": (net_income / revenue) if net_income is not None else None,
			}
		)
		if len(items) >= max_items:
			break
	return items


def _roic_rows(facts_by_metric: Mapping[str, list[dict[str, Any]]], *, max_items: int = 5, tax_rate: float = 0.21) -> list[dict[str, Any]]:
	operating_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "operating_income")}
	debt_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "total_debt")}
	equity_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "total_equity")}
	cash_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "cash_and_equivalents")}
	periods = sorted((period for period in operating_rows.keys() if period in debt_rows and period in equity_rows and period in cash_rows), reverse=True)
	items: list[dict[str, Any]] = []
	for period in periods:
		operating_income = safe_number(operating_rows[period].get("value"))
		total_debt = safe_number(debt_rows[period].get("value"))
		total_equity = safe_number(equity_rows[period].get("value"))
		cash = safe_number(cash_rows[period].get("value"))
		if None in {operating_income, total_debt, total_equity, cash}:
			continue
		invested_capital = total_debt + total_equity - cash
		if invested_capital <= 0:
			continue
		nopat = operating_income * (1 - tax_rate)
		items.append(
			{
				"period": str(period),
				"roic": nopat / invested_capital,
				"nopat": nopat,
				"invested_capital": invested_capital,
			}
		)
		if len(items) >= max_items:
			break
	return items


def _debt_to_equity_rows(facts_by_metric: Mapping[str, list[dict[str, Any]]], *, max_items: int = 5) -> list[dict[str, Any]]:
	debt_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "total_debt")}
	equity_rows = {row.get("period"): row for row in _metric_rows(facts_by_metric, "total_equity")}
	periods = sorted((period for period in debt_rows.keys() if period in equity_rows), reverse=True)
	items: list[dict[str, Any]] = []
	for period in periods:
		total_debt = safe_number(debt_rows[period].get("value"))
		total_equity = safe_number(equity_rows[period].get("value"))
		if total_debt is None or total_equity in (None, 0):
			continue
		items.append({"period": str(period), "debt_to_equity": total_debt / total_equity})
		if len(items) >= max_items:
			break
	return items


def _free_cash_flow_rows(facts_by_metric: Mapping[str, list[dict[str, Any]]], *, max_items: int = 5) -> list[dict[str, Any]]:
	free_cash_flow = {row.get("period"): row for row in _metric_rows(facts_by_metric, "free_cash_flow")}
	if not free_cash_flow:
		operating_cash_flow = {row.get("period"): row for row in _metric_rows(facts_by_metric, "operating_cash_flow")}
		capex = {row.get("period"): row for row in _metric_rows(facts_by_metric, "capital_expenditure")}
		for period, operating_cash_flow_row in operating_cash_flow.items():
			capex_row = capex.get(period)
			if capex_row is None:
				continue
			operating_cash_flow_value = safe_number(operating_cash_flow_row.get("value"))
			capex_value = safe_number(capex_row.get("value"))
			if operating_cash_flow_value is None or capex_value is None:
				continue
			free_cash_flow[period] = {"period": period, "value": operating_cash_flow_value - abs(capex_value)}
	periods = sorted((period for period in free_cash_flow.keys() if period), reverse=True)
	return [{"period": str(period), "free_cash_flow": safe_number(free_cash_flow[period].get("value"))} for period in periods[:max_items] if safe_number(free_cash_flow[period].get("value")) is not None]


def _growth_rows(metric_rows: list[dict[str, Any]], value_key: str, output_key: str, *, max_items: int = 4) -> list[dict[str, Any]]:
	chronic = sorted(metric_rows, key=lambda item: str(item.get("period") or ""))
	items: list[dict[str, Any]] = []
	for previous, current in zip(chronic, chronic[1:]):
		previous_value = safe_number(previous.get(value_key))
		current_value = safe_number(current.get(value_key))
		if previous_value in (None, 0) or current_value is None:
			continue
		items.append(
			{
				"period": str(current.get("period") or ""),
				"base_period": str(previous.get("period") or ""),
				output_key: (current_value - previous_value) / abs(previous_value),
			}
		)
	return list(reversed(items[-max_items:]))


def _series_payload(rows: list[dict[str, Any]], value_key: str, *, extra_keys: Sequence[str] | None = None) -> list[dict[str, Any]]:
	payload: list[dict[str, Any]] = []
	for row in rows:
		raw_value = row.get(value_key)
		if raw_value in (None, ""):
			continue
		value = safe_number(raw_value)
		item = {"period": str(row.get("period") or ""), "value": value}
		for key in extra_keys or ():
			if row.get(key) not in (None, ""):
				item[key] = row.get(key)
		payload.append(item)
	return payload


def _quantitative_candidate_facts(metrics_json: Mapping[str, Any], stock_data: Any) -> list[dict[str, Any]]:
	extra_facts: list[dict[str, Any]] = list(base_candidate_facts(stock_data))
	metric_specs = (
		("gross_margin", "historical_gross_margin", "Historical Gross Margin"),
		("operating_margin", "historical_operating_margin", "Historical Operating Margin"),
		("net_margin", "historical_net_margin", "Historical Net Margin"),
		("roic", "roic", "ROIC"),
		("debt_to_equity", "debt_to_equity", "Debt To Equity"),
		("free_cash_flow_growth", "historical_fcf_growth", "Historical FCF Growth"),
	)
	for metrics_key, fact_key, label in metric_specs:
		rows = list(metrics_json.get(metrics_key) or [])
		if not rows:
			continue
		value = safe_number(rows[0].get("value"))
		if value is None:
			continue
		extra_facts.append(
			CandidateFact(
				key=fact_key,
				label=label,
				value=value,
				numeric_value=value,
				source="SQLite Financials",
				confidence=0.82,
			).model_dump()
		)
	return extra_facts


def run_quantitative_analysis(
	target_ticker: str,
	stock_data: Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	_ = model_name, analysis_focus
	snapshot = build_company_snapshot(target_ticker, stock_data)
	source_links = build_source_links(target_ticker, stock_data)
	source_notes: list[Mapping[str, Any]] = [
		{
			"title": f"{target_ticker.upper()} SQLite financials",
			"url": None,
			"snippet": "Historical revenue, margin, capital, and cash-flow inputs loaded from the normalized SQLite warehouse.",
			"source_type": "sqlite_financials",
			"confidence": 0.88,
		}
	]
	fact_rows = get_sqlite_financial_facts(
		target_ticker,
		metric_names=[
			"revenue",
			"gross_profit",
			"operating_income",
			"net_income",
			"operating_cash_flow",
			"capital_expenditure",
			"free_cash_flow",
			"total_debt",
			"total_equity",
			"cash_and_equivalents",
			"gross_margin",
		],
	)
	facts_by_metric: dict[str, list[dict[str, Any]]] = {}
	for row in fact_rows:
		facts_by_metric.setdefault(str(row.get("metric_name") or ""), []).append(row)
	margin_rows = _historical_margin_rows(facts_by_metric)
	roic_rows = _roic_rows(facts_by_metric)
	debt_to_equity_rows = _debt_to_equity_rows(facts_by_metric)
	free_cash_flow_rows = _free_cash_flow_rows(facts_by_metric)
	free_cash_flow_growth_rows = _growth_rows(free_cash_flow_rows, "free_cash_flow", "free_cash_flow_growth")
	revenue_rows = _series_payload(_metric_rows(facts_by_metric, "revenue"), "value")
	metrics_json = {
		"revenue": revenue_rows[:5],
		"gross_margin": _series_payload(margin_rows, "gross_margin"),
		"operating_margin": _series_payload(margin_rows, "operating_margin"),
		"net_margin": _series_payload(margin_rows, "net_margin"),
		"roic": _series_payload(roic_rows, "roic"),
		"debt_to_equity": _series_payload(debt_to_equity_rows, "debt_to_equity"),
		"free_cash_flow": _series_payload(free_cash_flow_rows, "free_cash_flow"),
		"free_cash_flow_growth": _series_payload(free_cash_flow_growth_rows, "free_cash_flow_growth", extra_keys=("base_period",)),
		"latest_snapshot": {
			"current_price": safe_number(snapshot.get("current_price")),
			"market_cap": safe_number(snapshot.get("market_cap")),
			"starting_fcff": safe_number(snapshot.get("starting_fcff")),
			"starting_fcfe": safe_number(snapshot.get("starting_fcfe")),
		},
	}
	margin_lines = [
		f"- {clean_period_label(item.get('period'))}: gross margin {fmt_percent(item.get('gross_margin'))}; operating margin {fmt_percent(item.get('operating_margin'))}; net margin {fmt_percent(item.get('net_margin'))}."
		for item in margin_rows
	]
	roic_lines = [
		f"- {clean_period_label(item.get('period'))}: ROIC {fmt_percent(item.get('roic'))} on invested capital {fmt_money(item.get('invested_capital'))}."
		for item in roic_rows
	]
	leverage_lines = [
		f"- {clean_period_label(item.get('period'))}: debt-to-equity {fmt_percent(item.get('debt_to_equity'))}."
		for item in debt_to_equity_rows
	]
	fcf_lines = [
		f"- {clean_period_label(item.get('period'))}: free cash flow {fmt_money(item.get('free_cash_flow'))}."
		for item in free_cash_flow_rows
	]
	fcf_growth_lines = [
		f"- {clean_period_label(item.get('period'))} versus {clean_period_label(item.get('base_period'))}: FCF growth {fmt_percent(item.get('free_cash_flow_growth'))}."
		for item in free_cash_flow_growth_rows
	]
	report_markdown = "\n".join(
		[
			"### Historical Scale",
			f"- Current price: {fmt_price(snapshot.get('current_price'))}; market cap: {fmt_money(snapshot.get('market_cap'))}.",
			f"- Latest stored revenue anchor: {fmt_money(revenue_rows[0]['value']) if revenue_rows else 'N/A'}.",
			"### Historical Margins",
			"\n".join(margin_lines) or "- Historical margin rows were not available in SQLite for this run.",
			"### Returns and Leverage",
			"\n".join(roic_lines + leverage_lines) or "- ROIC and leverage metrics were not fully available from the stored rows.",
			"### Free Cash Flow",
			"\n".join(fcf_lines + fcf_growth_lines) or "- Historical free-cash-flow rows were not available in SQLite for this run.",
		]
	).strip()
	return build_analysis_artifact(
		"quantitative",
		report_markdown,
		source_links=dedupe_links(source_links),
		source_notes=source_notes,
		candidate_facts=_quantitative_candidate_facts(metrics_json, stock_data),
		confidence=0.88 if fact_rows else 0.6,
		summary=f"Quantitative read completed for {snapshot.get('company_name') or target_ticker}.",
		extra={"metrics_json": metrics_json},
	)


__all__ = ["run_quantitative_analysis"]
