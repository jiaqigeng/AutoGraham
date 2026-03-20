from __future__ import annotations

import unittest

import pandas as pd

from agent.tools.calculator_tools import calculate_recommended_value
from agent.tools.validation_tools import extract_json_object


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


if __name__ == "__main__":
	unittest.main()
