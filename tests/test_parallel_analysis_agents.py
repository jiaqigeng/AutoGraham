from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
	from agent.subagents.research.quantitative_agent import run_quantitative_analysis
except ModuleNotFoundError:  # pragma: no cover - depends on local interpreter setup.
	run_quantitative_analysis = None  # type: ignore[assignment]


@unittest.skipUnless(run_quantitative_analysis is not None, "parallel-analysis dependencies are not installed in this interpreter")
class ParallelAnalysisAgentTests(unittest.TestCase):
	def test_run_quantitative_analysis_returns_metrics_json(self) -> None:
		stock = SimpleNamespace(info={"shortName": "TestCo"})
		fact_rows = [
			{"metric_name": "revenue", "period": "2024-12-31", "value": 1000.0},
			{"metric_name": "revenue", "period": "2023-12-31", "value": 900.0},
			{"metric_name": "gross_profit", "period": "2024-12-31", "value": 450.0},
			{"metric_name": "gross_profit", "period": "2023-12-31", "value": 360.0},
			{"metric_name": "operating_income", "period": "2024-12-31", "value": 200.0},
			{"metric_name": "operating_income", "period": "2023-12-31", "value": 171.0},
			{"metric_name": "net_income", "period": "2024-12-31", "value": 150.0},
			{"metric_name": "net_income", "period": "2023-12-31", "value": 126.0},
			{"metric_name": "free_cash_flow", "period": "2024-12-31", "value": 180.0},
			{"metric_name": "free_cash_flow", "period": "2023-12-31", "value": 150.0},
			{"metric_name": "total_debt", "period": "2024-12-31", "value": 300.0},
			{"metric_name": "total_debt", "period": "2023-12-31", "value": 320.0},
			{"metric_name": "total_equity", "period": "2024-12-31", "value": 700.0},
			{"metric_name": "total_equity", "period": "2023-12-31", "value": 650.0},
			{"metric_name": "cash_and_equivalents", "period": "2024-12-31", "value": 120.0},
			{"metric_name": "cash_and_equivalents", "period": "2023-12-31", "value": 100.0},
		]

		with patch(
			"agent.subagents.research.quantitative_agent.build_company_snapshot",
			return_value={
				"company_name": "TestCo",
				"current_price": 100.0,
				"market_cap": 10_000.0,
				"starting_fcff": 180.0,
				"starting_fcfe": 170.0,
			},
		), patch("agent.subagents.research.quantitative_agent.build_source_links", return_value=[]), patch(
			"agent.subagents.research.quantitative_agent.get_sqlite_financial_facts",
			return_value=fact_rows,
		):
			artifact = run_quantitative_analysis("TST", stock)

		self.assertIn("metrics_json", artifact)
		self.assertIn("gross_margin", artifact["metrics_json"])
		self.assertIn("roic", artifact["metrics_json"])
		self.assertIn("debt_to_equity", artifact["metrics_json"])
		self.assertIn("free_cash_flow_growth", artifact["metrics_json"])
		self.assertAlmostEqual(artifact["metrics_json"]["gross_margin"][0]["value"], 0.45, places=6)
		self.assertAlmostEqual(artifact["metrics_json"]["debt_to_equity"][0]["value"], 300.0 / 700.0, places=6)
		self.assertAlmostEqual(artifact["metrics_json"]["free_cash_flow_growth"][0]["value"], 0.2, places=6)


if __name__ == "__main__":
	unittest.main()
