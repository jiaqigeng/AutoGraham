from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from workflows.ai_valuation import run_ai_valuation


class AIWorkflowTests(unittest.TestCase):
	def test_ai_workflow_returns_research_valuation_and_explanation(self) -> None:
		stock = SimpleNamespace(info={"currentPrice": 100.0, "shortName": "TestCo"})
		with patch(
			"agent.orchestrator.run_macro_analysis",
			return_value={
				"analysis_agent": "macro",
				"report_markdown": "### Top-Down Setup\n- Supportive setup",
				"source_links": ["https://example.com/aapl"],
				"source_notes": [{"title": "Example", "url": "https://example.com/aapl"}],
				"confidence": 0.7,
			},
		), patch(
			"agent.orchestrator.run_qualitative_analysis",
			return_value={
				"analysis_agent": "qualitative",
				"report_markdown": "### Business Model\n- Strong business",
				"source_links": ["https://example.com/qual"],
				"source_notes": [{"title": "Qual", "url": "https://example.com/qual"}],
				"candidate_facts": [{"key": "company_type", "label": "Company Type", "value": "Operating company", "source": "Qualitative Agent"}],
				"confidence": 0.65,
			},
		), patch(
			"agent.orchestrator.run_quantitative_analysis",
			return_value={
				"analysis_agent": "quantitative",
				"report_markdown": "### Market Anchors\n- Current price 100",
				"source_links": ["https://example.com/quant"],
				"source_notes": [{"title": "Quant", "url": "https://example.com/quant"}],
				"candidate_facts": [{"key": "current_price", "label": "Current Price", "value": 100.0, "numeric_value": 100.0, "source": "Yahoo Finance"}],
				"confidence": 0.8,
			},
		), patch(
			"agent.orchestrator.select_model",
			return_value={
				"selected_model": "DCF",
				"selected_variant": "Drivers",
				"preferred_calculation_model": "FCFF",
				"projection_years": 5,
				"model_reason": "Best fit",
			},
		), patch(
			"agent.orchestrator.plan_parameters",
			return_value={
				"selected_model": "DCF",
				"selected_variant": "Drivers",
				"calculation_model": "FCFF",
				"fetched_facts": [{"key": "current_price", "label": "Current Price", "value": 100.0, "numeric_value": 100.0}],
				"assumptions": {"wacc": 0.09, "growth_rate": 0.08, "projection_years": 5, "terminal_growth": 0.03},
				"assumption_reasons": [{"key": "wacc", "reason": "Risk-adjusted discount rate."}],
				"parameter_reason": "Base-case assumptions.",
			},
		), patch(
			"agent.orchestrator.validate_parameter_payload",
			return_value={
				"is_valid": True,
				"errors": [],
				"normalized_payload": {},
				"normalized_inputs": {"wacc": 0.09},
				"valuation_model_code": "FCFF",
				"growth_stage": "Drivers",
			},
		), patch(
			"agent.orchestrator.run_valuation_calculation",
			return_value={
				"selected_model": "FCFF",
				"model_name": "Free Cash Flow to Firm (FCFF)",
				"growth_stage": "Drivers",
				"assumptions": [{"key": "wacc", "value": 0.09}],
				"fair_value_per_share": 120.0,
				"current_price": 100.0,
				"margin_of_safety": 16.67,
			},
		), patch("agent.orchestrator.write_report", return_value="## Bottom Line\nLooks attractive"):
			result = run_ai_valuation("AAPL", stock)

		self.assertIn("memo_markdown", result)
		self.assertEqual(result["ticker"], "AAPL")
		self.assertEqual(result["company_name"], "TestCo")
		self.assertIn("parallel_analyses", result)
		self.assertIn("macro", result["parallel_analyses"])
		self.assertEqual(result["model_selection"]["selected_model"], "DCF")
		self.assertEqual(result["valuation_pick"]["selected_model"], "FCFF")
		self.assertEqual(result["parameter_payload"]["calculation_model"], "FCFF")
		self.assertIn("Bottom Line", result["explanation_markdown"])


if __name__ == "__main__":
	unittest.main()
