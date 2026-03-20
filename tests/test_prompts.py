from __future__ import annotations

import unittest

from agent.prompts.model_selection_prompts import build_model_selection_prompt
from agent.prompts.parameter_prompts import build_parameter_prompt
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
		self.assertIn('single_stage -> "Single-Stage (Stable)"', prompt)
		self.assertIn('"selected_variant" must be exactly one of: "Single-Stage (Stable)", "Two-Stage", "Three-Stage (Multi-stage decay)", or null.', prompt)
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

	def test_parameter_prompt_includes_estimator_contract_and_key_mapping(self) -> None:
		prompt = build_parameter_prompt(
			ticker="AAPL",
			selected_model="DCF",
			selected_variant="Two-Stage",
			candidate_facts=[
				{"label": "Current Price", "value": 100.0, "source": "Yahoo Finance"},
				{"label": "Starting FCFF", "value": 25000000000, "source": "Cash flow statement"},
			],
			analysis_focus="Stay conservative on terminal assumptions.",
		)

		self.assertIn("You are the Valuation Parameter Estimator for AutoGraham.", prompt)
		self.assertIn('single_stage -> "Single-Stage (Stable)"', prompt)
		self.assertIn('DCF + "Two-Stage" + FCFF: wacc, high_growth, projection_years, terminal_growth', prompt)
		self.assertIn('RIM: return_on_equity, cost_of_equity, payout_ratio, projection_years, terminal_growth', prompt)
		self.assertIn('"weak_or_uncertain_inputs"', prompt)
		self.assertIn("Additional analysis focus: Stay conservative on terminal assumptions.", prompt)


if __name__ == "__main__":
	unittest.main()
