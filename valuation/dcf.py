from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Integral, Real
from typing import Sequence, TypeAlias


@dataclass(frozen=True)
class SimpleDCFYear:
    year: int
    growth_rate: float
    cash_flow: float
    discount_rate: float
    discount_factor: float
    discounted_cash_flow: float


@dataclass(frozen=True)
class AdvancedFCFFYear:
    year: int
    revenue: float
    ebit_margin: float
    ebit: float
    tax_rate: float
    nopat: float
    depreciation: float
    capex: float
    change_in_nwc: float
    fcff: float
    wacc: float
    cumulative_discount_factor: float
    discounted_fcff: float


@dataclass(frozen=True)
class AdvancedFCFEYear:
    year: int
    revenue: float
    ebit_margin: float
    ebit: float
    tax_rate: float
    nopat: float
    depreciation: float
    capex: float
    change_in_nwc: float
    net_borrowing: float
    fcfe: float
    cost_of_equity: float
    cumulative_discount_factor: float
    discounted_fcfe: float


FCFFScheduleRow: TypeAlias = SimpleDCFYear | AdvancedFCFFYear
FCFEScheduleRow: TypeAlias = SimpleDCFYear | AdvancedFCFEYear


@dataclass(frozen=True)
class FCFFDCFResult:
    pv_forecast_cash_flows: float
    pv_terminal_value: float
    enterprise_value: float
    equity_value: float
    fair_value_per_share: float
    terminal_value: float
    terminal_wacc: float
    terminal_cost_of_equity: float | None = None
    schedule: list[FCFFScheduleRow] = field(default_factory=list)


@dataclass(frozen=True)
class FCFEDCFResult:
    pv_forecast_cash_flows: float
    pv_terminal_value: float
    equity_value: float
    fair_value_per_share: float
    terminal_value: float
    terminal_cost_of_equity: float
    schedule: list[FCFEScheduleRow] = field(default_factory=list)


def _validate_numeric(name: str, value: Real) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be numeric.")
    numeric_value = float(value)
    if math.isnan(numeric_value) or math.isinf(numeric_value):
        raise ValueError(f"{name} must be a finite numeric value.")
    return numeric_value


def _validate_positive(name: str, value: Real) -> float:
    numeric_value = _validate_numeric(name, value)
    if numeric_value <= 0:
        raise ValueError(f"{name} must be positive.")
    return numeric_value


def _validate_positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer.")
    integer_value = int(value)
    if integer_value <= 0:
        raise ValueError(f"{name} must be positive.")
    return integer_value


def _validate_discount_rate(name: str, discount_rate: float, terminal_growth: float) -> float:
    normalized_rate = _validate_numeric(name, discount_rate)
    normalized_growth = _validate_numeric("terminal_growth", terminal_growth)
    if normalized_rate <= -1.0:
        raise ValueError(f"{name} must be greater than -1.0.")
    if normalized_rate <= normalized_growth:
        raise ValueError(f"{name} must be greater than terminal_growth.")
    if normalized_rate - normalized_growth <= 0:
        raise ValueError(f"{name} - terminal_growth must be greater than zero.")
    return normalized_rate


def _validate_numeric_list(name: str, values: Sequence[Real]) -> list[float]:
    if not values:
        raise ValueError(f"{name} must be non-empty.")
    return [_validate_numeric(f"{name}[{index}]", value) for index, value in enumerate(values, start=1)]


def _validate_matching_lengths(group_name: str, series_map: dict[str, Sequence[float]]) -> int:
    lengths = {name: len(values) for name, values in series_map.items()}
    unique_lengths = set(lengths.values())
    if len(unique_lengths) != 1:
        formatted_lengths = ", ".join(f"{name}={length}" for name, length in lengths.items())
        raise ValueError(f"{group_name} lists must have the same length; received {formatted_lengths}.")
    return next(iter(unique_lengths))


def _build_cumulative_discount_factors(rates: Sequence[float], label: str) -> list[float]:
    cumulative_factors: list[float] = []
    cumulative_factor = 1.0
    for year, rate in enumerate(rates, start=1):
        if rate <= -1.0:
            raise ValueError(f"{label}[{year}] must be greater than -1.0.")
        cumulative_factor *= 1.0 + rate
        cumulative_factors.append(cumulative_factor)
    return cumulative_factors


