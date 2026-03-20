from __future__ import annotations

import unittest

import pandas as pd

from valuation.common import default_valuation_inputs
from valuation.dcf import calculate_fcfe_two_stage, calculate_fcff_single_stage


def _frame(values: dict[str, float]) -> pd.DataFrame:
	return pd.DataFrame({pd.Timestamp("2024-12-31"): values})


class DCFTests(unittest.TestCase):
	def test_default_inputs_adds_after_tax_interest_to_fcff(self) -> None:
		info = {
			"currentPrice": 50.0,
			"marketCap": 5_000.0,
			"effectiveTaxRate": 0.25,
			"totalDebt": 800.0,
			"totalCash": 150.0,
		}
		defaults = default_valuation_inputs(
			info,
			annual_cashflow=_frame(
				{
					"Free Cash Flow": 100.0,
					"Operating Cash Flow": 150.0,
					"Capital Expenditure": -50.0,
					"Net Issuance Payments Of Debt": 20.0,
				}
			),
			annual_balance_sheet=_frame(
				{
					"Total Debt": 800.0,
					"Cash And Cash Equivalents": 150.0,
					"Stockholders Equity": 2_000.0,
				}
			),
			annual_income_stmt=_frame(
				{
					"Interest Expense": 40.0,
					"Pretax Income": 200.0,
					"Tax Provision": 50.0,
				}
			),
		)

		self.assertEqual(defaults["starting_fcff"], 130.0)
		self.assertEqual(defaults["starting_fcfe"], 120.0)

	def test_default_inputs_convert_net_debt_to_gross_debt_when_cash_is_known(self) -> None:
		info = {
			"currentPrice": 20.0,
			"marketCap": 2_000.0,
			"effectiveTaxRate": 0.21,
			"totalCash": 300.0,
		}
		defaults = default_valuation_inputs(
			info,
			annual_cashflow=_frame({"Free Cash Flow": 80.0, "Operating Cash Flow": 100.0, "Capital Expenditure": -20.0}),
			annual_balance_sheet=_frame({"Net Debt": 500.0, "Cash And Cash Equivalents": 300.0, "Stockholders Equity": 1_200.0}),
			annual_income_stmt=_frame({"Interest Expense": 25.0, "Pretax Income": 100.0, "Tax Provision": 21.0}),
		)

		self.assertEqual(defaults["cash"], 300.0)
		self.assertEqual(defaults["total_debt"], 800.0)

	def test_fcff_single_stage_returns_positive_value(self) -> None:
		result = calculate_fcff_single_stage(
			current_fcff=100.0,
			shares_outstanding=10.0,
			wacc=0.10,
			stable_growth=0.03,
			total_debt=50.0,
			cash=20.0,
			current_price=8.0,
		)

		self.assertGreater(result.fair_value_per_share, 0)
		self.assertEqual(result.model_label, "FCFF")

	def test_fcff_single_stage_matches_gordon_growth_bridge(self) -> None:
		result = calculate_fcff_single_stage(
			current_fcff=100.0,
			shares_outstanding=10.0,
			wacc=0.10,
			stable_growth=0.03,
			total_debt=50.0,
			cash=20.0,
			current_price=8.0,
		)

		expected_enterprise_value = (100.0 * 1.03) / (0.10 - 0.03)
		expected_equity_value = expected_enterprise_value - 50.0 + 20.0
		expected_fair_value_per_share = expected_equity_value / 10.0
		self.assertAlmostEqual(result.enterprise_value or 0.0, expected_enterprise_value, places=6)
		self.assertAlmostEqual(result.equity_value, expected_equity_value, places=6)
		self.assertAlmostEqual(result.fair_value_per_share, expected_fair_value_per_share, places=6)

	def test_fcfe_two_stage_requires_positive_projection_years(self) -> None:
		with self.assertRaisesRegex(ValueError, "Projection years"):
			calculate_fcfe_two_stage(
				current_fcfe=100.0,
				shares_outstanding=10.0,
				high_growth=0.08,
				projection_years=0,
				cost_of_equity=0.11,
				terminal_growth=0.03,
				current_price=8.0,
			)


if __name__ == "__main__":
	unittest.main()
