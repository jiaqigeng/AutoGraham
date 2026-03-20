from __future__ import annotations

import unittest

from valuation.rim import calculate_rim


class RIMTests(unittest.TestCase):
	def test_rim_returns_positive_value(self) -> None:
		result = calculate_rim(
			book_value_per_share=20.0,
			shares_outstanding=100.0,
			return_on_equity=0.12,
			cost_of_equity=0.09,
			payout_ratio=0.3,
			projection_years=5,
			terminal_growth=0.03,
			current_price=18.0,
		)
		self.assertEqual(result.model_label, "RIM")
		self.assertGreater(result.fair_value_per_share, 20.0)

	def test_rim_matches_book_value_plus_discounted_residual_income(self) -> None:
		result = calculate_rim(
			book_value_per_share=20.0,
			shares_outstanding=100.0,
			return_on_equity=0.12,
			cost_of_equity=0.09,
			payout_ratio=0.3,
			projection_years=2,
			terminal_growth=0.03,
			current_price=18.0,
		)

		book_value_year_0 = 20.0
		residual_income_year_1 = book_value_year_0 * (0.12 - 0.09)
		book_value_year_1 = book_value_year_0 + (book_value_year_0 * 0.12) - (book_value_year_0 * 0.12 * 0.3)
		residual_income_year_2 = book_value_year_1 * (0.12 - 0.09)
		pv_year_1 = residual_income_year_1 / 1.09
		pv_year_2 = residual_income_year_2 / (1.09**2)
		terminal_residual_next = residual_income_year_2 * 1.03
		discounted_terminal_value = (terminal_residual_next / (0.09 - 0.03)) / (1.09**2)
		expected_fair_value = book_value_year_0 + pv_year_1 + pv_year_2 + discounted_terminal_value

		self.assertAlmostEqual(result.fair_value_per_share, expected_fair_value, places=6)
		self.assertAlmostEqual(result.schedule[-1]["Ending Book Value"], book_value_year_1 + (book_value_year_1 * 0.12) - (book_value_year_1 * 0.12 * 0.3), places=6)


if __name__ == "__main__":
	unittest.main()
