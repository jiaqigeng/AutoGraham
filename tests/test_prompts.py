from __future__ import annotations

import unittest

from agent.skill_prompt_loader import (
	build_context_request,
	build_context_system_prompt,
	build_dcf_parameter_prompt,
	build_model_selection_prompt,
	build_parameter_prompt,
)


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
		self.assertIn("## Available Variants For Reasoning", prompt)
		self.assertIn("- DCF: set `selected_variant` to `Drivers`", prompt)
		self.assertIn("`selected_variant` must always be exactly `Drivers`.", prompt)
		self.assertIn("never choose more than 10 years", prompt)
		self.assertIn("For the current AI workflow, `projection_years` must be exactly `5` or `10` whenever the chosen model requires an explicit forecast horizon.", prompt)
		self.assertIn("Choose only between `5` years and `10` years.", prompt)
		self.assertIn("If the company is still in buildout, scaling, restructuring, turnaround, or another transition period, consider a longer explicit forecast horizon.", prompt)
		self.assertIn("Consider business visibility. More stable and recurring businesses can support somewhat longer explicit forecasts than volatile, low-visibility, or rapidly changing businesses.", prompt)
		self.assertIn("Consider cyclicality. If the business is cyclical, use enough years to avoid anchoring on a single unusually strong or weak year, but avoid pretending you can forecast too far with precision.", prompt)
		self.assertIn("Consider capital intensity and investment programs. Heavy expansion capex, network buildout, capacity additions, or major product/platform investment can justify a longer horizon.", prompt)
		self.assertIn("If the company already looks mature, stable, and close to steady-state economics, prefer a shorter horizon.", prompt)
		self.assertIn('"projection_years": 5', prompt)
		self.assertIn('"projection_years_reason"', prompt)
		self.assertIn('"required_parameters_next"', prompt)
		self.assertIn("Output structured JSON only.", prompt)
		self.assertIn("Additional analysis focus: Be conservative about dividend durability.", prompt)
		self.assertNotIn("{{ticker}}", prompt)

	def test_context_system_prompt_includes_minimal_case_file_contract(self) -> None:
		prompt = build_context_system_prompt("MSFT", "Microsoft Corporation")

		self.assertIn("You are the lightweight Context Builder for AutoGraham.", prompt)
		self.assertIn("Build only the broad business context needed before model selection.", prompt)
		self.assertIn("Use tools only when needed, not by default.", prompt)
		self.assertIn("## Minimal Case File", prompt)
		self.assertIn("### Company Identity", prompt)
		self.assertIn("### Business Model", prompt)
		self.assertIn("### Company Type", prompt)
		self.assertIn("### Current Phase", prompt)

	def test_context_request_includes_company_hint(self) -> None:
		prompt = build_context_request(
			target_ticker="MSFT",
			company_name="Microsoft Corporation",
		)

		self.assertIn("company_name_hint: Microsoft Corporation", prompt)
		self.assertIn("ticker: MSFT", prompt)
		self.assertIn("build only the minimal case file needed before model selection", prompt)
		self.assertNotIn("Additional user focus", prompt)

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
		self.assertIn("Calculation model: FCFF", prompt)
		self.assertIn("Use this section only when the calculation model is `FCFF`.", prompt)
		self.assertIn("Try to look for relevant info and consensus through public and free online sources", prompt)
		self.assertIn("For DCF research, prefer grouped parameter web research by driver family instead of one tool call per parameter whenever practical.", prompt)
		self.assertIn("Every final parameter still needs evidence-based reasoning, but the evidence can come from grouped searches that cover a related set of assumptions together.", prompt)
		self.assertIn("Estimate only `projection_years` and the exact inputs required by the Python function.", prompt)
		self.assertIn("Pay special attention to whether the company is still in a buildout, scaling, restructuring, or transition phase.", prompt)
		self.assertIn("Do not estimate any additional model inputs beyond the fields listed above.", prompt)
		self.assertIn("Forecast revenue year by year from the latest actual revenue base.", prompt)
		self.assertIn("Do not add a separate `growth_rates` field.", prompt)
		self.assertIn("Estimate `wacc` directly as one scalar discount rate", prompt)
		self.assertIn('"projection_years": 0', prompt)
		self.assertIn('"assumption_notes": {', prompt)
		self.assertIn('"wacc": 0.0', prompt)
		self.assertIn('"model_warnings": [', prompt)
		self.assertIn("Ticker: AAPL", prompt)
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
		self.assertIn("Calculation model: FCFE", prompt)
		self.assertIn("Use this section only when the calculation model is `FCFE`.", prompt)
		self.assertIn("Try to look for relevant info and consensus through public and free online sources", prompt)
		self.assertIn("For DCF research, prefer grouped parameter web research by driver family instead of one tool call per parameter whenever practical.", prompt)
		self.assertIn("Every final parameter still needs evidence-based reasoning, but the evidence can come from grouped searches that cover a related set of assumptions together.", prompt)
		self.assertIn("Estimate only `projection_years` and the exact inputs required by the Python function.", prompt)
		self.assertIn("Pay special attention to whether the company is still in a buildout, scaling, restructuring, or transition phase.", prompt)
		self.assertIn("Do not estimate any additional model inputs beyond the fields listed above.", prompt)
		self.assertIn("Forecast revenue year by year from the latest actual revenue base.", prompt)
		self.assertIn("Do not add a separate `growth_rates` field.", prompt)
		self.assertIn("FCFE = EBIT * (1 - tax_rate) + Depreciation - Capex - Change in NWC + Net Borrowing.", prompt)
		self.assertIn('"projection_years": 0', prompt)
		self.assertIn('"assumption_notes": {', prompt)
		self.assertIn('"ebit_margin": []', prompt)
		self.assertIn('"cost_of_equity": 0.0', prompt)
		self.assertIn('"model_warnings": [', prompt)
		self.assertIn("Additional analysis focus: Be conservative on leverage support.", prompt)

	def test_parameter_prompt_dispatches_to_ddm_builder(self) -> None:
		prompt = build_parameter_prompt(
			ticker="KO",
			selected_model="DDM",
			selected_variant="Drivers",
			candidate_facts=[{"label": "Dividend Per Share", "value": 1.94, "source": "Yahoo Finance"}],
		)

		self.assertIn("You are the DDM parameter estimation specialist for AutoGraham.", prompt)
		self.assertIn("For DDM research, prefer grouped parameter web research by driver family instead of one tool call per parameter whenever practical.", prompt)
		self.assertIn("Every final parameter still needs evidence-based reasoning, but the evidence can come from grouped searches that cover a related set of assumptions together.", prompt)
		self.assertIn("Chosen variant: Drivers", prompt)
		self.assertIn("Chosen projection years: Not provided", prompt)
		self.assertIn("Use this section only when `Drivers` is `Drivers`.", prompt)
		self.assertIn('"earnings_per_share": []', prompt)
		self.assertIn('"payout_ratio": []', prompt)

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
		self.assertIn("For DDM research, prefer grouped parameter web research by driver family instead of one tool call per parameter whenever practical.", prompt)
		self.assertIn("Chosen variant: Drivers", prompt)
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
		self.assertIn("Do not evaluate whether RIM is appropriate.", prompt)
		self.assertIn("`calculate_rim_from_drivers(...)` in `rim.py`.", prompt)
		self.assertIn("For RIM research, prefer grouped parameter web research by driver family instead of one tool call per parameter whenever practical.", prompt)
		self.assertIn("Every final parameter still needs evidence-based reasoning, but the evidence can come from grouped searches that cover a related set of assumptions together.", prompt)
		self.assertIn("Chosen variant: None", prompt)
		self.assertIn('"return_on_equity": []', prompt)
		self.assertIn('"payout_ratio": []', prompt)
		self.assertIn("Additional analysis focus: Stay conservative on excess-return fade.", prompt)


if __name__ == "__main__":
	unittest.main()
