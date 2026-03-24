from __future__ import annotations

from typing import Any, Mapping

from valuation import MODEL_NAME_MAP, calculate_model, default_valuation_inputs
from valuation.registry import resolve_model_variant

from agent.tools.validation_tools import validate_parameter_payload


ASSUMPTION_LABELS = {
	"wacc": "WACC",
	"cost_of_equity": "Cost of Equity",
	"growth_rate": "Growth Rate",
	"revenue": "Revenue Forecast",
	"ebit_margin": "EBIT Margin Forecast",
	"tax_rate": "Tax Rate Forecast",
	"depreciation": "Depreciation Forecast",
	"capex": "Capex Forecast",
	"change_in_nwc": "Change in NWC Forecast",
	"net_borrowing": "Net Borrowing Forecast",
	"earnings_per_share": "Earnings Per Share Forecast",
	"required_return": "Required Return",
	"high_growth": "High Growth",
	"stable_growth": "Stable Growth",
	"terminal_growth": "Terminal Growth",
	"projection_years": "Projection Years",
	"book_value_per_share": "Book Value / Share",
	"return_on_equity": "Forward ROE",
	"payout_ratio": "Payout Ratio",
	"total_debt": "Total Debt",
	"cash": "Cash",
	"shares_outstanding": "Shares Outstanding",
}

FACT_LABELS = {
	"current_price": "Current Price",
	"shares_outstanding": "Shares Outstanding",
	"starting_fcff": "Starting FCFF",
	"starting_fcfe": "Starting FCFE",
	"book_value_per_share": "Book Value per Share",
	"dividend_per_share": "Dividend per Share",
	"total_debt": "Total Debt",
	"cash": "Cash",
	"return_on_equity": "Observed ROE",
	"payout_ratio": "Observed Payout Ratio",
}

NON_DISPLAY_ASSUMPTION_KEYS = {
	"current_dividend_per_share",
	"current_fcfe",
	"current_fcff",
	"current_price",
}


def build_default_fetched_facts(defaults: Mapping[str, float]) -> list[dict[str, Any]]:
	"""Create a baseline fetched-facts block from deterministic market data."""

	keys = (
		"current_price",
		"shares_outstanding",
		"starting_fcff",
		"starting_fcfe",
		"book_value_per_share",
		"dividend_per_share",
		"total_debt",
		"cash",
		"return_on_equity",
		"payout_ratio",
	)
	return [
		{
			"key": key,
			"label": FACT_LABELS.get(key, key.replace("_", " ").title()),
			"value": defaults.get(key),
			"numeric_value": defaults.get(key),
			"source": "Yahoo Finance / deterministic preprocessing",
			"confidence": 0.9,
			"note": "Observed data anchor used by the valuation boundary.",
		}
		for key in keys
	]


def assumption_keys_for_choice(selected_model: str, growth_stage: str | None) -> list[str]:
	"""Return display-worthy parameter keys derived from the valuation registry."""

	try:
		entry = resolve_model_variant(selected_model, growth_stage)
	except Exception:
		return []

	return [key for key in entry["parameters"] if key not in NON_DISPLAY_ASSUMPTION_KEYS]


def default_parameter_fallback(
	selected_model: str,
	selected_variant: str | None,
	defaults: Mapping[str, float],
	calculation_model: str | None = None,
) -> dict[str, Any]:
	"""Build conservative fallback assumptions after research/model selection."""

	calculation_code = calculation_model or ("FCFF" if selected_model == "DCF" else selected_model)
	if calculation_code == "FCFF":
		assumptions = {
			"wacc": defaults["wacc"],
			"growth_rate": defaults["high_growth"],
			"projection_years": defaults["projection_years"],
			"terminal_growth": defaults["stable_growth"],
		}
	elif calculation_code == "FCFE":
		assumptions = {
			"cost_of_equity": defaults["cost_of_equity"],
			"growth_rate": defaults["high_growth"],
			"projection_years": defaults["projection_years"],
			"terminal_growth": defaults["stable_growth"],
		}
	elif calculation_code == "DDM":
		assumptions = {"required_return": defaults["cost_of_equity"]}
		if selected_variant == "Single-Stage (Stable)":
			assumptions["stable_growth"] = defaults["stable_growth"]
		else:
			assumptions.update(
				{
					"high_growth": defaults["high_growth"],
					"projection_years": defaults["projection_years"],
					"terminal_growth": defaults["stable_growth"],
				}
			)
	else:
		assumptions = {
			"return_on_equity": defaults["return_on_equity"],
			"cost_of_equity": defaults["cost_of_equity"],
			"payout_ratio": defaults["payout_ratio"],
			"projection_years": defaults["projection_years"],
			"terminal_growth": defaults["stable_growth"],
		}

	return {
		"parameter_reason": "Fallback to conservative deterministic anchors after the agent could not produce a better validated parameter set.",
		"assumptions": assumptions,
		"assumption_reasons": [
			{"key": key, "reason": "Fallback to a conservative default anchor derived from company fundamentals."}
			for key in assumptions
		],
	}