def calculate_fcff_dcf_simple(
    current_fcff: float,
    growth_rate: float,
    projection_years: int,
    wacc: float,
    terminal_growth: float,
    total_debt: float,
    cash: float,
    shares_outstanding: float,
) -> FCFFDCFResult:
    normalized_current_fcff = _validate_numeric("current_fcff", current_fcff)
    normalized_growth_rate = _validate_numeric("growth_rate", growth_rate)
    normalized_projection_years = _validate_positive_int("projection_years", projection_years)
    normalized_wacc = _validate_discount_rate("wacc", wacc, terminal_growth)
    normalized_total_debt = _validate_numeric("total_debt", total_debt)
    normalized_cash = _validate_numeric("cash", cash)
    normalized_shares_outstanding = _validate_positive("shares_outstanding", shares_outstanding)

    schedule: list[SimpleDCFYear] = []
    pv_forecast_cash_flows = 0.0
    fcff = normalized_current_fcff

    for year in range(1, normalized_projection_years + 1):
        fcff *= 1.0 + normalized_growth_rate
        discount_factor = (1.0 + normalized_wacc) ** year
        discounted_fcff = fcff / discount_factor
        schedule.append(
            SimpleDCFYear(
                year=year,
                growth_rate=normalized_growth_rate,
                cash_flow=fcff,
                discount_rate=normalized_wacc,
                discount_factor=discount_factor,
                discounted_cash_flow=discounted_fcff,
            )
        )
        pv_forecast_cash_flows += discounted_fcff

    terminal_value = fcff * (1.0 + terminal_growth) / (normalized_wacc - terminal_growth)
    pv_terminal_value = terminal_value / ((1.0 + normalized_wacc) ** normalized_projection_years)
    enterprise_value = pv_forecast_cash_flows + pv_terminal_value
    equity_value = enterprise_value - normalized_total_debt + normalized_cash
    fair_value_per_share = equity_value / normalized_shares_outstanding

    return FCFFDCFResult(
        pv_forecast_cash_flows=pv_forecast_cash_flows,
        pv_terminal_value=pv_terminal_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        terminal_value=terminal_value,
        terminal_wacc=normalized_wacc,
        schedule=schedule,
    )


def calculate_fcfe_dcf_simple(
    current_fcfe: float,
    growth_rate: float,
    projection_years: int,
    cost_of_equity: float,
    terminal_growth: float,
    shares_outstanding: float,
) -> FCFEDCFResult:
    normalized_current_fcfe = _validate_numeric("current_fcfe", current_fcfe)
    normalized_growth_rate = _validate_numeric("growth_rate", growth_rate)
    normalized_projection_years = _validate_positive_int("projection_years", projection_years)
    normalized_cost_of_equity = _validate_discount_rate("cost_of_equity", cost_of_equity, terminal_growth)
    normalized_shares_outstanding = _validate_positive("shares_outstanding", shares_outstanding)

    schedule: list[SimpleDCFYear] = []
    pv_forecast_cash_flows = 0.0
    fcfe = normalized_current_fcfe

    for year in range(1, normalized_projection_years + 1):
        fcfe *= 1.0 + normalized_growth_rate
        discount_factor = (1.0 + normalized_cost_of_equity) ** year
        discounted_fcfe = fcfe / discount_factor
        schedule.append(
            SimpleDCFYear(
                year=year,
                growth_rate=normalized_growth_rate,
                cash_flow=fcfe,
                discount_rate=normalized_cost_of_equity,
                discount_factor=discount_factor,
                discounted_cash_flow=discounted_fcfe,
            )
        )
        pv_forecast_cash_flows += discounted_fcfe

    terminal_value = fcfe * (1.0 + terminal_growth) / (normalized_cost_of_equity - terminal_growth)
    pv_terminal_value = terminal_value / ((1.0 + normalized_cost_of_equity) ** normalized_projection_years)
    equity_value = pv_forecast_cash_flows + pv_terminal_value
    fair_value_per_share = equity_value / normalized_shares_outstanding

    return FCFEDCFResult(
        pv_forecast_cash_flows=pv_forecast_cash_flows,
        pv_terminal_value=pv_terminal_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        terminal_value=terminal_value,
        terminal_cost_of_equity=normalized_cost_of_equity,
        schedule=schedule,
    )


