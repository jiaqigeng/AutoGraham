from __future__ import annotations

from collections.abc import Callable
from typing import Any

from valuation.dcf import (
	calculate_apv,
	calculate_fcfe_single_stage,
	calculate_fcfe_three_stage,
	calculate_fcfe_two_stage,
	calculate_fcff_single_stage,
	calculate_fcff_three_stage,
	calculate_fcff_two_stage,
)
from valuation.ddm import (
	calculate_ddm_h_model,
	calculate_ddm_single_stage,
	calculate_ddm_three_stage,
	calculate_ddm_two_stage,
)
from valuation.rim import calculate_rim
from valuation.types import ValuationResult


MODEL_NAME_MAP = {
	"FCFF": "Free Cash Flow to Firm (FCFF)",
	"FCFE": "Free Cash Flow to Equity (FCFE)",
	"DDM": "Dividend Discount Model (DDM)",
	"APV": "Adjusted Present Value (APV)",
	"RIM": "Residual Income Model (RIM)",
}


RegistryEntry = dict[str, Any]


MODEL_REGISTRY: dict[str, RegistryEntry] = {
	"FCFF": {
		"display_name": MODEL_NAME_MAP["FCFF"],
		"variants": {
			"Single-Stage (Stable)": {
				"function": calculate_fcff_single_stage,
				"parameters": ["current_fcff", "shares_outstanding", "wacc", "stable_growth", "total_debt", "cash", "current_price"],
			},
			"Two-Stage": {
				"function": calculate_fcff_two_stage,
				"parameters": ["current_fcff", "shares_outstanding", "high_growth", "projection_years", "wacc", "terminal_growth", "total_debt", "cash", "current_price"],
			},
			"Three-Stage (Multi-stage decay)": {
				"function": calculate_fcff_three_stage,
				"parameters": ["current_fcff", "shares_outstanding", "high_growth", "high_growth_years", "transition_years", "wacc", "terminal_growth", "total_debt", "cash", "current_price"],
			},
		},
	},
	"FCFE": {
		"display_name": MODEL_NAME_MAP["FCFE"],
		"variants": {
			"Single-Stage (Stable)": {
				"function": calculate_fcfe_single_stage,
				"parameters": ["current_fcfe", "shares_outstanding", "cost_of_equity", "stable_growth", "current_price"],
			},
			"Two-Stage": {
				"function": calculate_fcfe_two_stage,
				"parameters": ["current_fcfe", "shares_outstanding", "high_growth", "projection_years", "cost_of_equity", "terminal_growth", "current_price"],
			},
			"Three-Stage (Multi-stage decay)": {
				"function": calculate_fcfe_three_stage,
				"parameters": ["current_fcfe", "shares_outstanding", "high_growth", "high_growth_years", "transition_years", "cost_of_equity", "terminal_growth", "current_price"],
			},
		},
	},
	"DDM": {
		"display_name": MODEL_NAME_MAP["DDM"],
		"variants": {
			"Single-Stage (Stable)": {
				"function": calculate_ddm_single_stage,
				"parameters": ["current_dividend_per_share", "shares_outstanding", "required_return", "stable_growth", "current_price"],
			},
			"Two-Stage": {
				"function": calculate_ddm_two_stage,
				"parameters": ["current_dividend_per_share", "shares_outstanding", "high_growth", "projection_years", "required_return", "terminal_growth", "current_price"],
			},
			"Three-Stage (Multi-stage decay)": {
				"function": calculate_ddm_three_stage,
				"parameters": ["current_dividend_per_share", "shares_outstanding", "high_growth", "high_growth_years", "transition_years", "required_return", "terminal_growth", "current_price"],
			},
			"H-Model": {
				"function": calculate_ddm_h_model,
				"parameters": ["current_dividend_per_share", "shares_outstanding", "short_term_growth", "stable_growth", "half_life_years", "required_return", "current_price"],
			},
		},
	},
	"APV": {
		"display_name": MODEL_NAME_MAP["APV"],
		"variants": {
			None: {
				"function": calculate_apv,
				"parameters": ["current_fcff", "shares_outstanding", "high_growth", "projection_years", "unlevered_cost", "terminal_growth", "total_debt", "cash", "tax_rate", "cost_of_debt", "current_price"],
			}
		},
	},
	"RIM": {
		"display_name": MODEL_NAME_MAP["RIM"],
		"variants": {
			None: {
				"function": calculate_rim,
				"parameters": ["book_value_per_share", "shares_outstanding", "return_on_equity", "cost_of_equity", "payout_ratio", "projection_years", "terminal_growth", "current_price"],
			}
		},
	},
}


def get_supported_models() -> dict[str, RegistryEntry]:
	return MODEL_REGISTRY


def resolve_model_variant(model_code: str, growth_stage: str | None) -> RegistryEntry:
	model_key = model_code.upper()
	if model_key not in MODEL_REGISTRY:
		raise ValueError(f"Unsupported valuation model: {model_code}")
	variants = MODEL_REGISTRY[model_key]["variants"]
	if growth_stage not in variants:
		if None in variants and growth_stage is not None:
			raise ValueError(f"{model_key} does not support a growth-stage variant.")
		if growth_stage is not None:
			raise ValueError(f"Unsupported growth stage '{growth_stage}' for model {model_key}.")
	return variants[growth_stage]


def calculate_model(
	model_code: str,
	growth_stage: str | None,
	assumptions: dict[str, float],
) -> ValuationResult:
	entry = resolve_model_variant(model_code, growth_stage)
	function: Callable[..., ValuationResult] = entry["function"]
	parameters: list[str] = entry["parameters"]
	integer_fields = {"projection_years", "high_growth_years", "transition_years"}
	call_args = [
		int(round(assumptions[name])) if name in integer_fields else assumptions[name]
		for name in parameters
	]
	return function(*call_args)
