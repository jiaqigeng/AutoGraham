from __future__ import annotations

import json
import re
from typing import Any, Mapping

from agent.schemas import DCFSchema, DDMSchema, ParameterPayload, RIMSchema
from valuation.registry import resolve_model_variant


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


def coerce_numeric_assumptions(raw_assumptions: Mapping[str, Any]) -> dict[str, float]:
	"""Coerce an assumption mapping into numeric values where possible."""

	coerced: dict[str, float] = {}
	for key, value in raw_assumptions.items():
		if value is None or value == "":
			continue
		coerced[key] = float(value)
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

	growth_stage = parsed.selected_variant
	if valuation_model_code == "RIM":
		growth_stage = None

	fact_lookup = candidate_fact_lookup([fact.model_dump() for fact in parsed.fetched_facts])
	combined_inputs = {**fact_lookup, **coerce_numeric_assumptions(parsed.assumptions)}
	if "dividend_per_share" in combined_inputs and "current_dividend_per_share" not in combined_inputs:
		combined_inputs["current_dividend_per_share"] = combined_inputs["dividend_per_share"]
	if "starting_fcff" in combined_inputs and "current_fcff" not in combined_inputs:
		combined_inputs["current_fcff"] = combined_inputs["starting_fcff"]
	if "starting_fcfe" in combined_inputs and "current_fcfe" not in combined_inputs:
		combined_inputs["current_fcfe"] = combined_inputs["starting_fcfe"]

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

	normalized_inputs: dict[str, float] = {}
	for key in required_parameters:
		value = combined_inputs.get(key)
		if value in (None, ""):
			errors.append(f"missing required input: {key}")
			continue
		normalized_inputs[key] = float(value)

	return {
		"is_valid": not errors,
		"errors": errors,
		"normalized_payload": normalized_payload,
		"normalized_inputs": normalized_inputs,
		"valuation_model_code": valuation_model_code,
		"growth_stage": growth_stage,
	}
