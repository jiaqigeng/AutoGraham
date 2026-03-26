from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.subagents.valuation.model_selector import select_model


class ModelSelectorTests(unittest.TestCase):
	def test_select_model_uses_agent_executor_output_when_available(self) -> None:
		stock = SimpleNamespace(
			info={
				"shortName": "DividendCo",
				"sector": "Utilities",
				"industry": "Regulated Electric",
				"dividendYield": 0.03,
				"currentPrice": 100.0,
			}
		)
		fake_executor = SimpleNamespace(
			invoke=lambda payload: {
				"output": (
					'{"selected_model":"DDM","selected_variant":"Drivers",'
					'"preferred_calculation_model":"DDM","projection_years":5,'
					'"projection_years_reason":"Five years fits payout normalization.",'
					'"model_reason":"Stable dividend base.","confidence":0.8}'
				)
			}
		)

		with patch("agent.subagents.valuation.model_selector._build_agent_executor", return_value=fake_executor), patch(
			"agent.subagents.valuation.model_selector.invoke_text_prompt",
			return_value=None,
		):
			result = select_model(
				ticker="DIV",
				stock_info=stock,
				candidate_facts=[
					{"key": "dividend_per_share", "label": "Dividend Per Share", "value": 3.0, "numeric_value": 3.0},
					{"key": "payout_ratio", "label": "Observed Payout Ratio", "value": 0.55, "numeric_value": 0.55},
				],
			)

		self.assertEqual(result["selected_model"], "DDM")
		self.assertEqual(result["selected_variant"], "Drivers")
		self.assertEqual(result["preferred_calculation_model"], "DDM")
		self.assertEqual(result["projection_years"], 5)

	def test_select_model_falls_back_when_agent_choice_is_implausible(self) -> None:
		stock = SimpleNamespace(
			info={
				"shortName": "NoDividendCo",
				"sector": "Technology",
				"industry": "Software",
				"dividendYield": 0.0,
				"currentPrice": 50.0,
			}
		)
		fake_executor = SimpleNamespace(
			invoke=lambda payload: {
				"output": (
					'{"selected_model":"DDM","selected_variant":"Drivers",'
					'"preferred_calculation_model":"DDM","projection_years":11,'
					'"projection_years_reason":"Too long.",'
					'"model_reason":"Bad fit.","confidence":0.9}'
				)
			}
		)

		with patch("agent.subagents.valuation.model_selector._build_agent_executor", return_value=fake_executor), patch(
			"agent.subagents.valuation.model_selector.invoke_text_prompt",
			return_value=None,
		):
			result = select_model(
				ticker="NODIV",
				stock_info=stock,
				candidate_facts=[
					{"key": "starting_fcff", "label": "Starting FCFF", "value": 1000000.0, "numeric_value": 1000000.0},
					{"key": "dividend_per_share", "label": "Dividend Per Share", "value": 0.0, "numeric_value": 0.0},
				],
			)

		self.assertEqual(result["selected_model"], "DCF")
		self.assertEqual(result["selected_variant"], "Drivers")
		self.assertIn(result["preferred_calculation_model"], {"FCFF", "FCFE"})
		self.assertEqual(result["projection_years"], 5)

	def test_select_model_rejects_projection_years_other_than_five_or_ten(self) -> None:
		stock = SimpleNamespace(
			info={
				"shortName": "BuildoutCo",
				"sector": "Technology",
				"industry": "Infrastructure Software",
				"dividendYield": 0.0,
				"currentPrice": 90.0,
			}
		)
		fake_executor = SimpleNamespace(
			invoke=lambda payload: {
				"output": (
					'{"selected_model":"DCF","selected_variant":"Drivers",'
					'"preferred_calculation_model":"FCFF","projection_years":7,'
					'"projection_years_reason":"Seven years fits the story.",'
					'"model_reason":"Operating cash flow is the right frame.","confidence":0.8}'
				)
			}
		)

		with patch("agent.subagents.valuation.model_selector._build_agent_executor", return_value=fake_executor), patch(
			"agent.subagents.valuation.model_selector.invoke_text_prompt",
			return_value=None,
		):
			result = select_model(
				ticker="BLDT",
				stock_info=stock,
				candidate_facts=[
					{"key": "starting_fcff", "label": "Starting FCFF", "value": 1000000.0, "numeric_value": 1000000.0},
				],
			)

		self.assertEqual(result["selected_model"], "DCF")
		self.assertEqual(result["selected_variant"], "Drivers")
		self.assertEqual(result["projection_years"], 5)


if __name__ == "__main__":
	unittest.main()
