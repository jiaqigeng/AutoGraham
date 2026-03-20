from __future__ import annotations

import unittest

from valuation.ddm import calculate_ddm_h_model, calculate_ddm_single_stage, calculate_ddm_two_stage


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


if __name__ == "__main__":
	unittest.main()
