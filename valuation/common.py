from __future__ import annotations

import math
from typing import Any, Mapping

try:
	import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on local interpreter setup.
	pd = None  # type: ignore[assignment]


class _EmptySeries:
	index: tuple[str, ...] = ()

	def get(self, _label: str) -> None:
		return None


def safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		numeric_value = float(value)
	except (TypeError, ValueError):
		return 0.0
	if math.isnan(numeric_value):
		return 0.0
	return numeric_value


def normalize_rate(value: object, fallback: float = 0.0) -> float:
	rate = safe_number(value)
	if rate == 0:
		return fallback
	if abs(rate) > 1:
		return rate / 100
	return rate


def safe_divide(numerator: float, denominator: float) -> float:
	if denominator == 0:
		return 0.0
	return numerator / denominator


def clip_value(value: float, lower: float, upper: float) -> float:
	return max(lower, min(value, upper))


def latest_statement_column(frame: pd.DataFrame | None) -> pd.Series | _EmptySeries:
	if frame is None:
		return pd.Series(dtype=float) if pd is not None else _EmptySeries()
	if pd is None:
		raise ModuleNotFoundError("pandas is required when statement DataFrames are provided.")
	if frame.empty:
		return pd.Series(dtype=float)
	sorted_columns = frame.columns.sort_values(ascending=False)
	return frame[sorted_columns[0]].fillna(0)


def statement_value(series: pd.Series, *labels: str) -> float:
	for label in labels:
		if label in series.index:
			return safe_number(series.get(label))
	return 0.0


def derive_shares_outstanding(
	market_cap: float,
	current_price: float,
	income_series: pd.Series,
	balance_series: pd.Series,
) -> float:
	if market_cap > 0 and current_price > 0:
		shares_outstanding = market_cap / current_price
		if shares_outstanding > 0:
			return shares_outstanding

	shares_outstanding = statement_value(balance_series, "Ordinary Shares Number", "Share Issued")
	if shares_outstanding > 0:
		return shares_outstanding

	return statement_value(
		income_series,
		"Diluted Average Shares",
		"Diluted Average Shares Outstanding",
		"Diluted Weighted Average Shares",
		"Diluted Weighted Average Shares Outstanding",
		"Basic Average Shares",
	)


def derive_growth_assumptions(
	info: Mapping[str, Any],
	payout_ratio: float,
	return_on_equity: float,
) -> tuple[float, float, float, float, float]:
	revenue_growth = normalize_rate(info.get("revenueGrowth"), 0.0)
	earnings_growth = normalize_rate(info.get("earningsGrowth"), 0.0)
	sustainable_growth = return_on_equity * max(0.0, 1 - payout_ratio)

	observed_growth_candidates = [
		candidate
		for candidate in (earnings_growth, revenue_growth, sustainable_growth)
		if candidate > -0.95
	]
	base_growth = sum(observed_growth_candidates) / len(observed_growth_candidates) if observed_growth_candidates else 0.06
	high_growth = clip_value(base_growth, -0.05, 0.18)
	stable_growth = clip_value(min(high_growth * 0.5, 0.03), -0.01, 0.03)

	if high_growth >= 0.14:
		projection_years = 7.0
	elif high_growth >= 0.08:
		projection_years = 5.0
	else:
		projection_years = 3.0

	high_growth_years = projection_years
	transition_years = 5.0 if high_growth > stable_growth + 0.03 else 3.0
	return high_growth, stable_growth, projection_years, high_growth_years, transition_years


def derive_capital_costs(
	info: Mapping[str, Any],
	tax_rate: float,
	total_debt: float,
	market_cap: float,
	interest_expense: float,
) -> tuple[float, float, float]:
	risk_free_rate = 0.0425
	equity_risk_premium = 0.055
	beta = safe_number(info.get("beta")) or 1.0
	beta = clip_value(beta, 0.6, 2.2)
	cost_of_equity = clip_value(risk_free_rate + beta * equity_risk_premium, 0.07, 0.18)

	base_cost_of_debt = safe_divide(interest_expense, total_debt)
	if base_cost_of_debt <= 0:
		interest_coverage = safe_divide(safe_number(info.get("ebitda")), interest_expense)
		if interest_coverage >= 8:
			base_cost_of_debt = 0.045
		elif interest_coverage >= 4:
			base_cost_of_debt = 0.055
		elif interest_coverage > 0:
			base_cost_of_debt = 0.07
		else:
			base_cost_of_debt = 0.06
	cost_of_debt = clip_value(base_cost_of_debt, 0.03, 0.12)

	enterprise_weight = market_cap + total_debt
	equity_weight = safe_divide(market_cap, enterprise_weight) if enterprise_weight > 0 else 1.0
	debt_weight = safe_divide(total_debt, enterprise_weight) if enterprise_weight > 0 else 0.0
	wacc = (equity_weight * cost_of_equity) + (debt_weight * cost_of_debt * (1 - tax_rate))
	wacc = clip_value(wacc if wacc > 0 else cost_of_equity, 0.06, 0.16)
	return cost_of_equity, cost_of_debt, wacc


