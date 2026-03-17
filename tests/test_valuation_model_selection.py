from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from agent.llm_service import recommend_valuation_model


def _frame(values: dict[str, float]) -> pd.DataFrame:
	return pd.DataFrame({pd.Timestamp("2024-12-31"): values})


def _stock(info: dict[str, float | str], cashflow: dict[str, float], balance: dict[str, float], income: dict[str, float]) -> SimpleNamespace:
	return SimpleNamespace(
		info=info,
		annual_cashflow=_frame(cashflow),
		annual_balance_sheet=_frame(balance),
		annual_income_stmt=_frame(income),
	)


class _FakeResponse:
	def __init__(self, content: str) -> None:
		self.content = content


class _FakeLLM:
	def __init__(self, responses: list[str]) -> None:
		self._responses = list(responses)
		self.prompts: list[str] = []

	def invoke(self, prompt: str) -> _FakeResponse:
		self.prompts.append(prompt)
		if not self._responses:
			raise AssertionError("No fake LLM responses left.")
		return _FakeResponse(self._responses.pop(0))


class ValuationModelSelectionTests(unittest.TestCase):
	def test_financial_dividend_payer_retries_until_ddm(self) -> None:
		stock = _stock(
			info={
				"currentPrice": 40.0,
				"marketCap": 40_000_000_000.0,
				"sector": "Financial Services",
				"industry": "Banks - Diversified",
				"dividendRate": 2.0,
				"dividendYield": 0.05,
				"payoutRatio": 0.45,
				"returnOnEquity": 0.13,
				"beta": 1.0,
				"bookValue": 28.0,
			},
			cashflow={
				"Free Cash Flow": 4_000_000_000.0,
				"Operating Cash Flow": 5_000_000_000.0,
				"Capital Expenditure": -1_000_000_000.0,
			},
			balance={
				"Total Debt": 15_000_000_000.0,
				"Cash And Cash Equivalents": 10_000_000_000.0,
				"Stockholders Equity": 28_000_000_000.0,
			},
			income={
				"Interest Expense": 800_000_000.0,
				"Pretax Income": 9_000_000_000.0,
				"Tax Provision": 1_800_000_000.0,
			},
		)

		fake_llm = _FakeLLM(
			[
				'{"selected_model":"FCFF","growth_stage":"Two-Stage","model_reason":"wrong first pass"}',
				'{"selected_model":"DDM","growth_stage":"H-Model","model_reason":"Financial dividend payer with distributable earnings."}',
				'{"parameter_reason":"Use an equity-return framework with a short fade into stable payout growth.","assumptions":{"required_return":0.10,"short_term_growth":0.05,"stable_growth":0.03,"half_life_years":3},"assumption_reasons":[{"key":"required_return","reason":"Equity holders set the hurdle rate."},{"key":"short_term_growth","reason":"Near-term growth can exceed the mature rate before fading."},{"key":"stable_growth","reason":"Mature dividend growth should stay modest."},{"key":"half_life_years","reason":"A short fade period fits a mature bank."}]}',
			]
		)
		with patch("agent.llm_service._build_chat_model", return_value=fake_llm):
			result = recommend_valuation_model("JPM", stock)

		self.assertEqual(result["selected_model"], "DDM")
		self.assertEqual(len(fake_llm.prompts), 3)
		self.assertIn("Banks, insurers, asset managers", fake_llm.prompts[0])
		self.assertIn("did not fit the company/model guidance", fake_llm.prompts[1])

	def test_financial_non_dividend_name_prefers_rim(self) -> None:
		stock = _stock(
			info={
				"currentPrice": 35.0,
				"marketCap": 7_000_000_000.0,
				"sector": "Financial Services",
				"industry": "Insurance - Specialty",
				"dividendRate": 0.0,
				"dividendYield": 0.0,
				"payoutRatio": 0.0,
				"returnOnEquity": 0.11,
				"beta": 0.95,
				"bookValue": 24.0,
			},
			cashflow={
				"Free Cash Flow": 500_000_000.0,
				"Operating Cash Flow": 650_000_000.0,
				"Capital Expenditure": -150_000_000.0,
			},
			balance={
				"Total Debt": 1_000_000_000.0,
				"Cash And Cash Equivalents": 800_000_000.0,
				"Stockholders Equity": 4_500_000_000.0,
			},
			income={
				"Interest Expense": 80_000_000.0,
				"Pretax Income": 700_000_000.0,
				"Tax Provision": 147_000_000.0,
			},
		)

		fake_llm = _FakeLLM(
			[
				'{"selected_model":"RIM","growth_stage":null,"model_reason":"Book value and ROE matter more than dividends here."}',
				'{"parameter_reason":"Residual income fits a non-dividend financial better than FCFF.","assumptions":{"cost_of_equity":0.10,"projection_years":5,"terminal_growth":0.025},"assumption_reasons":[{"key":"cost_of_equity","reason":"Residual income is discounted at the equity hurdle rate."},{"key":"projection_years","reason":"A medium horizon is appropriate."},{"key":"terminal_growth","reason":"Terminal growth stays conservative."}]}',
			]
		)
		with patch("agent.llm_service._build_chat_model", return_value=fake_llm):
			result = recommend_valuation_model("ACGL", stock)

		self.assertEqual(result["selected_model"], "RIM")
		self.assertEqual(len(fake_llm.prompts), 2)

	def test_tech_platform_prefers_fcff(self) -> None:
		stock = _stock(
			info={
				"currentPrice": 180.0,
				"marketCap": 2_000_000_000_000.0,
				"sector": "Communication Services",
				"industry": "Internet Content & Information",
				"dividendRate": 0.0,
				"dividendYield": 0.0,
				"payoutRatio": 0.0,
				"revenueGrowth": 0.12,
				"earningsGrowth": 0.14,
				"returnOnEquity": 0.28,
				"beta": 1.05,
				"bookValue": 28.0,
			},
			cashflow={
				"Free Cash Flow": 90_000_000_000.0,
				"Operating Cash Flow": 110_000_000_000.0,
				"Capital Expenditure": -20_000_000_000.0,
			},
			balance={
				"Total Debt": 25_000_000_000.0,
				"Cash And Cash Equivalents": 100_000_000_000.0,
				"Stockholders Equity": 300_000_000_000.0,
			},
			income={
				"Interest Expense": 1_500_000_000.0,
				"Pretax Income": 120_000_000_000.0,
				"Tax Provision": 20_000_000_000.0,
			},
		)

		fake_llm = _FakeLLM(
			[
				'{"selected_model":"FCFF","growth_stage":"Three-Stage (Multi-stage decay)","model_reason":"Operating cash flow before financing is the cleanest lens for a platform business."}',
				'{"parameter_reason":"A multi-stage FCFF model fits a growth platform with durable margins and strong reinvestment economics.","assumptions":{"wacc":0.09,"high_growth":0.11,"high_growth_years":5,"transition_years":4,"terminal_growth":0.03},"assumption_reasons":[{"key":"wacc","reason":"Enterprise value should be discounted at WACC."},{"key":"high_growth","reason":"The platform still has above-mature growth."},{"key":"high_growth_years","reason":"The competitive moat supports a longer explicit period."},{"key":"transition_years","reason":"Growth should fade gradually."},{"key":"terminal_growth","reason":"Terminal growth must stay below WACC."}]}',
			]
		)
		with patch("agent.llm_service._build_chat_model", return_value=fake_llm):
			result = recommend_valuation_model("GOOGL", stock)

		self.assertEqual(result["selected_model"], "FCFF")
		self.assertEqual(result["growth_stage"], "Three-Stage (Multi-stage decay)")


if __name__ == "__main__":
	unittest.main()