def calculate_fcff_dcf_from_drivers(
    revenue: Sequence[float],
    ebit_margin: Sequence[float],
    tax_rate: Sequence[float],
    depreciation: Sequence[float],
    capex: Sequence[float],
    change_in_nwc: Sequence[float],
    wacc: float,
    terminal_growth: float,
    total_debt: float,
    cash: float,
    shares_outstanding: float,
) -> FCFFDCFResult:
    normalized_series = {
        "revenue": _validate_numeric_list("revenue", revenue),
        "ebit_margin": _validate_numeric_list("ebit_margin", ebit_margin),
        "tax_rate": _validate_numeric_list("tax_rate", tax_rate),
        "depreciation": _validate_numeric_list("depreciation", depreciation),
        "capex": _validate_numeric_list("capex", capex),
        "change_in_nwc": _validate_numeric_list("change_in_nwc", change_in_nwc),
    }
    projection_years = _validate_matching_lengths("FCFF driver", normalized_series)
    normalized_wacc = _validate_discount_rate("wacc", wacc, terminal_growth)
    normalized_total_debt = _validate_numeric("total_debt", total_debt)
    normalized_cash = _validate_numeric("cash", cash)
    normalized_shares_outstanding = _validate_positive("shares_outstanding", shares_outstanding)

    yearly_fcff: list[float] = []
    intermediate_rows: list[dict[str, float | int]] = []

    for index in range(projection_years):
        year = index + 1
        ebit_value = normalized_series["revenue"][index] * normalized_series["ebit_margin"][index]
        nopat_value = ebit_value * (1.0 - normalized_series["tax_rate"][index])
        fcff_value = (
            nopat_value
            + normalized_series["depreciation"][index]
            - normalized_series["capex"][index]
            - normalized_series["change_in_nwc"][index]
        )

        yearly_fcff.append(fcff_value)
        intermediate_rows.append(
            {
                "year": year,
                "revenue": normalized_series["revenue"][index],
                "ebit_margin": normalized_series["ebit_margin"][index],
                "ebit": ebit_value,
                "tax_rate": normalized_series["tax_rate"][index],
                "nopat": nopat_value,
                "depreciation": normalized_series["depreciation"][index],
                "capex": normalized_series["capex"][index],
                "change_in_nwc": normalized_series["change_in_nwc"][index],
                "fcff": fcff_value,
                "wacc": normalized_wacc,
            }
        )

    cumulative_discount_factors = _build_cumulative_discount_factors([normalized_wacc] * projection_years, "wacc")
    schedule: list[AdvancedFCFFYear] = []
    pv_forecast_cash_flows = 0.0

    for row, cumulative_discount_factor in zip(intermediate_rows, cumulative_discount_factors, strict=True):
        discounted_fcff = float(row["fcff"]) / cumulative_discount_factor
        schedule.append(
            AdvancedFCFFYear(
                year=int(row["year"]),
                revenue=float(row["revenue"]),
                ebit_margin=float(row["ebit_margin"]),
                ebit=float(row["ebit"]),
                tax_rate=float(row["tax_rate"]),
                nopat=float(row["nopat"]),
                depreciation=float(row["depreciation"]),
                capex=float(row["capex"]),
                change_in_nwc=float(row["change_in_nwc"]),
                fcff=float(row["fcff"]),
                wacc=float(row["wacc"]),
                cumulative_discount_factor=cumulative_discount_factor,
                discounted_fcff=discounted_fcff,
            )
        )
        pv_forecast_cash_flows += discounted_fcff

    terminal_value = yearly_fcff[-1] * (1.0 + terminal_growth) / (normalized_wacc - terminal_growth)
    pv_terminal_value = terminal_value / cumulative_discount_factors[-1]
    enterprise_value = pv_forecast_cash_flows + pv_terminal_value
    equity_value = enterprise_value - normalized_total_debt + normalized_cash
    fair_value_per_share = equity_value / normalized_shares_outstanding

    return FCFFDCFResult(
        pv_forecast_cash_flows=pv_forecast_cash_flows,
        pv_terminal_value=pv_terminal_value,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        terminal_value=terminal_value,
        terminal_wacc=normalized_wacc,
        schedule=schedule,
    )


