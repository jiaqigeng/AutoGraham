from __future__ import annotations

import json
import re
from typing import Any, Mapping

from agent.schemas import DCFSchema, DDMSchema, ParameterPayload, RIMSchema
from valuation.registry import resolve_model_variant


DCF_DRIVER_VARIANT = "Drivers"


def extract_json_object(raw_text: str) -> dict[str, Any]:
	"""Extract the first JSON object from a text response."""

	text = raw_text.strip()
	fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
	if fenced_match:
		text = fenced_match.group(1)
	else:
		start = text.find("{")
		end = text.rfind("}")
		if start != -1 and end != -1 and end > start:
			text = text[start : end + 1]
	payload = json.loads(text)
	if not isinstance(payload, dict):
		raise ValueError("Valuation recommendation payload must be a JSON object.")
	return payload


def extract_json_array(raw_text: str) -> list[dict[str, Any]]:
	"""Extract the first JSON array from a text response."""

	text = raw_text.strip()
	fenced_match = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, flags=re.DOTALL)
	if fenced_match:
		text = fenced_match.group(1)
	else:
		start = text.find("[")
		end = text.rfind("]")
		if start != -1 and end != -1 and end > start:
			text = text[start : end + 1]
	payload = json.loads(text)
	if not isinstance(payload, list):
		raise ValueError("Expected a JSON array.")
	return [item for item in payload if isinstance(item, dict)]


def _coerce_numeric_value(value: Any) -> float | list[float]:
	"""Coerce a scalar or numeric list into floats."""

	if isinstance(value, list):
		return [float(item) for item in value]
	return float(value)


def coerce_numeric_assumptions(raw_assumptions: Mapping[str, Any]) -> dict[str, Any]:
	"""Coerce an assumption mapping into numeric values where possible."""

	coerced: dict[str, Any] = {}
	for key, value in raw_assumptions.items():
		if value is None or value == "":
			continue
		coerced[key] = _coerce_numeric_value(value)
	return coerced


def candidate_fact_lookup(candidate_facts: list[Mapping[str, Any]]) -> dict[str, float]:
	"""Turn fetched facts into a numeric lookup keyed by fact name."""

	lookup: dict[str, float] = {}
	for fact in candidate_facts:
		key = str(fact.get("key") or fact.get("label") or "").strip().lower().replace(" ", "_")
		if not key:
			continue
		value = fact.get("numeric_value", fact.get("value"))
		if value in (None, ""):
			continue
		try:
			lookup[key] = float(value)
		except (TypeError, ValueError):
			continue
	return lookup


def _is_numeric_sequence(value: Any) -> bool:
	return isinstance(value, list) and all(isinstance(item, (int, float)) for item in value)


def _detect_dcf_driver_variant(calculation_model: str | None, combined_inputs: Mapping[str, Any]) -> str | None:
	"""Infer whether the DCF payload is using the driver-based calculation path."""

	if calculation_model == "FCFF":
		required_lists = ("revenue", "ebit_margin", "tax_rate", "depreciation", "capex", "change_in_nwc")
	elif calculation_model == "FCFE":
		required_lists = ("revenue", "ebit_margin", "tax_rate", "depreciation", "capex", "change_in_nwc", "net_borrowing")
	else:
		return None
	if all(_is_numeric_sequence(combined_inputs.get(key)) for key in required_lists):
		if calculation_model == "FCFF":
			return DCF_DRIVER_VARIANT if isinstance(combined_inputs.get("wacc"), (int, float)) else None
		if calculation_model == "FCFE":
			return DCF_DRIVER_VARIANT if isinstance(combined_inputs.get("cost_of_equity"), (int, float)) else None
		return DCF_DRIVER_VARIANT
	return None


def validate_parameter_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
	"""Validate the model-ready payload right before deterministic valuation."""

	errors: list[str] = []
	try:
		parsed = ParameterPayload.model_validate(payload)
	except Exception as exc:
		return {
			"is_valid": False,
			"errors": [f"parameter payload schema error: {exc}"],
			"normalized_payload": {},
			"normalized_inputs": {},
			"valuation_model_code": None,
			"growth_stage": None,
		}

	normalized_payload = parsed.model_dump()
	calculation_model = parsed.calculation_model
	if parsed.selected_model == "DCF":
		if calculation_model not in {"FCFF", "FCFE"}:
			errors.append("DCF payload must specify calculation_model as FCFF or FCFE.")
		valuation_model_code = calculation_model
	elif parsed.selected_model == "DDM":
		valuation_model_code = "DDM"
		calculation_model = "DDM"
	elif parsed.selected_model == "RIM":
		valuation_model_code = "RIM"
		calculation_model = "RIM"
	else:
		valuation_model_code = None
		errors.append(f"Unsupported selected_model '{parsed.selected_model}'.")

	fact_lookup = candidate_fact_lookup([fact.model_dump() for fact in parsed.fetched_facts])
	combined_inputs = {**fact_lookup, **coerce_numeric_assumptions(parsed.assumptions)}
	growth_stage = parsed.selected_variant
	if valuation_model_code == "RIM":
		growth_stage = None
	elif valuation_model_code in {"FCFF", "FCFE"}:
		growth_stage = _detect_dcf_driver_variant(calculation_model, combined_inputs)
	if "dividend_per_share" in combined_inputs and "current_dividend_per_share" not in combined_inputs:
		combined_inputs["current_dividend_per_share"] = combined_inputs["dividend_per_share"]
	if "starting_fcff" in combined_inputs and "current_fcff" not in combined_inputs:
		combined_inputs["current_fcff"] = combined_inputs["starting_fcff"]
	if "starting_fcfe" in combined_inputs and "current_fcfe" not in combined_inputs:
		combined_inputs["current_fcfe"] = combined_inputs["starting_fcfe"]
	if calculation_model in {"FCFF", "FCFE"} and growth_stage != DCF_DRIVER_VARIANT and "growth_rate" not in combined_inputs:
		if "high_growth" in combined_inputs:
			combined_inputs["growth_rate"] = combined_inputs["high_growth"]
		elif "stable_growth" in combined_inputs:
			combined_inputs["growth_rate"] = combined_inputs["stable_growth"]

	try:
		if parsed.selected_model == "DCF":
			DCFSchema(calculation_model=calculation_model or "FCFF", selected_variant=growth_stage, **combined_inputs)
		elif parsed.selected_model == "DDM":
			DDMSchema(selected_variant=growth_stage, **combined_inputs)
		elif parsed.selected_model == "RIM":
			RIMSchema(**combined_inputs)
	except Exception as exc:
		errors.append(f"model-boundary schema error: {exc}")

	if valuation_model_code:
		try:
			required_parameters = resolve_model_variant(valuation_model_code, growth_stage)["parameters"]
		except Exception as exc:
			errors.append(str(exc))
			required_parameters = []
	else:
		required_parameters = []

	normalized_inputs: dict[str, Any] = {}
	for key in required_parameters:
		value = combined_inputs.get(key)
		if value in (None, ""):
			errors.append(f"missing required input: {key}")
			continue
		normalized_inputs[key] = _coerce_numeric_value(value)

	return {
		"is_valid": not errors,
		"errors": errors,
		"normalized_payload": normalized_payload,
		"normalized_inputs": normalized_inputs,
		"valuation_model_code": valuation_model_code,
		"growth_stage": growth_stage,
	}
