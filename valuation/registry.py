from __future__ import annotations

from collections.abc import Callable
from typing import Any

from valuation.common import margin_of_safety
from valuation.dcf import (
	calculate_fcfe_dcf_from_drivers,
	calculate_fcfe_dcf_simple,
	calculate_fcff_dcf_from_drivers,
	calculate_fcff_dcf_simple,
)
from valuation.ddm import (
	calculate_ddm_from_drivers,
	calculate_ddm_h_model,
	calculate_ddm_single_stage,
	calculate_ddm_three_stage,
	calculate_ddm_two_stage,
)
from valuation.rim import calculate_rim_from_drivers, calculate_rim_simple
from valuation.types import ValuationResult


MODEL_NAME_MAP = {
	"FCFF": "Free Cash Flow to Firm (FCFF)",
	"FCFE": "Free Cash Flow to Equity (FCFE)",
	"DDM": "Dividend Discount Model (DDM)",
	"RIM": "Residual Income Model (RIM)",
}


RegistryEntry = dict[str, Any]
DCF_DRIVER_VARIANT = "Drivers"


def _calculate_fcff_simple_registry(
	current_fcff: float,
	growth_rate: float,
	projection_years: int,
	wacc: float,
	terminal_growth: float,
	total_debt: float,
	cash: float,
	shares_outstanding: float,
	current_price: float,
) -> ValuationResult:
	result = calculate_fcff_dcf_simple(
		current_fcff=current_fcff,
		growth_rate=growth_rate,
		projection_years=projection_years,
		wacc=wacc,
		terminal_growth=terminal_growth,
		total_debt=total_debt,
		cash=cash,
		shares_outstanding=shares_outstanding,
	)
	return ValuationResult(
		model_label="FCFF",
		stage_label="Simple DCF",
		equity_value=result.equity_value,
		fair_value_per_share=result.fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(result.fair_value_per_share, current_price),
		present_value_of_cash_flows=result.pv_forecast_cash_flows,
		discounted_terminal_value=result.pv_terminal_value,
		enterprise_value=result.enterprise_value,
		schedule=[{field_name: getattr(row, field_name) for field_name in row.__dataclass_fields__} for row in result.schedule],
	)


def _calculate_fcfe_simple_registry(
	current_fcfe: float,
	growth_rate: float,
	projection_years: int,
	cost_of_equity: float,
	terminal_growth: float,
	shares_outstanding: float,
	current_price: float,
) -> ValuationResult:
	result = calculate_fcfe_dcf_simple(
		current_fcfe=current_fcfe,
		growth_rate=growth_rate,
		projection_years=projection_years,
		cost_of_equity=cost_of_equity,
		terminal_growth=terminal_growth,
		shares_outstanding=shares_outstanding,
	)
	return ValuationResult(
		model_label="FCFE",
		stage_label="Simple DCF",
		equity_value=result.equity_value,
		fair_value_per_share=result.fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(result.fair_value_per_share, current_price),
		present_value_of_cash_flows=result.pv_forecast_cash_flows,
		discounted_terminal_value=result.pv_terminal_value,
		schedule=[{field_name: getattr(row, field_name) for field_name in row.__dataclass_fields__} for row in result.schedule],
	)


def _calculate_fcff_driver_registry(
	revenue: list[float],
	ebit_margin: list[float],
	tax_rate: list[float],
	depreciation: list[float],
	capex: list[float],
	change_in_nwc: list[float],
	wacc: float,
	terminal_growth: float,
	total_debt: float,
	cash: float,
	shares_outstanding: float,
	current_price: float,
) -> ValuationResult:
	result = calculate_fcff_dcf_from_drivers(
		revenue=revenue,
		ebit_margin=ebit_margin,
		tax_rate=tax_rate,
		depreciation=depreciation,
		capex=capex,
		change_in_nwc=change_in_nwc,
		wacc=wacc,
		terminal_growth=terminal_growth,
		total_debt=total_debt,
		cash=cash,
		shares_outstanding=shares_outstanding,
	)
	return ValuationResult(
		model_label="FCFF",
		stage_label="Driver DCF",
		equity_value=result.equity_value,
		fair_value_per_share=result.fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(result.fair_value_per_share, current_price),
		present_value_of_cash_flows=result.pv_forecast_cash_flows,
		discounted_terminal_value=result.pv_terminal_value,
		enterprise_value=result.enterprise_value,
		schedule=[{field_name: getattr(row, field_name) for field_name in row.__dataclass_fields__} for row in result.schedule],
	)


