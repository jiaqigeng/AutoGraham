from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.subagents.parameter_estimator import estimate_parameters


class ParameterEstimatorTests(unittest.TestCase):
	def test_estimate_parameters_translates_fcff_yearly_payload(self) -> None:
		stock = SimpleNamespace(
			info={
				"currentPrice": 50.0,
				"shortName": "DriverCo",
				"marketCap": 5_000.0,
				"beta": 1.1,
				"freeCashflow": 100.0,
			},
			annual_cashflow=None,
			annual_balance_sheet=None,
			annual_income_stmt=None,
		)
		driver_json = """
{
  "company": "DriverCo",
  "ticker": "DRV",
  "currency": "USD",
  "projection_years": 5,
  "projection_rationale": "Five years balances visibility and normalization.",
  "inputs": {
    "revenue": [1000, 1070, 1130, 1180, 1220],
    "ebit_margin": [0.18, 0.185, 0.19, 0.192, 0.194],
    "tax_rate": [0.21, 0.21, 0.21, 0.21, 0.21],
    "depreciation": [40, 42, 44, 46, 48],
    "capex": [45, 47, 49, 51, 53],
    "change_in_nwc": [8, 8, 9, 9, 10],
    "wacc": 0.09,
    "terminal_growth": 0.025,
    "total_debt": 200,
    "cash": 90,
    "shares_outstanding": 100
  },
  "assumption_notes": {
    "projection_years": "Five years balances visibility and normalization.",
    "revenue": "Growth decelerates toward maturity.",
    "ebit_margin": "Margins improve modestly with scale.",
    "tax_rate": "Uses a normalized tax rate.",
    "depreciation": "Tracks the asset base.",
    "capex": "Supports growth and maintenance.",
    "change_in_nwc": "Working capital grows with scale.",
    "wacc": "Uses a normalized discount rate across the forecast period.",
    "terminal_growth": "Terminal growth stays conservative.",
    "total_debt": "Uses the latest debt balance.",
    "cash": "Uses current cash on hand.",
    "shares_outstanding": "Uses the latest diluted share count."
  },
  "model_warnings": ["Limited disclosure on future capital intensity."]
}
"""

		with patch("agent.subagents.parameter_estimator.invoke_text_prompt", return_value=driver_json):
			payload = estimate_parameters(
				ticker="DRV",
				stock_info=stock,
				candidate_facts=[],
				model_selection={"selected_model": "DCF", "selected_variant": None, "preferred_calculation_model": "FCFF"},
			)

		self.assertEqual(payload["selected_model"], "DCF")
		self.assertEqual(payload["calculation_model"], "FCFF")
		self.assertEqual(payload["assumptions"]["revenue"][0], 1000.0)
		self.assertEqual(payload["assumptions"]["wacc"], 0.09)
		self.assertEqual(payload["assumptions"]["terminal_growth"], 0.025)
		self.assertTrue(any(item["key"] == "wacc" for item in payload["assumption_reasons"]))
		self.assertIn("Limited disclosure on future capital intensity.", payload["weak_or_uncertain_inputs"])

	def test_estimate_parameters_does_not_fallback_to_simple_dcf_when_driver_payload_missing(self) -> None:
		stock = SimpleNamespace(
			info={
				"currentPrice": 200.0,
				"shortName": "Apple Inc.",
				"marketCap": 3_000_000.0,
				"beta": 1.2,
				"freeCashflow": 100.0,
				"revenueGrowth": 0.05,
				"earningsGrowth": 0.05,
			},
			annual_cashflow=None,
			annual_balance_sheet=None,
			annual_income_stmt=None,
		)

		with patch("agent.subagents.parameter_estimator.invoke_text_prompt", return_value='{"parameter_reason":"old shape"}'):
			payload = estimate_parameters(
				ticker="AAPL",
				stock_info=stock,
				candidate_facts=[],
				model_selection={"selected_model": "DCF", "selected_variant": None, "preferred_calculation_model": "FCFF"},
			)

		self.assertEqual(payload["selected_model"], "DCF")
		self.assertEqual(payload["calculation_model"], "FCFF")
		self.assertEqual(payload["assumptions"], {})
		self.assertFalse(any(key in payload["assumptions"] for key in ("growth_rate", "projection_years", "terminal_growth", "wacc")))
		self.assertIn("No simple DCF fallback was applied", payload["parameter_reason"])
		self.assertTrue(payload["weak_or_uncertain_inputs"])

	def test_estimate_parameters_translates_rim_yearly_payload(self) -> None:
		stock = SimpleNamespace(
			info={
				"currentPrice": 40.0,
				"shortName": "BankCo",
				"marketCap": 4_000.0,
				"beta": 1.0,
				"bookValue": 25.0,
				"returnOnEquity": 0.13,
				"payoutRatio": 0.40,
			},
			annual_cashflow=None,
			annual_balance_sheet=None,
			annual_income_stmt=None,
		)
		driver_json = """
{
  "company": "BankCo",
  "ticker": "BNK",
  "currency": "USD",
  "projection_years": 4,
  "projection_rationale": "Excess returns should normalize over a medium-term horizon.",
  "assumption_notes": {
    "projection_years": "Excess returns should normalize over a medium-term horizon.",
    "book_value_per_share": "Uses the latest reported book value per share.",
    "return_on_equity": "ROE fades gradually toward a mature level.",
    "payout_ratio": "Capital return rises as growth moderates.",
    "cost_of_equity": "Uses a normalized equity discount rate.",
    "terminal_growth": "Terminal growth stays conservative.",
    "shares_outstanding": "Uses the latest diluted share count."
  },
  "inputs": {
    "book_value_per_share": 25.0,
    "return_on_equity": [0.14, 0.135, 0.13, 0.125],
    "payout_ratio": [0.35, 0.38, 0.40, 0.42],
    "cost_of_equity": 0.10,
    "terminal_growth": 0.03,
    "shares_outstanding": 100
  },
  "model_warnings": ["Reserve assumptions may differ from market expectations."]
}
"""

		with patch("agent.subagents.parameter_estimator.invoke_text_prompt", return_value=driver_json):
			payload = estimate_parameters(
				ticker="BNK",
				stock_info=stock,
				candidate_facts=[],
				model_selection={"selected_model": "RIM", "selected_variant": None, "preferred_calculation_model": "RIM"},
			)

		self.assertEqual(payload["selected_model"], "RIM")
		self.assertEqual(payload["calculation_model"], "RIM")
		self.assertEqual(payload["assumptions"]["book_value_per_share"], 25.0)
		self.assertEqual(payload["assumptions"]["return_on_equity"][0], 0.14)
		self.assertEqual(payload["assumptions"]["payout_ratio"][-1], 0.42)
		self.assertTrue(any(item["key"] == "return_on_equity" for item in payload["assumption_reasons"]))
		self.assertIn("Reserve assumptions may differ from market expectations.", payload["weak_or_uncertain_inputs"])

	def test_estimate_parameters_translates_ddm_yearly_payload(self) -> None:
		stock = SimpleNamespace(
			info={
				"currentPrice": 55.0,
				"shortName": "DividendCo",
				"marketCap": 5_500.0,
				"beta": 0.9,
				"dividendRate": 1.8,
				"payoutRatio": 0.45,
			},
			annual_cashflow=None,
			annual_balance_sheet=None,
			annual_income_stmt=None,
		)
		driver_json = """
{
  "company": "DividendCo",
  "ticker": "DVD",
  "currency": "USD",
  "projection_years": 4,
  "projection_rationale": "A medium-term horizon captures normalization in payout policy.",
  "assumption_notes": {
    "projection_years": "A medium-term horizon captures normalization in payout policy.",
    "earnings_per_share": "EPS grows modestly before fading toward a mature rate.",
    "payout_ratio": "Payout expands slightly as reinvestment needs moderate.",
    "required_return": "Uses a normalized equity discount rate.",
    "terminal_growth": "Terminal growth stays conservative.",
    "shares_outstanding": "Uses the latest diluted share count."
  },
  "inputs": {
    "earnings_per_share": [4.0, 4.15, 4.3, 4.45],
    "payout_ratio": [0.45, 0.47, 0.48, 0.50],
    "required_return": 0.09,
    "terminal_growth": 0.03,
    "shares_outstanding": 100
  },
  "model_warnings": ["Payout policy could change if the economy weakens."]
}
"""

		with patch("agent.subagents.parameter_estimator.invoke_text_prompt", return_value=driver_json):
			payload = estimate_parameters(
				ticker="DVD",
				stock_info=stock,
				candidate_facts=[],
				model_selection={"selected_model": "DDM", "selected_variant": "Drivers", "preferred_calculation_model": "DDM"},
			)

		self.assertEqual(payload["selected_model"], "DDM")
		self.assertEqual(payload["selected_variant"], "Drivers")
		self.assertEqual(payload["calculation_model"], "DDM")
		self.assertEqual(payload["assumptions"]["earnings_per_share"][0], 4.0)
		self.assertEqual(payload["assumptions"]["payout_ratio"][-1], 0.5)
		self.assertEqual(payload["assumptions"]["required_return"], 0.09)
		self.assertTrue(any(item["key"] == "earnings_per_share" for item in payload["assumption_reasons"]))
		self.assertIn("Payout policy could change if the economy weakens.", payload["weak_or_uncertain_inputs"])


if __name__ == "__main__":
	unittest.main()
