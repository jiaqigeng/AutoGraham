from __future__ import annotations

import unittest

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - depends on local interpreter setup.
    pd = None

from valuation.common import default_valuation_inputs
from valuation.dcf import (
    AdvancedFCFEYear,
    AdvancedFCFFYear,
    SimpleDCFYear,
    calculate_fcfe_dcf_from_drivers,
    calculate_fcfe_dcf_simple,
    calculate_fcff_dcf_from_drivers,
    calculate_fcff_dcf_simple,
)


def _frame(values: dict[str, float]) -> pd.DataFrame:
    if pd is None:
        raise ModuleNotFoundError("pandas is required for statement-frame tests.")
    return pd.DataFrame({pd.Timestamp("2024-12-31"): values})


class DCFTests(unittest.TestCase):
    @unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
    def test_default_inputs_adds_after_tax_interest_to_fcff(self) -> None:
        info = {
            "currentPrice": 50.0,
            "marketCap": 5_000.0,
            "effectiveTaxRate": 0.25,
            "totalDebt": 800.0,
            "totalCash": 150.0,
        }
        defaults = default_valuation_inputs(
            info,
            annual_cashflow=_frame(
                {
                    "Free Cash Flow": 100.0,
                    "Operating Cash Flow": 150.0,
                    "Capital Expenditure": -50.0,
                    "Net Issuance Payments Of Debt": 20.0,
                }
            ),
            annual_balance_sheet=_frame(
                {
                    "Total Debt": 800.0,
                    "Cash And Cash Equivalents": 150.0,
                    "Stockholders Equity": 2_000.0,
                }
            ),
            annual_income_stmt=_frame(
                {
                    "Interest Expense": 40.0,
                    "Pretax Income": 200.0,
                    "Tax Provision": 50.0,
                }
            ),
        )

        self.assertEqual(defaults["starting_fcff"], 130.0)
        self.assertEqual(defaults["starting_fcfe"], 120.0)

    @unittest.skipUnless(pd is not None, "pandas is not installed in this interpreter")
    def test_default_inputs_convert_net_debt_to_gross_debt_when_cash_is_known(self) -> None:
        info = {
            "currentPrice": 20.0,
            "marketCap": 2_000.0,
            "effectiveTaxRate": 0.21,
            "totalCash": 300.0,
        }
        defaults = default_valuation_inputs(
            info,
            annual_cashflow=_frame({"Free Cash Flow": 80.0, "Operating Cash Flow": 100.0, "Capital Expenditure": -20.0}),
            annual_balance_sheet=_frame({"Net Debt": 500.0, "Cash And Cash Equivalents": 300.0, "Stockholders Equity": 1_200.0}),
            annual_income_stmt=_frame({"Interest Expense": 25.0, "Pretax Income": 100.0, "Tax Provision": 21.0}),
        )

        self.assertEqual(defaults["cash"], 300.0)
        self.assertEqual(defaults["total_debt"], 800.0)

    def test_fcff_dcf_simple_matches_manual_bridge(self) -> None:
        result = calculate_fcff_dcf_simple(
            current_fcff=100.0,
            growth_rate=0.06,
            projection_years=5,
            wacc=0.09,
            terminal_growth=0.03,
            total_debt=200.0,
            cash=50.0,
            shares_outstanding=100.0,
        )

        cash_flow = 100.0
        pv_forecast = 0.0
        for year in range(1, 6):
            cash_flow *= 1.06
            pv_forecast += cash_flow / (1.09**year)

        terminal_value = cash_flow * 1.03 / (0.09 - 0.03)
        pv_terminal = terminal_value / (1.09**5)
        enterprise_value = pv_forecast + pv_terminal
        equity_value = enterprise_value - 200.0 + 50.0

        self.assertAlmostEqual(result.pv_forecast_cash_flows, pv_forecast, places=6)
        self.assertAlmostEqual(result.pv_terminal_value, pv_terminal, places=6)
        self.assertAlmostEqual(result.enterprise_value, enterprise_value, places=6)
        self.assertAlmostEqual(result.equity_value, equity_value, places=6)
        self.assertAlmostEqual(result.fair_value_per_share, equity_value / 100.0, places=6)
        self.assertEqual(len(result.schedule), 5)
        self.assertIsInstance(result.schedule[0], SimpleDCFYear)

    def test_fcfe_dcf_simple_matches_manual_bridge(self) -> None:
        result = calculate_fcfe_dcf_simple(
            current_fcfe=80.0,
            growth_rate=0.05,
            projection_years=5,
            cost_of_equity=0.10,
            terminal_growth=0.03,
            shares_outstanding=100.0,
        )

        cash_flow = 80.0
        pv_forecast = 0.0
        for year in range(1, 6):
            cash_flow *= 1.05
            pv_forecast += cash_flow / (1.10**year)

        terminal_value = cash_flow * 1.03 / (0.10 - 0.03)
        pv_terminal = terminal_value / (1.10**5)
        equity_value = pv_forecast + pv_terminal

        self.assertAlmostEqual(result.pv_forecast_cash_flows, pv_forecast, places=6)
        self.assertAlmostEqual(result.pv_terminal_value, pv_terminal, places=6)
        self.assertAlmostEqual(result.equity_value, equity_value, places=6)
        self.assertAlmostEqual(result.fair_value_per_share, equity_value / 100.0, places=6)
        self.assertEqual(len(result.schedule), 5)
        self.assertIsInstance(result.schedule[0], SimpleDCFYear)

    def test_fcff_dcf_from_drivers_uses_cumulative_discounting(self) -> None:
        result = calculate_fcff_dcf_from_drivers(
            revenue=[1000, 1080, 1160, 1240, 1320],
            ebit_margin=[0.18, 0.185, 0.19, 0.195, 0.20],
            tax_rate=[0.21, 0.21, 0.21, 0.21, 0.21],
            depreciation=[40, 42, 44, 46, 48],
            capex=[55, 58, 60, 63, 66],
            change_in_nwc=[10, 11, 12, 13, 14],
            wacc=0.09,
            terminal_growth=0.03,
            total_debt=250.0,
            cash=90.0,
            shares_outstanding=100.0,
        )

        expected_fcff: list[float] = []
        for year in range(5):
            ebit = [1000, 1080, 1160, 1240, 1320][year] * [0.18, 0.185, 0.19, 0.195, 0.20][year]
            nopat = ebit * (1.0 - 0.21)
            fcff = nopat + [40, 42, 44, 46, 48][year] - [55, 58, 60, 63, 66][year] - [10, 11, 12, 13, 14][year]
            expected_fcff.append(fcff)

        cumulative_factor = 1.0
        pv_forecast = 0.0
        cumulative_factors: list[float] = []
        for fcff in expected_fcff:
            cumulative_factor *= 1.0 + 0.09
            cumulative_factors.append(cumulative_factor)
            pv_forecast += fcff / cumulative_factor

        terminal_wacc = 0.09
        terminal_value = expected_fcff[-1] * 1.03 / (terminal_wacc - 0.03)
        pv_terminal = terminal_value / cumulative_factors[-1]
        enterprise_value = pv_forecast + pv_terminal
        equity_value = enterprise_value - 250.0 + 90.0

        self.assertAlmostEqual(result.pv_forecast_cash_flows, pv_forecast, places=6)
        self.assertAlmostEqual(result.terminal_wacc, terminal_wacc, places=6)
        self.assertIsNone(result.terminal_cost_of_equity)
        self.assertAlmostEqual(result.pv_terminal_value, pv_terminal, places=6)
        self.assertAlmostEqual(result.enterprise_value, enterprise_value, places=6)
        self.assertAlmostEqual(result.equity_value, equity_value, places=6)
        self.assertEqual(len(result.schedule), 5)
        self.assertIsInstance(result.schedule[0], AdvancedFCFFYear)
        self.assertAlmostEqual(result.schedule[1].cumulative_discount_factor, cumulative_factors[1], places=6)
        self.assertAlmostEqual(result.schedule[0].wacc, 0.09, places=6)
        self.assertNotIn("risk_free_rate", result.schedule[0].__dataclass_fields__)
        self.assertNotIn("cost_of_debt", result.schedule[0].__dataclass_fields__)

    def test_fcfe_dcf_from_drivers_uses_cumulative_discounting(self) -> None:
        result = calculate_fcfe_dcf_from_drivers(
            revenue=[1000, 1080, 1160, 1240, 1320],
            ebit_margin=[0.16, 0.163, 0.166, 0.168, 0.17],
            tax_rate=[0.21, 0.21, 0.21, 0.21, 0.21],
            depreciation=[40, 42, 44, 46, 48],
            capex=[55, 58, 60, 63, 66],
            change_in_nwc=[10, 11, 12, 13, 14],
            net_borrowing=[5, 4, 3, 2, 1],
            cost_of_equity=0.095,
            terminal_growth=0.03,
            shares_outstanding=100.0,
        )

        expected_fcfe: list[float] = []
        for year in range(5):
            ebit = [1000, 1080, 1160, 1240, 1320][year] * [0.16, 0.163, 0.166, 0.168, 0.17][year]
            nopat = ebit * (1.0 - 0.21)
            fcfe = nopat + [40, 42, 44, 46, 48][year] - [55, 58, 60, 63, 66][year] - [10, 11, 12, 13, 14][year] + [5, 4, 3, 2, 1][year]
            expected_fcfe.append(fcfe)

        cumulative_factor = 1.0
        pv_forecast = 0.0
        cumulative_factors: list[float] = []
        for fcfe in expected_fcfe:
            cumulative_factor *= 1.0 + 0.095
            cumulative_factors.append(cumulative_factor)
            pv_forecast += fcfe / cumulative_factor

        terminal_cost_of_equity = 0.095
        terminal_value = expected_fcfe[-1] * 1.03 / (terminal_cost_of_equity - 0.03)
        pv_terminal = terminal_value / cumulative_factors[-1]
        equity_value = pv_forecast + pv_terminal

        self.assertAlmostEqual(result.pv_forecast_cash_flows, pv_forecast, places=6)
        self.assertAlmostEqual(result.terminal_cost_of_equity, terminal_cost_of_equity, places=6)
        self.assertAlmostEqual(result.pv_terminal_value, pv_terminal, places=6)
        self.assertAlmostEqual(result.equity_value, equity_value, places=6)
        self.assertAlmostEqual(result.fair_value_per_share, equity_value / 100.0, places=6)
        self.assertEqual(len(result.schedule), 5)
        self.assertIsInstance(result.schedule[0], AdvancedFCFEYear)
        self.assertAlmostEqual(result.schedule[2].cumulative_discount_factor, cumulative_factors[2], places=6)
        self.assertNotIn("net_income_margin", result.schedule[0].__dataclass_fields__)
        self.assertNotIn("risk_free_rate", result.schedule[0].__dataclass_fields__)

    def test_fcff_driver_validation_rejects_wacc_below_terminal_growth(self) -> None:
        with self.assertRaisesRegex(ValueError, "wacc"):
            calculate_fcff_dcf_from_drivers(
                revenue=[1000],
                ebit_margin=[0.18],
                tax_rate=[0.21],
                depreciation=[40],
                capex=[55],
                change_in_nwc=[10],
                wacc=0.02,
                terminal_growth=0.03,
                total_debt=250.0,
                cash=90.0,
                shares_outstanding=100.0,
            )

    def test_fcfe_simple_requires_positive_projection_years(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_years"):
            calculate_fcfe_dcf_simple(
                current_fcfe=80.0,
                growth_rate=0.05,
                projection_years=0,
                cost_of_equity=0.10,
                terminal_growth=0.03,
                shares_outstanding=100.0,
            )


if __name__ == "__main__":
    unittest.main()
