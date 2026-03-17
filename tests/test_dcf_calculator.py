from __future__ import annotations

import unittest

import pandas as pd

from utils.dcf_calculator import default_valuation_inputs


def _frame(values: dict[str, float]) -> pd.DataFrame:
	return pd.DataFrame({pd.Timestamp("2024-12-31"): values})


class DefaultValuationInputsTests(unittest.TestCase):
	def test_default_inputs_adds_after_tax_interest_to_fcff(self) -> None:
		info = {
			"currentPrice": 50.0,
			"marketCap": 5_000.0,
			"effectiveTaxRate": 0.25,
			"totalDebt": 800.0,
			"totalCash": 150.0,
		}
		annual_cashflow = _frame(
			{
				"Free Cash Flow": 100.0,
				"Operating Cash Flow": 150.0,
				"Capital Expenditure": -50.0,
				"Net Issuance Payments Of Debt": 20.0,
			}
		)
		annual_balance_sheet = _frame(
			{
				"Total Debt": 800.0,
				"Cash And Cash Equivalents": 150.0,
				"Stockholders Equity": 2_000.0,
			}
		)
		annual_income_stmt = _frame(
			{
				"Interest Expense": 40.0,
				"Pretax Income": 200.0,
				"Tax Provision": 50.0,
			}
		)

		defaults = default_valuation_inputs(
			info,
			annual_cashflow=annual_cashflow,
			annual_balance_sheet=annual_balance_sheet,
			annual_income_stmt=annual_income_stmt,
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
		annual_cashflow = _frame(
			{
				"Free Cash Flow": 80.0,
				"Operating Cash Flow": 100.0,
				"Capital Expenditure": -20.0,
			}
		)
		annual_balance_sheet = _frame(
			{
				"Net Debt": 500.0,
				"Cash And Cash Equivalents": 300.0,
				"Stockholders Equity": 1_200.0,
			}
		)
		annual_income_stmt = _frame(
			{
				"Interest Expense": 25.0,
				"Pretax Income": 100.0,
				"Tax Provision": 21.0,
			}
		)

		defaults = default_valuation_inputs(
			info,
			annual_cashflow=annual_cashflow,
			annual_balance_sheet=annual_balance_sheet,
			annual_income_stmt=annual_income_stmt,
		)

		self.assertEqual(defaults["cash"], 300.0)
		self.assertEqual(defaults["total_debt"], 800.0)

	def test_default_growth_assumptions_allow_low_or_negative_terminal_growth(self) -> None:
		info = {
			"currentPrice": 10.0,
			"marketCap": 1_000.0,
			"revenueGrowth": -0.03,
			"earningsGrowth": -0.04,
			"payoutRatio": 0.9,
			"returnOnEquity": 0.05,
		}
		annual_cashflow = _frame(
			{
				"Free Cash Flow": 40.0,
				"Operating Cash Flow": 50.0,
				"Capital Expenditure": -10.0,
			}
		)
		annual_balance_sheet = _frame(
			{
				"Total Debt": 100.0,
				"Cash And Cash Equivalents": 50.0,
				"Stockholders Equity": 500.0,
			}
		)
		annual_income_stmt = _frame(
			{
				"Interest Expense": 10.0,
				"Pretax Income": 80.0,
				"Tax Provision": 16.0,
			}
		)

		defaults = default_valuation_inputs(
			info,
			annual_cashflow=annual_cashflow,
			annual_balance_sheet=annual_balance_sheet,
			annual_income_stmt=annual_income_stmt,
		)

		self.assertLess(defaults["high_growth"], 0)
		self.assertLessEqual(defaults["stable_growth"], 0)


if __name__ == "__main__":
	unittest.main()
