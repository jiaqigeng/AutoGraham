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


if __name__ == "__main__":
	unittest.main()
