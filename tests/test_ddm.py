from __future__ import annotations

import unittest

from valuation.ddm import calculate_ddm_from_drivers, calculate_ddm_h_model, calculate_ddm_single_stage, calculate_ddm_two_stage


class DDMTests(unittest.TestCase):
	def test_ddm_single_stage_uses_gordon_growth(self) -> None:
		result = calculate_ddm_single_stage(
			current_dividend_per_share=2.0,
			shares_outstanding=100.0,
			required_return=0.10,
			stable_growth=0.03,
			current_price=20.0,
		)
		self.assertAlmostEqual(result.fair_value_per_share, 29.4285714286, places=4)

	def test_h_model_returns_named_stage(self) -> None:
		result = calculate_ddm_h_model(
			current_dividend_per_share=2.0,
			shares_outstanding=100.0,
			short_term_growth=0.07,
			stable_growth=0.03,
			half_life_years=4.0,
			required_return=0.10,
			current_price=20.0,
		)
		self.assertEqual(result.stage_label, "H-Model")
		self.assertGreater(result.fair_value_per_share, 0)

	def test_h_model_matches_formula(self) -> None:
		result = calculate_ddm_h_model(
			current_dividend_per_share=2.0,
			shares_outstanding=100.0,
			short_term_growth=0.07,
			stable_growth=0.03,
			half_life_years=4.0,
			required_return=0.10,
			current_price=20.0,
		)

		expected = (2.0 * (1 + 0.03) + 2.0 * 4.0 * (0.07 - 0.03)) / (0.10 - 0.03)
		self.assertAlmostEqual(result.fair_value_per_share, expected, places=6)

	def test_two_stage_requires_positive_projection_years(self) -> None:
		with self.assertRaisesRegex(ValueError, "Projection years"):
			calculate_ddm_two_stage(
				current_dividend_per_share=2.0,
				shares_outstanding=100.0,
				high_growth=0.07,
				projection_years=0,
				required_return=0.10,
				terminal_growth=0.03,
				current_price=20.0,
			)

	def test_driver_ddm_projects_dividends_from_eps_and_payout(self) -> None:
		result = calculate_ddm_from_drivers(
			earnings_per_share=[4.0, 4.2, 4.4],
			payout_ratio=[0.50, 0.50, 0.50],
			required_return=0.10,
			terminal_growth=0.03,
			shares_outstanding=100.0,
			current_price=20.0,
		)

		expected_present_value = (2.0 / 1.10) + (2.1 / 1.10**2) + (2.2 / 1.10**3)
		expected_terminal = (2.2 * 1.03) / (0.10 - 0.03) / 1.10**3
		self.assertEqual(result.stage_label, "Driver DDM")
		self.assertAlmostEqual(result.present_value_of_cash_flows, expected_present_value, places=6)
		self.assertAlmostEqual(result.discounted_terminal_value, expected_terminal, places=6)
		self.assertAlmostEqual(result.fair_value_per_share, expected_present_value + expected_terminal, places=6)
		self.assertEqual(result.schedule[0]["Dividend Per Share"], 2.0)


if __name__ == "__main__":
	unittest.main()
