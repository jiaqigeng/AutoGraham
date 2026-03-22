from __future__ import annotations

import unittest

import pandas as pd

from agent.tools.calculator_tools import calculate_recommended_value, run_valuation_calculation
from agent.tools.validation_tools import extract_json_object, validate_parameter_payload


def _frame(values: dict[str, float]) -> pd.DataFrame:
	return pd.DataFrame({pd.Timestamp("2024-12-31"): values})


class AgentToolsTests(unittest.TestCase):
	def test_extract_json_object_handles_fenced_block(self) -> None:
		payload = extract_json_object('```json\n{"selected_model":"RIM"}\n```')
		self.assertEqual(payload["selected_model"], "RIM")

	def test_calculator_tools_run_deterministic_model(self) -> None:
		info = {
			"currentPrice": 40.0,
			"marketCap": 40_000.0,
			"bookValue": 28.0,
			"returnOnEquity": 0.13,
			"payoutRatio": 0.45,
			"beta": 1.0,
		}
		result = calculate_recommended_value(
			info,
			{
				"selected_model": "RIM",
				"growth_stage": None,
				"model_reason": "Book value matters.",
				"parameter_reason": "Residual income fits.",
				"assumptions": {"cost_of_equity": 0.10, "projection_years": 5, "terminal_growth": 0.025},
				"assumption_reasons": [],
			},
			annual_cashflow=_frame({"Free Cash Flow": 100.0}),
			annual_balance_sheet=_frame({"Stockholders Equity": 28_000.0}),
			annual_income_stmt=_frame({"Net Income": 3_640.0}),
		)
		self.assertEqual(result["selected_model"], "RIM")
		self.assertGreater(result["fair_value_per_share"], 0)

	def test_validate_parameter_payload_detects_fcff_driver_inputs(self) -> None:
		payload = {
			"selected_model": "DCF",
			"selected_variant": None,
			"calculation_model": "FCFF",
			"fetched_facts": [
				{"key": "current_price", "label": "Current Price", "value": 50.0, "numeric_value": 50.0},
			],
			"assumptions": {
				"revenue": [1000, 1070, 1135, 1190, 1235],
				"ebit_margin": [0.18, 0.185, 0.19, 0.192, 0.194],
				"tax_rate": [0.21, 0.21, 0.21, 0.21, 0.21],
				"depreciation": [42, 44, 46, 48, 50],
				"capex": [50, 52, 54, 56, 58],
				"change_in_nwc": [8, 9, 10, 10, 11],
				"wacc": 0.09,
				"terminal_growth": 0.025,
				"total_debt": 250,
				"cash": 120,
				"shares_outstanding": 100,
			},
			"assumption_reasons": [],
		}

		validation = validate_parameter_payload(payload)

		self.assertTrue(validation["is_valid"])
		self.assertEqual(validation["valuation_model_code"], "FCFF")
		self.assertEqual(validation["growth_stage"], "Drivers")
		self.assertIsInstance(validation["normalized_inputs"]["revenue"], list)

	def test_run_valuation_calculation_supports_fcfe_driver_inputs(self) -> None:
		payload = {
			"selected_model": "DCF",
			"selected_variant": None,
			"calculation_model": "FCFE",
			"parameter_reason": "Driver-based FCFE forecast.",
			"fetched_facts": [
				{"key": "current_price", "label": "Current Price", "value": 80.0, "numeric_value": 80.0},
			],
			"assumptions": {
				"revenue": [900, 960, 1015, 1060, 1100],
				"ebit_margin": [0.18, 0.182, 0.184, 0.185, 0.186],
				"tax_rate": [0.21, 0.21, 0.21, 0.21, 0.21],
				"depreciation": [30, 31, 32, 33, 34],
				"capex": [34, 35, 36, 37, 38],
				"change_in_nwc": [6, 7, 7, 8, 8],
				"net_borrowing": [3, 2, 1, 1, 0],
				"cost_of_equity": 0.095,
				"terminal_growth": 0.025,
				"shares_outstanding": 50,
			},
			"assumption_reasons": [],
		}

		result = run_valuation_calculation(payload)

		self.assertEqual(result["selected_model"], "FCFE")
		self.assertEqual(result["growth_stage"], "Drivers")
		self.assertGreater(result["fair_value_per_share"], 0)
		self.assertTrue(any(row["key"] == "revenue" for row in result["assumptions"]))


if __name__ == "__main__":
	unittest.main()
