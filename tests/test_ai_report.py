from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "ui_components" / "ai_report.py"
MODULE_SPEC = importlib.util.spec_from_file_location("ai_report_module", MODULE_PATH)
AI_REPORT_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(AI_REPORT_MODULE)
build_ai_report_sections = AI_REPORT_MODULE.build_ai_report_sections


class AIReportRenderingTests(unittest.TestCase):
	def test_build_ai_report_sections_returns_plain_markdown_sections(self) -> None:
		sections = build_ai_report_sections(
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
				"schedule": [
					{"year": 1, "revenue": 101_000_000_000, "wacc": 0.09},
					{"year": 2, "revenue": 105_000_000_000, "wacc": 0.09},
				],
				"assumptions": [
					{"key": "wacc", "label": "WACC", "value": 0.09, "reason": "Discount rate"},
					{"key": "cash", "label": "Cash", "value": 50_000_000_000, "reason": "Uses the latest balance-sheet cash balance. Extra detail that should not carry through."},
					{"key": "revenue", "label": "Revenue Forecast", "value": [100_000_000_000, 105_000_000_000], "reason": "Projected revenue path."},
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
				"# Apple Inc. Investment Research Report\n\n"
				"## Investment Summary\n\n"
				"Demand remains resilient.\n\n"
				"## Risk & Uncertainty\n\n"
				"Execution remains the main risk."
			),
			source_links=["https://example.com/apple", "https://example.com/apple"],
			confidence=0.82,
		)

		combined = "\n".join(sections.values())
		self.assertNotIn("<div", combined)
		self.assertNotIn("<section", combined)
		self.assertIn("# Apple Inc. Investment Research Report", sections["report_markdown"])
		self.assertIn("- **Company:** Apple Inc.", sections["overview_markdown"])
		self.assertIn("- **Model:** Free Cash Flow to Firm (FCFF)", sections["overview_markdown"])
		self.assertIn("- **Confidence:** 82.00%", sections["overview_markdown"])
		self.assertIn("| Assumption | Value | Type | Reason |", sections["assumptions_markdown"])
		self.assertIn("| WACC | 9.00% | Estimated | Discount rate |", sections["assumptions_markdown"])
		self.assertIn("| Cash | $50.00B | Direct data | Uses the latest balance-sheet cash balance. |", sections["assumptions_markdown"])
		self.assertIn("## Forecast Paths", sections["assumptions_markdown"])
		self.assertIn("| 1 | $100.00B |", sections["assumptions_markdown"])
		self.assertIn("The model suggests the shares trade below estimated fair value.", sections["comparison_markdown"])
		self.assertIn("- https://example.com/apple", sections["sources_markdown"])
		self.assertEqual(sections["sources_markdown"].count("https://example.com/apple"), 1)
		self.assertIn("| Year | Revenue | Wacc |", sections["schedule_markdown"])


if __name__ == "__main__":
	unittest.main()
