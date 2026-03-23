from __future__ import annotations

import unittest

from agent.prompts.model_selection_prompts import build_model_selection_prompt
from agent.prompts.parameter_prompts import build_dcf_parameter_prompt, build_parameter_prompt
from agent.prompts.research_prompts import build_research_request, build_research_system_prompt


class PromptTests(unittest.TestCase):
	def test_model_selection_prompt_includes_requested_guidance_and_output_contract(self) -> None:
		prompt = build_model_selection_prompt(
			ticker="AAPL",
			company_name="Apple Inc.",
			candidate_facts=[
				{"label": "Dividend Per Share", "value": 0.96, "source": "Yahoo Finance"},
				{"label": "Book Value Per Share", "value": 4.2, "source": "Yahoo Finance"},
			],
			analysis_focus="Be conservative about dividend durability.",
		)

		self.assertIn("You are the valuation model selection specialist for AutoGraham.", prompt)
		self.assertIn("Available variants for reasoning:", prompt)
		self.assertIn('- DCF: set "selected_variant" to null', prompt)
		self.assertIn('"selected_variant" must be null for DCF and RIM.', prompt)
		self.assertIn('"required_parameters_next"', prompt)
		self.assertIn("Do not output markdown.", prompt)
		self.assertIn("Additional analysis focus: Be conservative about dividend durability.", prompt)

	def test_research_system_prompt_includes_structured_json_contract(self) -> None:
		prompt = build_research_system_prompt("MSFT", "Microsoft Corporation")

		self.assertIn("You are the Broad Valuation Researcher for AutoGraham.", prompt)
		self.assertIn("AutoGraham supports only these valuation models:", prompt)
		self.assertIn('"model_plausibility"', prompt)
		self.assertIn('"candidate_facts"', prompt)
		self.assertIn('"overall_research_confidence"', prompt)
		self.assertIn("Return output in raw JSON only.", prompt)

	def test_research_request_includes_company_hint_and_focus(self) -> None:
		prompt = build_research_request(
			target_ticker="MSFT",
			company_name="Microsoft Corporation",
			analysis_focus="Pay extra attention to capital return and margin targets.",
		)

		self.assertIn("company_name_hint: Microsoft Corporation", prompt)
		self.assertIn("ticker: MSFT", prompt)
		self.assertIn("follow the required JSON schema exactly", prompt)
		self.assertIn("Pay extra attention to capital return and margin targets.", prompt)

	def test_dcf_parameter_prompt_includes_yearly_fcff_contract(self) -> None:
		prompt = build_dcf_parameter_prompt(
			ticker="AAPL",
			selected_variant=None,
			candidate_facts=[
				{"label": "Current Price", "value": 100.0, "source": "Yahoo Finance"},
				{"label": "Starting FCFF", "value": 25000000000, "source": "Cash flow statement"},
			],
			calculation_model="FCFF",
			analysis_focus="Stay conservative on terminal assumptions.",
		)

		self.assertIn("You are the DCF parameter estimation specialist for AutoGraham.", prompt)
		self.assertIn("Do NOT evaluate whether FCFF DCF is appropriate.", prompt)
		self.assertIn("Try to look for relevant info and consensus through public and free online sources", prompt)
		self.assertIn("Estimate only `projection_years` and the exact inputs required by the Python function.", prompt)
		self.assertIn("Pay special attention to whether the company is still in a buildout, scaling, restructuring, or transition phase.", prompt)
		self.assertIn("Do not estimate any additional model inputs beyond the fields listed above.", prompt)
		self.assertIn("Forecast revenue year by year from the latest actual revenue base.", prompt)
		self.assertIn("Do not add a separate `growth_rates` field.", prompt)
		self.assertIn("Estimate `wacc` directly as one scalar discount rate", prompt)
		self.assertIn('"projection_years": 0', prompt)
		self.assertIn('"assumption_notes": {', prompt)
		self.assertIn('"wacc": 0.0', prompt)
		self.assertIn('"model_warnings": ["string"]', prompt)
		self.assertIn("Target company:\nAAPL", prompt)
		self.assertIn("Additional analysis focus: Stay conservative on terminal assumptions.", prompt)

	def test_dcf_parameter_prompt_supports_fcfe_yearly_contract(self) -> None:
		prompt = build_dcf_parameter_prompt(
			ticker="META",
			selected_variant=None,
			candidate_facts=[
				{"label": "Revenue", "value": 100000000000, "source": "Income statement"},
				{"label": "Net Borrowing", "value": 0, "source": "Cash flow statement"},
			],
			calculation_model="FCFE",
			analysis_focus="Be conservative on leverage support.",
		)

		self.assertIn("You are the DCF parameter estimation specialist for AutoGraham.", prompt)
		self.assertIn("Do NOT evaluate whether FCFE DCF is appropriate.", prompt)
		self.assertIn("Try to look for relevant info and consensus through public and free online sources", prompt)
		self.assertIn("Estimate only `projection_years` and the exact inputs required by the Python function.", prompt)
		self.assertIn("Pay special attention to whether the company is still in a buildout, scaling, restructuring, or transition phase.", prompt)
		self.assertIn("Do not estimate any additional model inputs beyond the fields listed above.", prompt)
		self.assertIn("Forecast revenue year by year from the latest actual revenue base.", prompt)
		self.assertIn("Do not add a separate `growth_rates` field.", prompt)
		self.assertIn("Important modeling definitions:", prompt)
		self.assertIn('"projection_years": 0', prompt)
		self.assertIn('"assumption_notes": {', prompt)
		self.assertIn('"ebit_margin": []', prompt)
		self.assertIn('"cost_of_equity": 0.0', prompt)
		self.assertIn('"model_warnings": ["string"]', prompt)
		self.assertIn("Additional analysis focus: Be conservative on leverage support.", prompt)

	def test_parameter_prompt_dispatches_to_ddm_builder(self) -> None:
		prompt = build_parameter_prompt(
			ticker="KO",
			selected_model="DDM",
			selected_variant="Two-Stage",
			candidate_facts=[{"label": "Dividend Per Share", "value": 1.94, "source": "Yahoo Finance"}],
		)

		self.assertIn("Chosen model family: DDM", prompt)
		self.assertIn('DDM + "Drivers": earnings_per_share, payout_ratio, required_return, terminal_growth, shares_outstanding', prompt)
		self.assertIn('DDM + "Two-Stage": required_return, high_growth, projection_years, terminal_growth', prompt)
		self.assertIn("DDM supports both stage-based variants and the driver-based `Drivers` path.", prompt)

	def test_parameter_prompt_dispatches_to_ddm_driver_builder(self) -> None:
		prompt = build_parameter_prompt(
			ticker="PG",
			selected_model="DDM",
			selected_variant="Drivers",
			candidate_facts=[{"label": "Dividend Per Share", "value": 4.03, "source": "Yahoo Finance"}],
			calculation_model="DDM",
			analysis_focus="Stay conservative on payout expansion.",
		)

		self.assertIn("You are the DDM parameter estimation specialist for AutoGraham.", prompt)
		self.assertIn("`calculate_ddm_from_drivers(...)` in `ddm.py`.", prompt)
		self.assertIn('"earnings_per_share": []', prompt)
		self.assertIn('"payout_ratio": []', prompt)
		self.assertIn("Additional analysis focus: Stay conservative on payout expansion.", prompt)

	def test_parameter_prompt_dispatches_to_rim_driver_builder(self) -> None:
		prompt = build_parameter_prompt(
			ticker="JPM",
			selected_model="RIM",
			selected_variant=None,
			candidate_facts=[{"label": "Book Value Per Share", "value": 110.0, "source": "Yahoo Finance"}],
			calculation_model="RIM",
			analysis_focus="Stay conservative on excess-return fade.",
		)

		self.assertIn("You are the RIM parameter estimation specialist for AutoGraham.", prompt)
		self.assertIn("Do NOT evaluate whether RIM is appropriate.", prompt)
		self.assertIn("`calculate_rim_from_drivers(...)` in `rim.py`.", prompt)
		self.assertIn('"return_on_equity": []', prompt)
		self.assertIn('"payout_ratio": []', prompt)
		self.assertIn("Additional analysis focus: Stay conservative on excess-return fade.", prompt)


if __name__ == "__main__":
	unittest.main()
