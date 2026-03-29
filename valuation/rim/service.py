from __future__ import annotations

from valuation.rim.models import calculate_rim
from valuation.rim.schemas import RIMAssumptions, RIMInput, RIMMarketData, RIMOutput


def _copy_series(value: float | list[float]) -> float | list[float]:
    if isinstance(value, list):
        return list(value)
    return value


def prepare_rim_input(rim_input: RIMInput) -> RIMInput:
    """Return a defensive copy of the RIM input before calculation."""
    if rim_input is None:
        raise ValueError("rim_input is required.")

    if rim_input.market_data is None:
        raise ValueError("rim_input.market_data is required.")

    if rim_input.assumptions is None:
        raise ValueError("rim_input.assumptions is required.")

    market_data = rim_input.market_data
    assumptions = rim_input.assumptions

    prepared_market_data = RIMMarketData(
        current_book_value_per_share=market_data.current_book_value_per_share,
        shares_outstanding=market_data.shares_outstanding,
        current_price=market_data.current_price,
    )

    prepared_assumptions = RIMAssumptions(
        projection_years=assumptions.projection_years,
        return_on_equity=list(assumptions.return_on_equity),
        payout_ratios=_copy_series(assumptions.payout_ratios),
        cost_of_equity=assumptions.cost_of_equity,
        terminal_return_on_equity=assumptions.terminal_return_on_equity,
        terminal_growth_rate=assumptions.terminal_growth_rate,
    )

    return RIMInput(
        market_data=prepared_market_data,
        assumptions=prepared_assumptions,
    )


def run_rim_valuation(rim_input: RIMInput) -> RIMOutput:
    """Prepare the app-facing input object and return the model output."""
    prepared_input = prepare_rim_input(rim_input)
    return calculate_rim(prepared_input)
