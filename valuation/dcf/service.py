from __future__ import annotations

from valuation.dcf.models import calculate_dcf
from valuation.dcf.schemas import DCFAssumptions, DCFInput, DCFMarketData, DCFOutput


def _copy_series(value: float | list[float]) -> float | list[float]:
    if isinstance(value, list):
        return list(value)
    return value


def prepare_dcf_input(dcf_input: DCFInput) -> DCFInput:
    """Return a defensive copy of the DCF input before calculation."""
    if dcf_input is None:
        raise ValueError("dcf_input is required.")

    if dcf_input.market_data is None:
        raise ValueError("dcf_input.market_data is required.")

    if dcf_input.assumptions is None:
        raise ValueError("dcf_input.assumptions is required.")

    market_data = dcf_input.market_data
    assumptions = dcf_input.assumptions

    prepared_market_data = DCFMarketData(
        current_revenue=market_data.current_revenue,
        current_ebit=market_data.current_ebit,
        tax_rate=market_data.tax_rate,
        depreciation_amortization=market_data.depreciation_amortization,
        capex=market_data.capex,
        change_in_nwc=market_data.change_in_nwc,
        cash=market_data.cash,
        total_debt=market_data.total_debt,
        shares_outstanding=market_data.shares_outstanding,
        current_price=market_data.current_price,
    )

    prepared_assumptions = DCFAssumptions(
        projection_years=assumptions.projection_years,
        revenue_growth_rates=list(assumptions.revenue_growth_rates),
        ebit_margins=list(assumptions.ebit_margins),
        tax_rates=_copy_series(assumptions.tax_rates),
        da_as_pct_revenue=_copy_series(assumptions.da_as_pct_revenue),
        capex_as_pct_revenue=_copy_series(assumptions.capex_as_pct_revenue),
        nwc_as_pct_revenue=_copy_series(assumptions.nwc_as_pct_revenue),
        wacc=assumptions.wacc,
        exit_multiple=assumptions.exit_multiple,
    )

    return DCFInput(
        market_data=prepared_market_data,
        assumptions=prepared_assumptions,
    )


def run_dcf_valuation(dcf_input: DCFInput) -> DCFOutput:
    """Prepare the app-facing input object and return the model output."""
    prepared_input = prepare_dcf_input(dcf_input)
    return calculate_dcf(prepared_input)
