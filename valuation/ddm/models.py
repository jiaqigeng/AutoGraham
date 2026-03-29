from __future__ import annotations

from valuation.ddm.schemas import (
    DDMAssumptions,
    DDMInput,
    DDMOutput,
    DDMProjectedYear,
)


def _validate_assumptions(assumptions: DDMAssumptions) -> None:
    if assumptions.projection_years <= 0:
        raise ValueError("projection_years must be greater than 0.")

    if len(assumptions.dividend_growth_rates) != assumptions.projection_years:
        raise ValueError(
            "dividend_growth_rates must contain one value per projected year."
        )

    if assumptions.cost_of_equity <= -1:
        raise ValueError("cost_of_equity must be greater than -1.0.")

    if assumptions.terminal_growth_rate <= -1:
        raise ValueError("terminal_growth_rate must be greater than -1.0.")

    if assumptions.terminal_growth_rate >= assumptions.cost_of_equity:
        raise ValueError("terminal_growth_rate must be less than cost_of_equity.")


def _validate_inputs(ddm_input: DDMInput) -> None:
    market_data = ddm_input.market_data

    if market_data.current_dividend_per_share < 0:
        raise ValueError("current_dividend_per_share must be non-negative.")

    if market_data.shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be greater than 0.")

    if market_data.current_price is not None and market_data.current_price <= 0:
        raise ValueError("current_price must be greater than 0 when provided.")

    _validate_assumptions(ddm_input.assumptions)


def _project_years(ddm_input: DDMInput) -> list[DDMProjectedYear]:
    assumptions = ddm_input.assumptions
    projected_years: list[DDMProjectedYear] = []
    prior_dividend = ddm_input.market_data.current_dividend_per_share

    for index in range(assumptions.projection_years):
        year = index + 1
        growth_rate = assumptions.dividend_growth_rates[index]
        dividend_per_share = prior_dividend * (1 + growth_rate)
        discount_factor = 1 / ((1 + assumptions.cost_of_equity) ** year)
        present_value_dividend = dividend_per_share * discount_factor

        projected_years.append(
            DDMProjectedYear(
                year=year,
                dividend_per_share=dividend_per_share,
                growth_rate=growth_rate,
                discount_factor=discount_factor,
                present_value_dividend=present_value_dividend,
            )
        )

        prior_dividend = dividend_per_share

    return projected_years


def calculate_ddm(ddm_input: DDMInput) -> DDMOutput:
    """Run a multi-stage dividend discount model using yearly dividend growth assumptions."""
    _validate_inputs(ddm_input)

    projected_years = _project_years(ddm_input)
    if not projected_years:
        raise ValueError("DDM projection produced no projected years.")

    assumptions = ddm_input.assumptions
    market_data = ddm_input.market_data
    final_year = projected_years[-1]

    terminal_dividend_per_share = final_year.dividend_per_share * (
        1 + assumptions.terminal_growth_rate
    )
    terminal_value_per_share = terminal_dividend_per_share / (
        assumptions.cost_of_equity - assumptions.terminal_growth_rate
    )
    present_value_terminal_value = (
        terminal_value_per_share * final_year.discount_factor
    )
    pv_of_projected_dividends = sum(
        year.present_value_dividend for year in projected_years
    )
    fair_value_per_share = (
        pv_of_projected_dividends + present_value_terminal_value
    )
    equity_value = fair_value_per_share * market_data.shares_outstanding

    upside_downside_pct: float | None = None
    if market_data.current_price is not None:
        upside_downside_pct = (
            fair_value_per_share - market_data.current_price
        ) / market_data.current_price

    terminal_value_pct_of_fair_value = 0.0
    if fair_value_per_share != 0:
        terminal_value_pct_of_fair_value = (
            present_value_terminal_value / fair_value_per_share
        )

    return DDMOutput(
        projected_years=projected_years,
        terminal_dividend_per_share=terminal_dividend_per_share,
        terminal_value_per_share=terminal_value_per_share,
        present_value_terminal_value=present_value_terminal_value,
        pv_of_projected_dividends=pv_of_projected_dividends,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        current_price=market_data.current_price,
        upside_downside_pct=upside_downside_pct,
        terminal_value_pct_of_fair_value=terminal_value_pct_of_fair_value,
        assumptions_used=assumptions,
    )
