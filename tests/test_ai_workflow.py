from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from workflows.ai_valuation import run_ai_valuation


class AIWorkflowTests(unittest.TestCase):
	def test_ai_workflow_returns_research_valuation_and_explanation(self) -> None:
		stock = SimpleNamespace(info={"currentPrice": 100.0, "shortName": "TestCo"})
		with patch(
			"agent.supervisor.research_company",
			return_value={
				"report_markdown": "## Business Strategy & Outlook\nStrong business",
				"source_links": ["https://example.com/aapl"],
				"source_notes": [{"title": "Example", "url": "https://example.com/aapl"}],
				"confidence": 0.7,
			},
		), patch(
			"agent.supervisor.extract_candidate_facts",
			return_value=[{"key": "current_price", "label": "Current Price", "value": 100.0, "numeric_value": 100.0, "source": "Yahoo Finance"}],
		), patch(
			"agent.supervisor.select_model",
			return_value={
				"selected_model": "DCF",
				"selected_variant": None,
				"preferred_calculation_model": "FCFF",
				"model_reason": "Best fit",
			},
		), patch(
			"agent.supervisor.estimate_parameters",
			return_value={
				"selected_model": "DCF",
				"selected_variant": None,
				"calculation_model": "FCFF",
				"fetched_facts": [{"key": "current_price", "label": "Current Price", "value": 100.0, "numeric_value": 100.0}],
				"assumptions": {"wacc": 0.09, "growth_rate": 0.08, "projection_years": 5, "terminal_growth": 0.03},
				"assumption_reasons": [{"key": "wacc", "reason": "Risk-adjusted discount rate."}],
				"parameter_reason": "Base-case assumptions.",
			},
		), patch(
			"agent.supervisor.validate_parameter_payload",
			return_value={
				"is_valid": True,
				"errors": [],
				"normalized_payload": {},
				"normalized_inputs": {"wacc": 0.09},
				"valuation_model_code": "FCFF",
				"growth_stage": None,
			},
		), patch(
			"agent.supervisor.run_valuation_calculation",
			return_value={
				"selected_model": "FCFF",
				"model_name": "Free Cash Flow to Firm (FCFF)",
				"growth_stage": None,
				"assumptions": [{"key": "wacc", "value": 0.09}],
				"fair_value_per_share": 120.0,
				"current_price": 100.0,
				"margin_of_safety": 16.67,
			},
		), patch("agent.supervisor.explain_valuation", return_value="## Bottom Line\nLooks attractive"):
			result = run_ai_valuation("AAPL", stock)

		self.assertIn("memo_markdown", result)
		self.assertEqual(result["ticker"], "AAPL")
		self.assertEqual(result["company_name"], "TestCo")
		self.assertEqual(result["model_selection"]["selected_model"], "DCF")
		self.assertEqual(result["valuation_pick"]["selected_model"], "FCFF")
		self.assertEqual(result["parameter_payload"]["calculation_model"], "FCFF")
		self.assertIn("Bottom Line", result["explanation_markdown"])


if __name__ == "__main__":
	unittest.main()
