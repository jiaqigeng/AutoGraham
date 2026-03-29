from __future__ import annotations

from valuation.ddm.models import calculate_ddm
from valuation.ddm.schemas import DDMAssumptions, DDMInput, DDMMarketData, DDMOutput


def prepare_ddm_input(ddm_input: DDMInput) -> DDMInput:
    """Return a defensive copy of the DDM input before calculation."""
    if ddm_input is None:
        raise ValueError("ddm_input is required.")

    if ddm_input.market_data is None:
        raise ValueError("ddm_input.market_data is required.")

    if ddm_input.assumptions is None:
        raise ValueError("ddm_input.assumptions is required.")

    market_data = ddm_input.market_data
    assumptions = ddm_input.assumptions

    prepared_market_data = DDMMarketData(
        current_dividend_per_share=market_data.current_dividend_per_share,
        shares_outstanding=market_data.shares_outstanding,
        current_price=market_data.current_price,
    )

    prepared_assumptions = DDMAssumptions(
        projection_years=assumptions.projection_years,
        dividend_growth_rates=list(assumptions.dividend_growth_rates),
        cost_of_equity=assumptions.cost_of_equity,
        terminal_growth_rate=assumptions.terminal_growth_rate,
    )

    return DDMInput(
        market_data=prepared_market_data,
        assumptions=prepared_assumptions,
    )


def run_ddm_valuation(ddm_input: DDMInput) -> DDMOutput:
    """Prepare the app-facing input object and return the model output."""
    prepared_input = prepare_ddm_input(ddm_input)
    return calculate_ddm(prepared_input)
