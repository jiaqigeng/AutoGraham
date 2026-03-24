from __future__ import annotations

import unittest
from unittest.mock import patch

try:
	import pandas as pd
	from agent.tools.finance_tools import (
		CompanyProfileData,
		IncomeStatementData,
		ValuationMetricsData,
		format_company_profile_text,
		get_cash_flow_health,
		get_company_profile_data,
		get_income_statement_data,
		get_valuation_metrics,
		get_valuation_metrics_data,
	)
	from data.market_data import StockData
except ModuleNotFoundError:  # pragma: no cover - depends on local interpreter setup.
	pd = None  # type: ignore[assignment]
	StockData = None  # type: ignore[assignment]
	CompanyProfileData = None  # type: ignore[assignment]
	IncomeStatementData = None  # type: ignore[assignment]
	ValuationMetricsData = None  # type: ignore[assignment]
	format_company_profile_text = None  # type: ignore[assignment]
	get_cash_flow_health = None  # type: ignore[assignment]
	get_company_profile_data = None  # type: ignore[assignment]
	get_income_statement_data = None  # type: ignore[assignment]
	get_valuation_metrics = None  # type: ignore[assignment]
	get_valuation_metrics_data = None  # type: ignore[assignment]


def _stock_data(*, info: dict[str, object] | None = None) -> StockData:
	assert StockData is not None
	assert pd is not None
	return StockData(
		info=dict(info or {}),
		quarterly_income_stmt=pd.DataFrame(),
		annual_cashflow=pd.DataFrame(),
		annual_balance_sheet=pd.DataFrame(),
		annual_income_stmt=pd.DataFrame(),
	)


@unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
class FinanceToolsTests(unittest.TestCase):
	def test_get_valuation_metrics_data_returns_structured_dataclass(self) -> None:
		stock_data = _stock_data(
			info={
				"quoteType": "EQUITY",
				"shortName": "Microsoft",
				"currentPrice": 412.34,
				"marketCap": 3_050_000_000_000,
				"trailingPE": 33.2,
				"forwardPE": 29.4,
				"trailingEps": 12.41,
				"dividendYield": 0.0072,
			}
		)

		with patch("agent.tools.finance_tools.get_cached_stock_data", return_value=stock_data):
			metrics = get_valuation_metrics_data(" msft ")

		self.assertIsInstance(metrics, ValuationMetricsData)
		self.assertEqual(metrics.ticker, "MSFT")
		self.assertAlmostEqual(metrics.current_price, 412.34, places=6)
		self.assertAlmostEqual(metrics.forward_pe, 29.4, places=6)
		self.assertAlmostEqual(metrics.dividend_yield or 0.0, 0.0072, places=6)

	def test_get_income_statement_data_returns_structured_dataclass(self) -> None:
		stock_data = _stock_data()
		expected_metrics = {
			"period": "Quarter Ended: Dec 31, 2025",
			"revenue": 1000.0,
			"gross_profit": 420.0,
			"operating_income": 190.0,
			"operating_expenses": 230.0,
			"net_profit": 140.0,
			"gross_margin": 0.42,
			"operating_margin": 0.19,
			"net_margin": 0.14,
		}

		with patch("agent.tools.finance_tools.get_cached_stock_data", return_value=stock_data), patch(
			"agent.tools.finance_tools.extract_latest_quarter_metrics",
			return_value=expected_metrics,
		):
			metrics = get_income_statement_data("nvda")

		self.assertIsInstance(metrics, IncomeStatementData)
		self.assertEqual(metrics.ticker, "NVDA")
		self.assertEqual(metrics.period, "Quarter Ended: Dec 31, 2025")
		self.assertAlmostEqual(metrics.gross_margin or 0.0, 0.42, places=6)

	def test_company_profile_data_preserves_full_summary_while_formatter_truncates(self) -> None:
		summary = "A" * 1400
		stock_data = _stock_data(
			info={
				"quoteType": "EQUITY",
				"longName": "Example Co",
				"sector": "Technology",
				"industry": "Software",
				"longBusinessSummary": summary,
			}
		)

		with patch("agent.tools.finance_tools.get_cached_stock_data", return_value=stock_data):
			profile = get_company_profile_data("exmp")

		self.assertIsInstance(profile, CompanyProfileData)
		self.assertEqual(profile.summary, summary)

		formatted = format_company_profile_text(profile)
		self.assertIn("Company Profile for EXMP", formatted)
		self.assertIn(f"Summary: {'A' * 1200}", formatted)
		self.assertNotIn(f"Summary: {'A' * 1201}", formatted)

	def test_tool_wrapper_keeps_agent_friendly_valuation_text(self) -> None:
		with patch(
			"agent.tools.finance_tools.get_valuation_metrics_data",
			return_value=ValuationMetricsData(
				ticker="AAPL",
				current_price=200.0,
				market_cap=3_000_000_000_000,
				trailing_pe=31.0,
				forward_pe=28.0,
				trailing_eps=6.45,
				dividend_yield=0.005,
			),
		):
			formatted = get_valuation_metrics("aapl")

		self.assertIn("Valuation Metrics for AAPL", formatted)
		self.assertIn("Current Price: $200.00", formatted)
		self.assertIn("Dividend Yield: 0.50%", formatted)

	def test_tool_wrapper_converts_structured_errors_to_data_unavailable_message(self) -> None:
		with patch("agent.tools.finance_tools.get_cash_flow_health_data", side_effect=ValueError("No cash flow data found.")):
			formatted = get_cash_flow_health(" tsla ")

		self.assertIn("DATA_UNAVAILABLE for TSLA", formatted)
		self.assertIn("No cash flow data found.", formatted)


if __name__ == "__main__":
	unittest.main()
