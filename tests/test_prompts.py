from __future__ import annotations

import unittest

from agent.skill_prompt_loader import (
	build_extraction_prompt,
	build_macro_analysis_prompts,
	build_dcf_parameter_prompt,
	build_model_selection_prompt,
	build_parameter_prompt,
	build_qualitative_analysis_prompts,
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

	def test_macro_analysis_prompts_render_from_skill_markdown(self) -> None:
		system_prompt, user_prompt = build_macro_analysis_prompts(
			ticker="MSFT",
			company_name="Microsoft Corporation",
			sector="Technology",
			industry="Software - Infrastructure",
			competitors=["AMZN", "GOOGL"],
			macro_lines=["- CPI: 3.1 as of 2026-03-01."],
			company_news_lines=["- Microsoft AI momentum continues: Enterprise demand remains healthy."],
			market_news_lines=["- Cloud spending stays resilient: Hyperscaler capex remains elevated."],
			tailwind_lines=["- AI platform adoption remains strong."],
			headwind_lines=["- Competition in cloud infrastructure remains intense."],
			analysis_focus="Focus on cloud and AI demand durability.",
		)

		self.assertIn("You are AutoGraham's Macro & Industry Agent.", system_prompt)
		self.assertIn("Ticker: MSFT", user_prompt)
		self.assertIn("Competitors (inferred): AMZN, GOOGL", user_prompt)
		self.assertIn("Analysis focus: Focus on cloud and AI demand durability.", user_prompt)
		self.assertNotIn("{{ticker}}", user_prompt)

	def test_qualitative_analysis_prompts_render_from_skill_markdown(self) -> None:
		system_prompt, user_prompt = build_qualitative_analysis_prompts(
			ticker="ADBE",
			company_summary="Adobe sells creative and document software through subscription models.",
			revenue_driver_lines=["- Business: Subscription revenue remains the primary driver."],
			moat_lines=["- Business: Switching costs remain meaningful for creative professionals."],
			risk_lines=["- Risk Factors: Competition from AI-native tools could pressure pricing."],
			analysis_focus="Focus on product ecosystem stickiness.",
		)

		self.assertIn("You are AutoGraham's Qualitative Analyst Agent.", system_prompt)
		self.assertIn("Ticker: ADBE", user_prompt)
		self.assertIn("Company summary: Adobe sells creative", user_prompt)
		self.assertIn("Focus on product ecosystem stickiness.", user_prompt)
		self.assertNotIn("{{company_summary}}", user_prompt)

	def test_extraction_prompt_renders_from_skill_markdown(self) -> None:
		system_prompt, user_prompt = build_extraction_prompt(
			ticker="AAPL",
			research_report="Revenue growth is slowing while services remain resilient.",
			source_notes=[{"title": "10-K", "snippet": "Services gross margin remains strong."}],
		)

		self.assertEqual(system_prompt, "Return JSON only.")
		self.assertIn("Specialized role: Source extractor.", user_prompt)
		self.assertIn("Ticker: AAPL", user_prompt)
		self.assertIn("- 10-K: Services gross margin remains strong.", user_prompt)
		self.assertNotIn("{{source_notes}}", user_prompt)


if __name__ == "__main__":
	unittest.main()
