from __future__ import annotations

from collections.abc import Sequence

from valuation.common import margin_of_safety, validate_discount_rate, validate_positive
from valuation.types import ValuationResult


def _validate_ratio_sequence(name: str, values: Sequence[float]) -> list[float]:
	if not values:
		raise ValueError(f"{name} must contain at least one forecast value.")
	normalized: list[float] = []
	for index, value in enumerate(values, start=1):
		numeric_value = float(value)
		if numeric_value < 0 or numeric_value > 1:
			raise ValueError(f"{name}[{index}] must be between 0% and 100%.")
		normalized.append(numeric_value)
	return normalized


def _calculate_rim_from_series(
	book_value_per_share: float,
	shares_outstanding: float,
	return_on_equity: Sequence[float],
	cost_of_equity: float,
	payout_ratio: Sequence[float],
	terminal_growth: float,
	current_price: float,
	stage_label: str,
) -> ValuationResult:
	validate_positive("Book value per share", book_value_per_share)
	validate_positive("Shares outstanding", shares_outstanding)
	validate_discount_rate(cost_of_equity, terminal_growth)
	roe_forecast = [float(value) for value in return_on_equity]
	payout_forecast = _validate_ratio_sequence("payout_ratio", payout_ratio)
	if len(roe_forecast) != len(payout_forecast):
		raise ValueError("RIM driver inputs must have matching return_on_equity and payout_ratio lengths.")
	projection_years = len(roe_forecast)
	validate_positive("Projection years", projection_years)

	beginning_book_value = book_value_per_share
	present_value_sum = 0.0
	schedule: list[dict[str, float | int | str]] = []
	last_residual_income = 0.0

	for year, (year_roe, year_payout_ratio) in enumerate(zip(roe_forecast, payout_forecast, strict=True), start=1):
		earnings_per_share = beginning_book_value * year_roe
		dividends_per_share = earnings_per_share * year_payout_ratio
		residual_income = earnings_per_share - (cost_of_equity * beginning_book_value)
		present_value = residual_income / (1 + cost_of_equity) ** year
		ending_book_value = beginning_book_value + earnings_per_share - dividends_per_share
		schedule.append(
			{
				"Year": year,
				"Beginning Book Value": beginning_book_value,
				"Earnings Per Share": earnings_per_share,
				"Dividends Per Share": dividends_per_share,
				"ROE": year_roe,
				"Payout Ratio": year_payout_ratio,
				"Residual Income": residual_income,
				"Present Value": present_value,
				"Ending Book Value": ending_book_value,
			}
		)
		present_value_sum += present_value
		last_residual_income = residual_income
		beginning_book_value = ending_book_value

	terminal_residual_next = last_residual_income * (1 + terminal_growth)
	terminal_value = terminal_residual_next / (cost_of_equity - terminal_growth)
	discounted_terminal_value = terminal_value / (1 + cost_of_equity) ** projection_years
	fair_value_per_share = book_value_per_share + present_value_sum + discounted_terminal_value
	equity_value = fair_value_per_share * shares_outstanding if shares_outstanding > 0 else fair_value_per_share
	return ValuationResult(
		model_label="RIM",
		stage_label=stage_label,
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		schedule=schedule,
	)


def calculate_rim_simple(
	book_value_per_share: float,
	shares_outstanding: float,
	return_on_equity: float,
	cost_of_equity: float,
	payout_ratio: float,
	projection_years: int,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	validate_positive("Projection years", projection_years)
	return _calculate_rim_from_series(
		book_value_per_share=book_value_per_share,
		shares_outstanding=shares_outstanding,
		return_on_equity=[float(return_on_equity)] * int(projection_years),
		cost_of_equity=cost_of_equity,
		payout_ratio=[float(payout_ratio)] * int(projection_years),
		terminal_growth=terminal_growth,
		current_price=current_price,
		stage_label="Residual Income Model",
	)


def calculate_rim_from_drivers(
	book_value_per_share: float,
	shares_outstanding: float,
	return_on_equity: Sequence[float],
	cost_of_equity: float,
	payout_ratio: Sequence[float],
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	return _calculate_rim_from_series(
		book_value_per_share=book_value_per_share,
		shares_outstanding=shares_outstanding,
		return_on_equity=return_on_equity,
		cost_of_equity=cost_of_equity,
		payout_ratio=payout_ratio,
		terminal_growth=terminal_growth,
		current_price=current_price,
		stage_label="Driver RIM",
	)


def calculate_rim(
	book_value_per_share: float,
	shares_outstanding: float,
	return_on_equity: float,
	cost_of_equity: float,
	payout_ratio: float,
	projection_years: int,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	"""Backward-compatible alias for the simple residual income model."""

	return calculate_rim_simple(
		book_value_per_share=book_value_per_share,
		shares_outstanding=shares_outstanding,
		return_on_equity=return_on_equity,
		cost_of_equity=cost_of_equity,
		payout_ratio=payout_ratio,
		projection_years=projection_years,
		terminal_growth=terminal_growth,
		current_price=current_price,
	)


__all__ = ["calculate_rim", "calculate_rim_from_drivers", "calculate_rim_simple"]