def _calculate_fcfe_driver_registry(
	revenue: list[float],
	ebit_margin: list[float],
	tax_rate: list[float],
	depreciation: list[float],
	capex: list[float],
	change_in_nwc: list[float],
	net_borrowing: list[float],
	cost_of_equity: float,
	terminal_growth: float,
	shares_outstanding: float,
	current_price: float,
) -> ValuationResult:
	result = calculate_fcfe_dcf_from_drivers(
		revenue=revenue,
		ebit_margin=ebit_margin,
		tax_rate=tax_rate,
		depreciation=depreciation,
		capex=capex,
		change_in_nwc=change_in_nwc,
		net_borrowing=net_borrowing,
		cost_of_equity=cost_of_equity,
		terminal_growth=terminal_growth,
		shares_outstanding=shares_outstanding,
	)
	return ValuationResult(
		model_label="FCFE",
		stage_label="Driver DCF",
		equity_value=result.equity_value,
		fair_value_per_share=result.fair_value_per_share,
		current_price=current_price,
		margin_of_safety=margin_of_safety(result.fair_value_per_share, current_price),
		present_value_of_cash_flows=result.pv_forecast_cash_flows,
		discounted_terminal_value=result.pv_terminal_value,
		schedule=[{field_name: getattr(row, field_name) for field_name in row.__dataclass_fields__} for row in result.schedule],
	)


def _calculate_rim_simple_registry(
	book_value_per_share: float,
	shares_outstanding: float,
	return_on_equity: float,
	cost_of_equity: float,
	payout_ratio: float,
	projection_years: int,
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	return calculate_rim_simple(
		book_value_per_share=book_value_per_share,
		shares_outstanding=shares_outstanding,
		return_on_equity=return_on_equity,
		cost_of_equity=cost_of_equity,
		payout_ratio=payout_ratio,
		projection_years=projection_years,
		terminal_growth=terminal_growth,
		current_price=current_price,
	)


def _calculate_rim_driver_registry(
	book_value_per_share: float,
	shares_outstanding: float,
	return_on_equity: list[float],
	cost_of_equity: float,
	payout_ratio: list[float],
	terminal_growth: float,
	current_price: float,
) -> ValuationResult:
	return calculate_rim_from_drivers(
		book_value_per_share=book_value_per_share,
		shares_outstanding=shares_outstanding,
		return_on_equity=return_on_equity,
		cost_of_equity=cost_of_equity,
		payout_ratio=payout_ratio,
		terminal_growth=terminal_growth,
		current_price=current_price,
	)


MODEL_REGISTRY: dict[str, RegistryEntry] = {
	"FCFF": {
		"display_name": MODEL_NAME_MAP["FCFF"],
		"variants": {
			None: {
				"function": _calculate_fcff_simple_registry,
				"parameters": ["current_fcff", "growth_rate", "projection_years", "wacc", "terminal_growth", "total_debt", "cash", "shares_outstanding", "current_price"],
			},
			DCF_DRIVER_VARIANT: {
				"function": _calculate_fcff_driver_registry,
				"parameters": [
					"revenue",
					"ebit_margin",
					"tax_rate",
					"depreciation",
					"capex",
					"change_in_nwc",
					"wacc",
					"terminal_growth",
					"total_debt",
					"cash",
					"shares_outstanding",
					"current_price",
				],
			},
		},
	},
	"FCFE": {
		"display_name": MODEL_NAME_MAP["FCFE"],
		"variants": {
			None: {
				"function": _calculate_fcfe_simple_registry,
				"parameters": ["current_fcfe", "growth_rate", "projection_years", "cost_of_equity", "terminal_growth", "shares_outstanding", "current_price"],
			},
			DCF_DRIVER_VARIANT: {
				"function": _calculate_fcfe_driver_registry,
				"parameters": [
					"revenue",
					"ebit_margin",
					"tax_rate",
					"depreciation",
					"capex",
					"change_in_nwc",
					"net_borrowing",
					"cost_of_equity",
					"terminal_growth",
					"shares_outstanding",
					"current_price",
				],
			},
		},
	},
	"DDM": {
		"display_name": MODEL_NAME_MAP["DDM"],
		"variants": {
			DCF_DRIVER_VARIANT: {
				"function": calculate_ddm_from_drivers,
				"parameters": ["earnings_per_share", "payout_ratio", "required_return", "terminal_growth", "shares_outstanding", "current_price"],
			},
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
	"RIM": {
		"display_name": MODEL_NAME_MAP["RIM"],
		"variants": {
			None: {
				"function": _calculate_rim_simple_registry,
				"parameters": ["book_value_per_share", "shares_outstanding", "return_on_equity", "cost_of_equity", "payout_ratio", "projection_years", "terminal_growth", "current_price"],
			},
			DCF_DRIVER_VARIANT: {
				"function": _calculate_rim_driver_registry,
				"parameters": ["book_value_per_share", "shares_outstanding", "return_on_equity", "cost_of_equity", "payout_ratio", "terminal_growth", "current_price"],
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
	assumptions: dict[str, Any],
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
