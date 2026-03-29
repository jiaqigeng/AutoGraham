from __future__ import annotations

from valuation.rim.schemas import (
    RIMAssumptions,
    RIMInput,
    RIMOutput,
    RIMProjectedYear,
    ScalarOrList,
)


def _expand_series(
    value: ScalarOrList,
    projection_years: int,
    field_name: str,
) -> list[float]:
    if isinstance(value, list):
        if len(value) != projection_years:
            raise ValueError(
                f"{field_name} must contain {projection_years} values when provided as a list."
            )
        return value

    return [value] * projection_years


def _validate_assumptions(assumptions: RIMAssumptions) -> None:
    if assumptions.projection_years <= 0:
        raise ValueError("projection_years must be greater than 0.")

    if len(assumptions.return_on_equity) != assumptions.projection_years:
        raise ValueError(
            "return_on_equity must contain one value per projected year."
        )

    _expand_series(
        assumptions.payout_ratios, assumptions.projection_years, "payout_ratios"
    )

    if assumptions.cost_of_equity <= -1:
        raise ValueError("cost_of_equity must be greater than -1.0.")

    if assumptions.terminal_growth_rate <= -1:
        raise ValueError("terminal_growth_rate must be greater than -1.0.")

    if assumptions.terminal_growth_rate >= assumptions.cost_of_equity:
        raise ValueError("terminal_growth_rate must be less than cost_of_equity.")


def _validate_inputs(rim_input: RIMInput) -> None:
    market_data = rim_input.market_data

    if market_data.current_book_value_per_share < 0:
        raise ValueError("current_book_value_per_share must be non-negative.")

    if market_data.shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be greater than 0.")

    if market_data.current_price is not None and market_data.current_price <= 0:
        raise ValueError("current_price must be greater than 0 when provided.")

    _validate_assumptions(rim_input.assumptions)


def _project_years(rim_input: RIMInput) -> list[RIMProjectedYear]:
    assumptions = rim_input.assumptions
    payout_ratios = _expand_series(
        assumptions.payout_ratios, assumptions.projection_years, "payout_ratios"
    )

    projected_years: list[RIMProjectedYear] = []
    beginning_book_value_per_share = rim_input.market_data.current_book_value_per_share

    for index in range(assumptions.projection_years):
        year = index + 1
        return_on_equity = assumptions.return_on_equity[index]
        payout_ratio = payout_ratios[index]

        earnings_per_share = beginning_book_value_per_share * return_on_equity
        dividends_per_share = earnings_per_share * payout_ratio
        retained_earnings_per_share = earnings_per_share - dividends_per_share
        ending_book_value_per_share = (
            beginning_book_value_per_share + retained_earnings_per_share
        )
        residual_income_per_share = (
            beginning_book_value_per_share
            * (return_on_equity - assumptions.cost_of_equity)
        )
        discount_factor = 1 / ((1 + assumptions.cost_of_equity) ** year)
        present_value_residual_income = residual_income_per_share * discount_factor

        projected_years.append(
            RIMProjectedYear(
                year=year,
                beginning_book_value_per_share=beginning_book_value_per_share,
                ending_book_value_per_share=ending_book_value_per_share,
                return_on_equity=return_on_equity,
                earnings_per_share=earnings_per_share,
                payout_ratio=payout_ratio,
                dividends_per_share=dividends_per_share,
                retained_earnings_per_share=retained_earnings_per_share,
                residual_income_per_share=residual_income_per_share,
                discount_factor=discount_factor,
                present_value_residual_income=present_value_residual_income,
            )
        )

        beginning_book_value_per_share = ending_book_value_per_share

    return projected_years


def calculate_rim(rim_input: RIMInput) -> RIMOutput:
    """Run a residual income model using yearly ROE and payout assumptions."""
    _validate_inputs(rim_input)

    projected_years = _project_years(rim_input)
    if not projected_years:
        raise ValueError("RIM projection produced no projected years.")

    assumptions = rim_input.assumptions
    market_data = rim_input.market_data
    final_year = projected_years[-1]

    terminal_book_value_per_share = final_year.ending_book_value_per_share
    terminal_residual_income_per_share = terminal_book_value_per_share * (
        assumptions.terminal_return_on_equity - assumptions.cost_of_equity
    ) * (1 + assumptions.terminal_growth_rate)
    terminal_value_per_share = terminal_residual_income_per_share / (
        assumptions.cost_of_equity - assumptions.terminal_growth_rate
    )
    present_value_terminal_value = (
        terminal_value_per_share * final_year.discount_factor
    )
    pv_of_projected_residual_income = sum(
        year.present_value_residual_income for year in projected_years
    )
    fair_value_per_share = (
        market_data.current_book_value_per_share
        + pv_of_projected_residual_income
        + present_value_terminal_value
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

    return RIMOutput(
        projected_years=projected_years,
        terminal_book_value_per_share=terminal_book_value_per_share,
        terminal_return_on_equity=assumptions.terminal_return_on_equity,
        terminal_residual_income_per_share=terminal_residual_income_per_share,
        terminal_value_per_share=terminal_value_per_share,
        present_value_terminal_value=present_value_terminal_value,
        pv_of_projected_residual_income=pv_of_projected_residual_income,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        current_price=market_data.current_price,
        upside_downside_pct=upside_downside_pct,
        terminal_value_pct_of_fair_value=terminal_value_pct_of_fair_value,
        assumptions_used=assumptions,
    )
