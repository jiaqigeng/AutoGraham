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


def calculate_ddm_single_stage(
	current_dividend_per_share: float,
	shares_outstanding: float,
	required_return: float,
	stable_growth: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Current dividend per share", current_dividend_per_share)
	validate_discount_rate(required_return, stable_growth)

	next_dividend = current_dividend_per_share * (1 + stable_growth)
	fair_value_per_share = next_dividend / (required_return - stable_growth)
	equity_value = fair_value_per_share * shares_outstanding if shares_outstanding > 0 else fair_value_per_share
	return ValuationResult(
		model_label="DDM",
		stage_label="Single-Stage (Stable)",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=fair_value_per_share,
		discounted_terminal_value=0.0,
		schedule=[
			{
				"Year": "Perpetuity",
				"Growth Rate": stable_growth,
				"Cash Flow": next_dividend,
				"Present Value": fair_value_per_share,
			}
		],
	)


def calculate_ddm_two_stage(
	current_dividend_per_share: float,
	shares_outstanding: float,
	high_growth: float,
	projection_years: int,
	required_return: float,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	_validate_projection_years(projection_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_dividend_per_share,
		[high_growth] * projection_years,
		required_return,
		terminal_growth,
	)
	fair_value_per_share = present_value_sum + discounted_terminal_value
	equity_value = fair_value_per_share * shares_outstanding if shares_outstanding > 0 else fair_value_per_share
	return ValuationResult(
		model_label="DDM",
		stage_label="Two-Stage",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		schedule=schedule,
	)


def calculate_ddm_three_stage(
	current_dividend_per_share: float,
	shares_outstanding: float,
	high_growth: float,
	high_growth_years: int,
	transition_years: int,
	required_return: float,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	growth_rates = build_decay_growth_rates(high_growth, terminal_growth, high_growth_years, transition_years)
	present_value_sum, _, discounted_terminal_value, schedule = discount_explicit_series(
		current_dividend_per_share,
		growth_rates,
		required_return,
		terminal_growth,
	)
	fair_value_per_share = present_value_sum + discounted_terminal_value
	equity_value = fair_value_per_share * shares_outstanding if shares_outstanding > 0 else fair_value_per_share
	return ValuationResult(
		model_label="DDM",
		stage_label="Three-Stage (Multi-stage decay)",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		schedule=schedule,
	)


def calculate_ddm_h_model(
	current_dividend_per_share: float,
	shares_outstanding: float,
	short_term_growth: float,
	stable_growth: float,
	half_life_years: float,
	required_return: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Current dividend per share", current_dividend_per_share)
	validate_positive("H-model half-life", half_life_years)
	validate_discount_rate(required_return, stable_growth)

	fair_value_per_share = (
		current_dividend_per_share * (1 + stable_growth)
		+ current_dividend_per_share * half_life_years * (short_term_growth - stable_growth)
	) / (required_return - stable_growth)
	equity_value = fair_value_per_share * shares_outstanding if shares_outstanding > 0 else fair_value_per_share
	return ValuationResult(
		model_label="DDM",
		stage_label="H-Model",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=fair_value_per_share,
		discounted_terminal_value=0.0,
		schedule=[
			{
				"Year": "H-Model",
				"Growth Rate": short_term_growth,
				"Cash Flow": current_dividend_per_share,
				"Present Value": fair_value_per_share,
			}
		],
	)
