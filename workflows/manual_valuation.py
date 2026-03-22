from __future__ import annotations

from typing import Any, Mapping

from valuation.common import margin_of_safety
from valuation.dcf import calculate_fcfe_dcf_simple, calculate_fcff_dcf_simple
from valuation import calculate_model, default_valuation_inputs
from valuation.types import ValuationResult


MODEL_OPTIONS = [
	"Free Cash Flow to Firm (FCFF) - Unlevered DCF",
	"Free Cash Flow to Equity (FCFE) - Levered DCF",
	"Dividend Discount Model (DDM)",
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


def _simple_schedule_to_rows(schedule: list[object]) -> list[dict[str, float | int | str]]:
	rows: list[dict[str, float | int | str]] = []
	for row in schedule:
		rows.append(
			{
				"Year": getattr(row, "year"),
				"Growth Rate": getattr(row, "growth_rate"),
				"Cash Flow": getattr(row, "cash_flow"),
				"Discount Rate": getattr(row, "discount_rate"),
				"Discount Factor": getattr(row, "discount_factor"),
				"Discounted Cash Flow": getattr(row, "discounted_cash_flow"),
			}
		)
	return rows


def _run_manual_dcf_simple(model_code: str, assumptions: Mapping[str, float]) -> ValuationResult:
	current_price = float(assumptions.get("current_price", 0.0))
	if model_code == "FCFF":
		result = calculate_fcff_dcf_simple(
			current_fcff=float(assumptions.get("starting_fcff", 0.0)),
			growth_rate=float(assumptions["growth_rate"]),
			projection_years=int(assumptions["projection_years"]),
			wacc=float(assumptions["wacc"]),
			terminal_growth=float(assumptions["terminal_growth"]),
			total_debt=float(assumptions.get("total_debt", 0.0)),
			cash=float(assumptions.get("cash", 0.0)),
			shares_outstanding=float(assumptions["shares_outstanding"]),
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
			schedule=_simple_schedule_to_rows(result.schedule),
		)

	result = calculate_fcfe_dcf_simple(
		current_fcfe=float(assumptions.get("starting_fcfe", 0.0)),
		growth_rate=float(assumptions["growth_rate"]),
		projection_years=int(assumptions["projection_years"]),
		cost_of_equity=float(assumptions["cost_of_equity"]),
		terminal_growth=float(assumptions["terminal_growth"]),
		shares_outstanding=float(assumptions["shares_outstanding"]),
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
		schedule=_simple_schedule_to_rows(result.schedule),
	)


def run_manual_valuation(
	model_code: str,
	growth_stage: str | None,
	assumptions: Mapping[str, float],
) -> ValuationResult:
	if model_code in {"FCFF", "FCFE"}:
		return _run_manual_dcf_simple(model_code, assumptions)
	return calculate_model(model_code, growth_stage, _registry_payload(assumptions))
