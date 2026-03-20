from __future__ import annotations

from valuation.common import (
	build_decay_growth_rates,
	discount_explicit_series,
	margin_of_safety,
	validate_discount_rate,
	validate_positive,
)
from valuation.types import ValuationResult


def _validate_projection_years(projection_years: int) -> None:
	validate_positive("Projection years", projection_years)


def calculate_fcfe_single_stage(
	current_fcfe: float,
	shares_outstanding: float,
	cost_of_equity: float,
	stable_growth: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	validate_positive("Starting FCFE", current_fcfe)
	validate_discount_rate(cost_of_equity, stable_growth)

	next_year_fcfe = current_fcfe * (1 + stable_growth)
	equity_value = next_year_fcfe / (cost_of_equity - stable_growth)
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="FCFE",
		stage_label="Single-Stage (Stable)",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=equity_value,
		discounted_terminal_value=0.0,
		schedule=[
			{
				"Year": "Perpetuity",
				"Growth Rate": stable_growth,
				"Cash Flow": next_year_fcfe,
				"Present Value": equity_value,
			}
		],
	)


def calculate_fcfe_two_stage(
	current_fcfe: float,
	shares_outstanding: float,
	high_growth: float,
	projection_years: int,
	cost_of_equity: float,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	_validate_projection_years(projection_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_fcfe,
		[high_growth] * projection_years,
		cost_of_equity,
		terminal_growth,
	)
	equity_value = present_value_sum + discounted_terminal_value
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="FCFE",
		stage_label="Two-Stage",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		schedule=schedule,
	)


def calculate_fcfe_three_stage(
	current_fcfe: float,
	shares_outstanding: float,
	high_growth: float,
	high_growth_years: int,
	transition_years: int,
	cost_of_equity: float,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	growth_rates = build_decay_growth_rates(high_growth, terminal_growth, high_growth_years, transition_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_fcfe,
		growth_rates,
		cost_of_equity,
		terminal_growth,
	)
	equity_value = present_value_sum + discounted_terminal_value
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="FCFE",
		stage_label="Three-Stage (Multi-stage decay)",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		schedule=schedule,
	)


def calculate_fcff_single_stage(
	current_fcff: float,
	shares_outstanding: float,
	wacc: float,
	stable_growth: float,
	total_debt: float,
	cash: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	validate_positive("Starting FCFF", current_fcff)
	validate_discount_rate(wacc, stable_growth)

	next_year_fcff = current_fcff * (1 + stable_growth)
	enterprise_value = next_year_fcff / (wacc - stable_growth)
	equity_value = enterprise_value - total_debt + cash
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="FCFF",
		stage_label="Single-Stage (Stable)",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=enterprise_value,
		discounted_terminal_value=0.0,
		enterprise_value=enterprise_value,
		schedule=[
			{
				"Year": "Perpetuity",
				"Growth Rate": stable_growth,
				"Cash Flow": next_year_fcff,
				"Present Value": enterprise_value,
			}
		],
	)


def calculate_fcff_two_stage(
	current_fcff: float,
	shares_outstanding: float,
	high_growth: float,
	projection_years: int,
	wacc: float,
	terminal_growth: float,
	total_debt: float,
	cash: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	_validate_projection_years(projection_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_fcff,
		[high_growth] * projection_years,
		wacc,
		terminal_growth,
	)
	enterprise_value = present_value_sum + discounted_terminal_value
	equity_value = enterprise_value - total_debt + cash
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="FCFF",
		stage_label="Two-Stage",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		enterprise_value=enterprise_value,
		schedule=schedule,
	)


def calculate_fcff_three_stage(
	current_fcff: float,
	shares_outstanding: float,
	high_growth: float,
	high_growth_years: int,
	transition_years: int,
	wacc: float,
	terminal_growth: float,
	total_debt: float,
	cash: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	growth_rates = build_decay_growth_rates(high_growth, terminal_growth, high_growth_years, transition_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_fcff,
		growth_rates,
		wacc,
		terminal_growth,
	)
	enterprise_value = present_value_sum + discounted_terminal_value
	equity_value = enterprise_value - total_debt + cash
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="FCFF",
		stage_label="Three-Stage (Multi-stage decay)",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		enterprise_value=enterprise_value,
		schedule=schedule,
	)


def calculate_apv(
	current_fcff: float,
	shares_outstanding: float,
	high_growth: float,
	projection_years: int,
	unlevered_cost: float,
	terminal_growth: float,
	total_debt: float,
	cash: float,
	tax_rate: float,
	cost_of_debt: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Shares outstanding", shares_outstanding)
	validate_positive("Cost of debt", cost_of_debt)
	_validate_projection_years(projection_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_fcff,
		[high_growth] * projection_years,
		unlevered_cost,
		terminal_growth,
	)
	unlevered_enterprise_value = present_value_sum + discounted_terminal_value
	annual_tax_shield = total_debt * cost_of_debt * tax_rate
	pv_tax_shield = 0.0
	for year in range(1, projection_years + 1):
		pv_tax_shield += annual_tax_shield / (1 + cost_of_debt) ** year
	terminal_tax_shield = annual_tax_shield / cost_of_debt
	pv_tax_shield += terminal_tax_shield / (1 + cost_of_debt) ** projection_years
	levered_enterprise_value = unlevered_enterprise_value + pv_tax_shield
	equity_value = levered_enterprise_value - total_debt + cash
	fair_value_per_share = equity_value / shares_outstanding
	return ValuationResult(
		model_label="APV",
		stage_label="Adjusted Present Value",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		enterprise_value=levered_enterprise_value,
		tax_shield_value=pv_tax_shield,
		schedule=schedule,
	)