def _result_to_payload(result: Any, selected_model: str, growth_stage: str | None) -> dict[str, Any]:
	"""Normalize the deterministic valuation result into a serializable payload."""

	return {
		"selected_model": selected_model,
		"model_name": MODEL_NAME_MAP[selected_model],
		"growth_stage": growth_stage,
		"fair_value_per_share": result.fair_value_per_share,
		"current_price": result.current_price,
		"margin_of_safety": result.margin_of_safety,
		"equity_value": result.equity_value,
		"present_value_of_cash_flows": result.present_value_of_cash_flows,
		"discounted_terminal_value": result.discounted_terminal_value,
		"enterprise_value": result.enterprise_value,
		"schedule": list(getattr(result, "schedule", []) or []),
		"tax_shield_value": result.tax_shield_value,
	}


def run_valuation_calculation(parameter_payload: Mapping[str, Any]) -> dict[str, Any]:
	"""Validate the payload and call deterministic valuation math outside the agent folder."""

	validation = validate_parameter_payload(parameter_payload)
	if not validation["is_valid"]:
		raise ValueError("; ".join(validation["errors"]))

	selected_model = str(validation["valuation_model_code"] or "")
	growth_stage = validation.get("growth_stage")
	result = calculate_model(selected_model, growth_stage, validation["normalized_inputs"])

	reason_lookup = {
		item.get("key"): item.get("reason")
		for item in (parameter_payload.get("assumption_reasons") or [])
		if isinstance(item, dict) and item.get("key")
	}
	assumption_rows = []
	for key in assumption_keys_for_choice(selected_model, growth_stage):
		if key not in validation["normalized_inputs"]:
			continue
		assumption_rows.append(
			{
				"key": key,
				"label": ASSUMPTION_LABELS.get(key, key.replace("_", " ").title()),
				"value": validation["normalized_inputs"][key],
				"reason": reason_lookup.get(key, "Estimated assumption used by the deterministic valuation boundary."),
			}
		)

	payload = _result_to_payload(result, selected_model, growth_stage)
	payload["assumptions"] = assumption_rows
	payload["parameter_reason"] = str(parameter_payload.get("parameter_reason") or "").strip()
	payload["confidence"] = parameter_payload.get("confidence")
	payload["weak_or_uncertain_inputs"] = list(parameter_payload.get("weak_or_uncertain_inputs") or [])
	return payload


def calculate_recommended_value(
	info: Mapping[str, Any],
	recommendation: Mapping[str, Any],
	annual_cashflow=None,
	annual_balance_sheet=None,
	annual_income_stmt=None,
) -> dict[str, Any]:
	"""Compatibility helper for tests and simple agent-tool usage."""

	defaults = default_valuation_inputs(
		info,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)
	selected_model = str(recommendation.get("selected_model") or "").upper()
	growth_stage = recommendation.get("selected_variant", recommendation.get("growth_stage"))
	if selected_model not in MODEL_NAME_MAP:
		raise ValueError("AI returned an unsupported valuation model.")

	payload_model = "DCF" if selected_model in {"FCFF", "FCFE"} else selected_model
	payload = {
		"selected_model": payload_model,
		"selected_variant": growth_stage,
		"calculation_model": selected_model,
		"parameter_reason": str(recommendation.get("parameter_reason") or "").strip(),
		"fetched_facts": build_default_fetched_facts(defaults),
		"assumptions": dict(recommendation.get("assumptions") or {}),
		"assumption_reasons": list(recommendation.get("assumption_reasons") or []),
		"confidence": recommendation.get("confidence"),
	}
	result_payload = run_valuation_calculation(payload)
	result_payload["model_reason"] = str(recommendation.get("model_reason") or "").strip()
	return result_payload