def calculate_fcfe_dcf_from_drivers(
    revenue: Sequence[float],
    ebit_margin: Sequence[float],
    tax_rate: Sequence[float],
    depreciation: Sequence[float],
    capex: Sequence[float],
    change_in_nwc: Sequence[float],
    net_borrowing: Sequence[float],
    cost_of_equity: float,
    terminal_growth: float,
    shares_outstanding: float,
) -> FCFEDCFResult:
    normalized_series = {
        "revenue": _validate_numeric_list("revenue", revenue),
        "ebit_margin": _validate_numeric_list("ebit_margin", ebit_margin),
        "tax_rate": _validate_numeric_list("tax_rate", tax_rate),
        "depreciation": _validate_numeric_list("depreciation", depreciation),
        "capex": _validate_numeric_list("capex", capex),
        "change_in_nwc": _validate_numeric_list("change_in_nwc", change_in_nwc),
        "net_borrowing": _validate_numeric_list("net_borrowing", net_borrowing),
    }
    projection_years = _validate_matching_lengths("FCFE driver", normalized_series)
    normalized_cost_of_equity = _validate_discount_rate("cost_of_equity", cost_of_equity, terminal_growth)
    normalized_shares_outstanding = _validate_positive("shares_outstanding", shares_outstanding)

    yearly_fcfe: list[float] = []
    intermediate_rows: list[dict[str, float | int]] = []

    for index in range(projection_years):
        year = index + 1
        ebit_value = normalized_series["revenue"][index] * normalized_series["ebit_margin"][index]
        nopat_value = ebit_value * (1.0 - normalized_series["tax_rate"][index])
        fcfe_value = (
            nopat_value
            + normalized_series["depreciation"][index]
            - normalized_series["capex"][index]
            - normalized_series["change_in_nwc"][index]
            + normalized_series["net_borrowing"][index]
        )

        yearly_fcfe.append(fcfe_value)
        intermediate_rows.append(
            {
                "year": year,
                "revenue": normalized_series["revenue"][index],
                "ebit_margin": normalized_series["ebit_margin"][index],
                "ebit": ebit_value,
                "tax_rate": normalized_series["tax_rate"][index],
                "nopat": nopat_value,
                "depreciation": normalized_series["depreciation"][index],
                "capex": normalized_series["capex"][index],
                "change_in_nwc": normalized_series["change_in_nwc"][index],
                "net_borrowing": normalized_series["net_borrowing"][index],
                "fcfe": fcfe_value,
                "cost_of_equity": normalized_cost_of_equity,
            }
        )

    cumulative_discount_factors = _build_cumulative_discount_factors(
        [normalized_cost_of_equity] * projection_years,
        "cost_of_equity",
    )
    schedule: list[AdvancedFCFEYear] = []
    pv_forecast_cash_flows = 0.0

    for row, cumulative_discount_factor in zip(intermediate_rows, cumulative_discount_factors, strict=True):
        discounted_fcfe = float(row["fcfe"]) / cumulative_discount_factor
        schedule.append(
            AdvancedFCFEYear(
                year=int(row["year"]),
                revenue=float(row["revenue"]),
                ebit_margin=float(row["ebit_margin"]),
                ebit=float(row["ebit"]),
                tax_rate=float(row["tax_rate"]),
                nopat=float(row["nopat"]),
                depreciation=float(row["depreciation"]),
                capex=float(row["capex"]),
                change_in_nwc=float(row["change_in_nwc"]),
                net_borrowing=float(row["net_borrowing"]),
                fcfe=float(row["fcfe"]),
                cost_of_equity=float(row["cost_of_equity"]),
                cumulative_discount_factor=cumulative_discount_factor,
                discounted_fcfe=discounted_fcfe,
            )
        )
        pv_forecast_cash_flows += discounted_fcfe

    terminal_value = yearly_fcfe[-1] * (1.0 + terminal_growth) / (normalized_cost_of_equity - terminal_growth)
    pv_terminal_value = terminal_value / cumulative_discount_factors[-1]
    equity_value = pv_forecast_cash_flows + pv_terminal_value
    fair_value_per_share = equity_value / normalized_shares_outstanding

    return FCFEDCFResult(
        pv_forecast_cash_flows=pv_forecast_cash_flows,
        pv_terminal_value=pv_terminal_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        terminal_value=terminal_value,
        terminal_cost_of_equity=normalized_cost_of_equity,
        schedule=schedule,
    )


__all__ = [
    "AdvancedFCFEYear",
    "AdvancedFCFFYear",
    "FCFEDCFResult",
    "FCFFDCFResult",
    "SimpleDCFYear",
    "calculate_fcfe_dcf_from_drivers",
    "calculate_fcfe_dcf_simple",
    "calculate_fcff_dcf_from_drivers",
    "calculate_fcff_dcf_simple",
]
