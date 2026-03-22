from __future__ import annotations

import unittest

from ui_components.ai_report import render_ai_report


class AIReportRenderingTests(unittest.TestCase):
	def test_render_ai_report_uses_distinct_heading_levels_without_sources_or_header(self) -> None:
		html_output = render_ai_report(
			"## Ignored report",
			ticker="AAPL",
			company_name="Apple Inc.",
			valuation_pick={
				"model_name": "Free Cash Flow to Firm (FCFF)",
				"selected_model": "FCFF",
				"growth_stage": "Mature",
				"fair_value_per_share": 210.0,
				"current_price": 180.0,
				"margin_of_safety": 16.67,
				"assumptions": [
					{"key": "wacc", "label": "WACC", "value": 0.09, "reason": "Discount rate"},
					{"key": "cash", "label": "Cash", "value": 50_000_000_000, "reason": "Uses the latest balance-sheet cash balance. Extra detail that should not carry through."},
				],
			},
			model_selection={"model_reason": "Cash-flow profile fits FCFF."},
			parameter_payload={
				"parameter_reason": "Base-case operating assumptions.",
				"fetched_facts": [
					{"key": "cash", "value": 50_000_000_000},
				],
				"assumptions": {
					"wacc": 0.09,
					"cash": 50_000_000_000,
				},
				"assumption_reasons": [
					{"key": "wacc", "reason": "Reflects the base discount rate for the forecast period."},
					{"key": "cash", "reason": "Uses the latest balance-sheet cash balance. Extra detail that should not carry through."},
				],
			},
			explanation_markdown=(
				"# Apple Inc. Investment Research Report\n## Investment Summary\n### Outlook\n#### Key Drivers\nDemand remains resilient.\n\n"
				"## Financial Health\nNet cash remains solid and liquidity is strong.\n\n"
				"## 6. Bulls Say / Bears Say\n\n"
				"## Bulls Say\nServices growth and recurring revenue support durable margins.\n\n"
				"## Bears Say\nValuation still assumes stronger hardware replacement demand than the market may deliver.\n\n"
				"## Sources\nhttps://example.com/source-one\n\n"
				"| Metric | Value |\n| --- | --- |\n| Fair Value | $210 |\n| Margin of Safety | 16.67% |"
			),
			source_links=["https://example.com/apple"],
			confidence=0.82,
		)

		self.assertNotIn("ai-dashboard-header-title", html_output)
		self.assertIn("ai-research-section-card", html_output)
		self.assertGreaterEqual(html_output.count("ai-research-section-card"), 3)
		self.assertNotIn('<div class="ai-dashboard-panel-title">Apple Inc. Investment Research Report</div>', html_output)
		self.assertIn('<div class="ai-dashboard-panel-title">Investment Summary</div>', html_output)
		self.assertIn('<div class="ai-dashboard-panel-title">Outlook</div>', html_output)
		self.assertIn('<div class="ai-dashboard-panel-title">Key Drivers</div>', html_output)
		self.assertIn('<div class="ai-dashboard-panel-title">6. Bulls Say / Bears Say</div>', html_output)
		self.assertNotIn('<div class="ai-dashboard-panel-title">Financial Health</div>', html_output)
		self.assertNotIn('<div class="ai-dashboard-panel-title">Bulls Say</div>', html_output)
		self.assertNotIn('<div class="ai-dashboard-panel-title">Bears Say</div>', html_output)
		self.assertNotIn('<div class="ai-dashboard-panel-title">Sources</div>', html_output)
		self.assertNotIn("https://example.com/source-one", html_output)
		self.assertIn("<strong>Bulls Say.</strong>", html_output)
		self.assertIn("<strong>Bears Say.</strong>", html_output)
		self.assertNotIn("Valuation Snapshot", html_output)
		self.assertNotIn("ai-workflow-sources-label", html_output)
		self.assertNotIn("https://example.com/apple", html_output)
		self.assertNotIn("Confidence 82%", html_output)
		self.assertIn("ai-dashboard-metric-card is-positive", html_output)
		self.assertIn("ai-dashboard-detail-value ai-dashboard-detail-value-half", html_output)
		self.assertIn("Discount rate This is a forward-looking estimate rather than a directly reported figure", html_output)
		self.assertIn("Uses the latest balance-sheet cash balance.", html_output)
		self.assertNotIn("Extra detail that should not carry through", html_output)
		self.assertNotIn("Valuation Gap", html_output)
		self.assertNotIn("Status", html_output)
		self.assertNotIn("Formula Check", html_output)
		self.assertIn("Possible reasons include", html_output)


if __name__ == "__main__":
	unittest.main()