def derive_total_debt(
	balance_series: pd.Series,
	info: Mapping[str, Any],
	cash: float,
) -> float:
	total_debt = max(
		statement_value(
			balance_series,
			"Total Debt",
			"Long Term Debt And Capital Lease Obligation",
			"Long Term Debt",
			"Current Debt",
		),
		0.0,
	)
	if total_debt > 0:
		return total_debt

	total_debt = max(safe_number(info.get("totalDebt")), 0.0)
	if total_debt > 0:
		return total_debt

	net_debt = max(statement_value(balance_series, "Net Debt"), 0.0)
	if net_debt > 0:
		return net_debt + cash if cash > 0 else net_debt

	return 0.0


def default_valuation_inputs(
	info: Mapping[str, Any],
	annual_cashflow: pd.DataFrame | None = None,
	annual_balance_sheet: pd.DataFrame | None = None,
	annual_income_stmt: pd.DataFrame | None = None,
) -> dict[str, float]:
	current_price = safe_number(info.get("currentPrice", info.get("regularMarketPrice", 0)))
	market_cap = safe_number(info.get("marketCap"))
	dividend_yield = normalize_rate(info.get("dividendYield"), 0.0)
	dividend_rate = safe_number(info.get("dividendRate"))
	if dividend_rate <= 0 and current_price > 0 and dividend_yield > 0:
		dividend_rate = current_price * dividend_yield

	cashflow_series = latest_statement_column(annual_cashflow)
	balance_series = latest_statement_column(annual_balance_sheet)
	income_series = latest_statement_column(annual_income_stmt)
	shares_outstanding = derive_shares_outstanding(market_cap, current_price, income_series, balance_series)

	levered_free_cash_flow = statement_value(cashflow_series, "Free Cash Flow")
	if levered_free_cash_flow <= 0:
		levered_free_cash_flow = safe_number(info.get("freeCashflow"))

	operating_cash_flow = statement_value(cashflow_series, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
	if operating_cash_flow <= 0:
		operating_cash_flow = safe_number(info.get("operatingCashflow"))

	capital_expenditure = abs(statement_value(cashflow_series, "Capital Expenditure"))
	interest_expense = abs(statement_value(income_series, "Interest Expense"))
	tax_rate = normalize_rate(info.get("effectiveTaxRate"), 0.0)
	if tax_rate <= 0:
		tax_rate = normalize_rate(statement_value(income_series, "Tax Rate For Calcs"), 0.0)
	if tax_rate <= 0:
		pretax_income = statement_value(income_series, "Pretax Income")
		tax_provision = statement_value(income_series, "Tax Provision")
		tax_rate = safe_divide(tax_provision, pretax_income) if pretax_income > 0 else 0.21
	tax_rate = clip_value(tax_rate if tax_rate > 0 else 0.21, 0.10, 0.35)

	net_borrowing = statement_value(cashflow_series, "Net Issuance Payments Of Debt")
	if net_borrowing == 0:
		net_borrowing = statement_value(cashflow_series, "Issuance Of Debt") - abs(statement_value(cashflow_series, "Repayment Of Debt"))

	if levered_free_cash_flow <= 0 and operating_cash_flow > 0 and capital_expenditure > 0:
		levered_free_cash_flow = operating_cash_flow - capital_expenditure

	after_tax_interest = interest_expense * (1 - tax_rate)
	starting_fcff = levered_free_cash_flow + after_tax_interest if levered_free_cash_flow > 0 else operating_cash_flow + after_tax_interest - capital_expenditure
	if starting_fcff <= 0:
		starting_fcff = max(operating_cash_flow + after_tax_interest - capital_expenditure, 0.0)

	starting_fcfe = levered_free_cash_flow + net_borrowing if levered_free_cash_flow > 0 and net_borrowing != 0 else levered_free_cash_flow
	if starting_fcfe <= 0 and operating_cash_flow > 0:
		starting_fcfe = max(operating_cash_flow - capital_expenditure + net_borrowing, 0.0)
	if starting_fcfe <= 0:
		starting_fcfe = safe_number(info.get("freeCashflow"))

	cash = max(statement_value(balance_series, "Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", "Cash Equivalents"), 0.0)
	if cash <= 0:
		cash = max(safe_number(info.get("totalCash")), 0.0)
	total_debt = derive_total_debt(balance_series, info, cash)

	book_value_per_share = max(safe_number(info.get("bookValue")), 0.0)
	if book_value_per_share <= 0 and shares_outstanding > 0:
		stockholders_equity = statement_value(balance_series, "Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest")
		book_value_per_share = max(safe_divide(stockholders_equity, shares_outstanding), 0.0)

	payout_ratio = normalize_rate(info.get("payoutRatio"), 0.0)
	if payout_ratio <= 0:
		cash_dividends_paid = abs(statement_value(cashflow_series, "Cash Dividends Paid", "Common Stock Dividend Paid"))
		net_income = abs(statement_value(income_series, "Net Income", "Net Income Common Stockholders"))
		payout_ratio = safe_divide(cash_dividends_paid, net_income) if net_income > 0 else 0.35
	payout_ratio = clip_value(payout_ratio if payout_ratio > 0 else 0.35, 0.0, 1.0)

	return_on_equity = normalize_rate(info.get("returnOnEquity"), 0.0)
	if return_on_equity <= 0 and book_value_per_share > 0:
		eps = safe_number(info.get("trailingEps", info.get("forwardEps", 0)))
		return_on_equity = safe_divide(eps, book_value_per_share)
	return_on_equity = clip_value(return_on_equity if return_on_equity > 0 else 0.12, 0.06, 0.30)

	if market_cap <= 0 and current_price > 0 and shares_outstanding > 0:
		market_cap = current_price * shares_outstanding

	cost_of_equity, cost_of_debt, wacc = derive_capital_costs(info, tax_rate, total_debt, market_cap, interest_expense)
	debt_to_equity = safe_divide(total_debt, market_cap) if market_cap > 0 else 0.0
	beta = clip_value(safe_number(info.get("beta")) or 1.0, 0.6, 2.2)
	asset_beta = safe_divide(beta, 1 + ((1 - tax_rate) * debt_to_equity)) if market_cap > 0 else beta
	unlevered_cost = clip_value(0.0425 + asset_beta * 0.055, 0.06, 0.16)

	high_growth, stable_growth, projection_years, high_growth_years, transition_years = derive_growth_assumptions(info, payout_ratio, return_on_equity)

	return {
		"current_price": current_price,
		"shares_outstanding": shares_outstanding,
		"starting_fcfe": max(starting_fcfe, 0.0),
		"starting_fcff": max(starting_fcff, 0.0),
		"dividend_per_share": max(dividend_rate, 0.0),
		"total_debt": total_debt,
		"cash": cash,
		"book_value_per_share": book_value_per_share,
		"return_on_equity": return_on_equity,
		"payout_ratio": payout_ratio,
		"tax_rate": tax_rate,
		"cost_of_equity": cost_of_equity,
		"wacc": wacc,
		"unlevered_cost": unlevered_cost,
		"cost_of_debt": cost_of_debt,
		"high_growth": high_growth,
		"stable_growth": stable_growth,
		"projection_years": projection_years,
		"high_growth_years": high_growth_years,
		"transition_years": transition_years,
	}


def margin_of_safety(fair_value_per_share: float, current_price: float) -> float | None:
	if fair_value_per_share <= 0 or current_price <= 0:
		return None
	return ((fair_value_per_share - current_price) / current_price) * 100


def validate_discount_rate(discount_rate: float, terminal_growth: float) -> None:
	if discount_rate <= 0:
		raise ValueError("Discount rate must be positive.")
	if terminal_growth >= discount_rate:
		raise ValueError("Terminal growth rate must be lower than the discount rate.")


def validate_positive(label: str, value: float) -> None:
	if value <= 0:
		raise ValueError(f"{label} must be greater than zero.")


def discount_explicit_series(
	base_cash_flow: float,
	growth_rates: list[float],
	discount_rate: float,
	terminal_growth: float,
) -> tuple[float, float, float, list[dict[str, float | int | str]]]:
	validate_positive("Starting cash flow", base_cash_flow)
	validate_discount_rate(discount_rate, terminal_growth)

	schedule: list[dict[str, float | int | str]] = []
	present_value_sum = 0.0
	cash_flow = base_cash_flow

	for year, growth_rate in enumerate(growth_rates, start=1):
		cash_flow *= 1 + growth_rate
		present_value = cash_flow / (1 + discount_rate) ** year
		schedule.append(
			{
				"Year": year,
				"Growth Rate": growth_rate,
				"Cash Flow": cash_flow,
				"Present Value": present_value,
			}
		)
		present_value_sum += present_value

	terminal_value = cash_flow * (1 + terminal_growth) / (discount_rate - terminal_growth)
	discounted_terminal_value = terminal_value / (1 + discount_rate) ** len(growth_rates)
	return present_value_sum, terminal_value, discounted_terminal_value, schedule


def build_decay_growth_rates(
	high_growth: float,
	terminal_growth: float,
	high_growth_years: int,
	transition_years: int,
) -> list[float]:
	if high_growth_years < 1:
		raise ValueError("High-growth period must be at least one year.")
	if transition_years < 1:
		raise ValueError("Transition period must be at least one year.")

	growth_rates = [high_growth] * high_growth_years
	for step in range(1, transition_years + 1):
		growth_rate = high_growth + (terminal_growth - high_growth) * (step / transition_years)
		growth_rates.append(growth_rate)
	return growth_rates
