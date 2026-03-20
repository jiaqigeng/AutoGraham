from __future__ import annotations

from valuation.common import margin_of_safety, validate_discount_rate, validate_positive
from valuation.types import ValuationResult


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
	validate_positive("Book value per share", book_value_per_share)
	validate_positive("Projection years", projection_years)
	validate_discount_rate(cost_of_equity, terminal_growth)
	if payout_ratio < 0 or payout_ratio > 1:
		raise ValueError("Payout ratio must be between 0% and 100%.")

	beginning_book_value = book_value_per_share
	present_value_sum = 0.0
	schedule: list[dict[str, float | int | str]] = []
	last_residual_income = 0.0

	for year in range(1, projection_years + 1):
		earnings_per_share = beginning_book_value * return_on_equity
		dividends_per_share = earnings_per_share * payout_ratio
		residual_income = earnings_per_share - (cost_of_equity * beginning_book_value)
		present_value = residual_income / (1 + cost_of_equity) ** year
		ending_book_value = beginning_book_value + earnings_per_share - dividends_per_share
		schedule.append(
			{
				"Year": year,
				"Beginning Book Value": beginning_book_value,
				"Earnings Per Share": earnings_per_share,
				"Dividends Per Share": dividends_per_share,
				"ROE": return_on_equity,
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
		stage_label="Residual Income Model",
		equity_value=equity_value,
		fair_value_per_share=fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(fair_value_per_share, current_price),
		present_value_of_cash_flows=present_value_sum,
		discounted_terminal_value=discounted_terminal_value,
		schedule=schedule,
	)
