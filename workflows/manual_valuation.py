from __future__ import annotations

from typing import Any, Mapping

from valuation import calculate_model, default_valuation_inputs
from valuation.types import ValuationResult


MODEL_OPTIONS = [
	"Free Cash Flow to Firm (FCFF) - Unlevered DCF",
	"Free Cash Flow to Equity (FCFE) - Levered DCF",
	"Dividend Discount Model (DDM)",
	"Adjusted Present Value (APV)",
	"Residual Income Model (RIM)",
]

MODEL_META = {
	"Free Cash Flow to Firm (FCFF) - Unlevered DCF": {
		"code": "FCFF",
		"short": "FCFF",
		"eyebrow": "Unlevered enterprise lens",
		"description": "Values the operating business first, then bridges from enterprise value to equity after debt and cash.",
	},
	"Free Cash Flow to Equity (FCFE) - Levered DCF": {
		"code": "FCFE",
		"short": "FCFE",
		"eyebrow": "Direct equity cash flows",
		"description": "Discounts cash available to equity holders directly, which makes it useful when leverage is part of the story.",
	},
	"Dividend Discount Model (DDM)": {
		"code": "DDM",
		"short": "DDM",
		"eyebrow": "Distribution-based valuation",
		"description": "Frames value through dividend capacity and works best for mature payout-heavy businesses.",
	},
	"Adjusted Present Value (APV)": {
		"code": "APV",
		"short": "APV",
		"eyebrow": "Capital structure overlay",
		"description": "Separates operating value from financing side effects so tax shields can be inspected explicitly.",
	},
	"Residual Income Model (RIM)": {
		"code": "RIM",
		"short": "RIM",
		"eyebrow": "Balance-sheet anchored",
		"description": "Starts from book value and adds present value of future residual income above the cost of equity.",
	},
}

GROWTH_OPTIONS = ["Single-Stage (Stable)", "Two-Stage", "Three-Stage (Multi-stage decay)"]


def prepare_manual_valuation(stock_data: Any) -> dict[str, Any]:
	company_info = getattr(stock_data, "info", stock_data)
	annual_cashflow = getattr(stock_data, "annual_cashflow", None)
	annual_balance_sheet = getattr(stock_data, "annual_balance_sheet", None)
	annual_income_stmt = getattr(stock_data, "annual_income_stmt", None)
	frame_ticker = getattr(annual_cashflow, "attrs", {}).get("ticker", "ticker")
	scope = str(company_info.get("symbol") or company_info.get("shortName") or frame_ticker).strip().upper().replace(" ", "_")
	defaults = default_valuation_inputs(
		company_info,
		annual_cashflow=annual_cashflow,
		annual_balance_sheet=annual_balance_sheet,
		annual_income_stmt=annual_income_stmt,
	)
	return {"scope": scope, "defaults": defaults, "company_info": company_info}


def _registry_payload(assumptions: Mapping[str, float]) -> dict[str, float]:
	return {
		"current_fcff": assumptions.get("starting_fcff", 0.0),
		"current_fcfe": assumptions.get("starting_fcfe", 0.0),
		"current_dividend_per_share": assumptions.get("dividend_per_share", 0.0),
		**assumptions,
	}


def run_manual_valuation(
	model_code: str,
	growth_stage: str | None,
	assumptions: Mapping[str, float],
) -> ValuationResult:
	return calculate_model(model_code, growth_stage, _registry_payload(assumptions))
