from __future__ import annotations

import unittest

try:
	import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on local interpreter setup.
	pd = None  # type: ignore[assignment]

from data.financial_statements import (
	build_income_waterfall_figure,
	extract_latest_quarter_metrics,
	format_period_label,
	get_display_period_columns,
)
from data.normalization import format_percent


class PercentFormattingTests(unittest.TestCase):
	def test_format_percent_preserves_decimal_fraction_inputs(self) -> None:
		self.assertEqual(format_percent(0.38), "38.00%")

	def test_format_percent_accepts_whole_percent_inputs(self) -> None:
		self.assertEqual(format_percent(38), "38.00%")

	def test_format_percent_returns_na_for_missing_or_invalid_values(self) -> None:
		self.assertEqual(format_percent(None), "N/A")
		self.assertEqual(format_percent("N/A"), "N/A")


class QuarterlyMetricsTests(unittest.TestCase):
	@unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
	def test_extract_latest_quarter_metrics_reports_all_margins(self) -> None:
		frame = pd.DataFrame(
			{
				pd.Timestamp("2024-12-31"): {
					"Revenue": 1000.0,
					"Cost of Revenue": 600.0,
					"Operating Expenses": 220.0,
					"Net Income": 120.0,
				}
			}
		)

		metrics = extract_latest_quarter_metrics(frame)

		self.assertEqual(metrics["period"], "Quarter Ended: Dec 31, 2024")
		self.assertAlmostEqual(metrics["gross_profit"], 400.0, places=6)
		self.assertAlmostEqual(metrics["operating_income"], 180.0, places=6)
		self.assertAlmostEqual(metrics["gross_margin"], 0.40, places=6)
		self.assertAlmostEqual(metrics["operating_margin"], 0.18, places=6)
		self.assertAlmostEqual(metrics["net_margin"], 0.12, places=6)

	@unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
	def test_format_period_label_supports_annual_labels(self) -> None:
		self.assertEqual(format_period_label(pd.Timestamp("2024-12-31"), period_type="Annual"), "Year Ended: Dec 31, 2024")

	@unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
	def test_get_display_period_columns_limits_quarters_to_latest_four(self) -> None:
		frame = pd.DataFrame(
			columns=[
				pd.Timestamp("2025-12-31"),
				pd.Timestamp("2025-09-30"),
				pd.Timestamp("2025-06-30"),
				pd.Timestamp("2025-03-31"),
				pd.Timestamp("2024-12-31"),
			]
		)

		columns = get_display_period_columns(frame, period_type="Quarterly", limit=4)

		self.assertEqual(len(columns), 4)
		self.assertEqual(columns[0], pd.Timestamp("2025-12-31"))
		self.assertEqual(columns[-1], pd.Timestamp("2025-03-31"))

	@unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
	def test_get_display_period_columns_keeps_only_december_31_for_annual(self) -> None:
		frame = pd.DataFrame(
			columns=[
				pd.Timestamp("2025-12-31"),
				pd.Timestamp("2025-09-30"),
				pd.Timestamp("2024-12-31"),
				pd.Timestamp("2024-06-30"),
			]
		)

		columns = get_display_period_columns(frame, period_type="Annual")

		self.assertEqual(columns, [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31")])

	@unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
	def test_get_display_period_columns_falls_back_to_reported_annual_periods_when_december_31_missing(self) -> None:
		frame = pd.DataFrame(
			columns=[
				pd.Timestamp("2025-09-30"),
				pd.Timestamp("2024-09-30"),
				pd.Timestamp("2023-09-30"),
				pd.Timestamp("2022-09-30"),
				pd.Timestamp("2021-09-30"),
			]
		)

		columns = get_display_period_columns(frame, period_type="Annual", limit=4)

		self.assertEqual(columns, [
			pd.Timestamp("2025-09-30"),
			pd.Timestamp("2024-09-30"),
			pd.Timestamp("2023-09-30"),
			pd.Timestamp("2022-09-30"),
		])

	def test_build_income_waterfall_annual_omits_qoq_annotations(self) -> None:
		frame = pd.DataFrame(
			{
				pd.Timestamp("2024-12-31"): {
					"Revenue": 1_000_000_000.0,
					"Cost of Revenue": 600_000_000.0,
					"Operating Expenses": 220_000_000.0,
					"Net Income": 120_000_000.0,
				},
				pd.Timestamp("2023-12-31"): {
					"Revenue": 800_000_000.0,
					"Cost of Revenue": 500_000_000.0,
					"Operating Expenses": 190_000_000.0,
					"Net Income": 90_000_000.0,
				},
			}
		)

		figure, labels = build_income_waterfall_figure(frame, selected_column=pd.Timestamp("2024-12-31"), period_type="Annual")
		text_values = [text for text in figure.data[0].text if text]

		self.assertEqual(labels[0], "Year Ended: Dec 31, 2024")
		self.assertTrue(any("YoY:" in text for text in text_values))
		self.assertTrue(all("QoQ:" not in text for text in text_values))

	def test_get_display_period_columns_limits_annual_results_to_latest_four(self) -> None:
		frame = pd.DataFrame(
			columns=[
				pd.Timestamp("2025-12-31"),
				pd.Timestamp("2024-12-31"),
				pd.Timestamp("2023-12-31"),
				pd.Timestamp("2022-12-31"),
				pd.Timestamp("2021-12-31"),
			]
		)

		columns = get_display_period_columns(frame, period_type="Annual", limit=4)

		self.assertEqual(columns, [
			pd.Timestamp("2025-12-31"),
			pd.Timestamp("2024-12-31"),
			pd.Timestamp("2023-12-31"),
			pd.Timestamp("2022-12-31"),
		])


if __name__ == "__main__":
	unittest.main()
