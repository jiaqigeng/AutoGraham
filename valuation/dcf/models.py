from __future__ import annotations

from valuation.dcf.schemas import (
    DCFAssumptions,
    DCFInput,
    DCFOutput,
    DCFProjectedYear,
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


def _validate_assumptions(assumptions: DCFAssumptions) -> None:
    if assumptions.projection_years <= 0:
        raise ValueError("projection_years must be greater than 0.")

    if len(assumptions.revenue_growth_rates) != assumptions.projection_years:
        raise ValueError(
            "revenue_growth_rates must contain one value per projected year."
        )

    if len(assumptions.ebit_margins) != assumptions.projection_years:
        raise ValueError("ebit_margins must contain one value per projected year.")

    _expand_series(assumptions.tax_rates, assumptions.projection_years, "tax_rates")
    _expand_series(
        assumptions.da_as_pct_revenue,
        assumptions.projection_years,
        "da_as_pct_revenue",
    )
    _expand_series(
        assumptions.capex_as_pct_revenue,
        assumptions.projection_years,
        "capex_as_pct_revenue",
    )
    _expand_series(
        assumptions.nwc_as_pct_revenue,
        assumptions.projection_years,
        "nwc_as_pct_revenue",
    )

    if assumptions.wacc <= -1:
        raise ValueError("wacc must be greater than -1.0.")

    if assumptions.exit_multiple < 0:
        raise ValueError("exit_multiple must be non-negative.")


def _validate_inputs(dcf_input: DCFInput) -> None:
    market_data = dcf_input.market_data
    assumptions = dcf_input.assumptions

    if market_data.current_revenue < 0:
        raise ValueError("current_revenue must be non-negative.")

    if market_data.shares_outstanding <= 0:
        raise ValueError("shares_outstanding must be greater than 0.")

    _validate_assumptions(assumptions)


def _build_projection_inputs(assumptions: DCFAssumptions) -> tuple[
    list[float],
    list[float],
    list[float],
    list[float],
]:
    return (
        _expand_series(assumptions.tax_rates, assumptions.projection_years, "tax_rates"),
        _expand_series(
            assumptions.da_as_pct_revenue,
            assumptions.projection_years,
            "da_as_pct_revenue",
        ),
        _expand_series(
            assumptions.capex_as_pct_revenue,
            assumptions.projection_years,
            "capex_as_pct_revenue",
        ),
        _expand_series(
            assumptions.nwc_as_pct_revenue,
            assumptions.projection_years,
            "nwc_as_pct_revenue",
        ),
    )


def _project_years(dcf_input: DCFInput) -> list[DCFProjectedYear]:
    assumptions = dcf_input.assumptions
    tax_rates, da_rates, capex_rates, nwc_rates = _build_projection_inputs(assumptions)

    projected_years: list[DCFProjectedYear] = []
    prior_revenue = dcf_input.market_data.current_revenue

    for index in range(assumptions.projection_years):
        year = index + 1
        growth_rate = assumptions.revenue_growth_rates[index]
        revenue = prior_revenue * (1 + growth_rate)
        ebit_margin = assumptions.ebit_margins[index]
        ebit = revenue * ebit_margin

        tax_rate = tax_rates[index]
        taxes = ebit * tax_rate
        nopat = ebit - taxes

        depreciation_amortization = revenue * da_rates[index]
        ebitda = ebit + depreciation_amortization
        capex = revenue * capex_rates[index]
        change_in_nwc = revenue * nwc_rates[index]
        fcff = nopat + depreciation_amortization - capex - change_in_nwc

        discount_factor = 1 / ((1 + assumptions.wacc) ** year)
        present_value_fcff = fcff * discount_factor

        projected_years.append(
            DCFProjectedYear(
                year=year,
                revenue=revenue,
                ebit=ebit,
                ebit_margin=ebit_margin,
                taxes=taxes,
                nopat=nopat,
                depreciation_amortization=depreciation_amortization,
                ebitda=ebitda,
                capex=capex,
                change_in_nwc=change_in_nwc,
                fcff=fcff,
                discount_factor=discount_factor,
                present_value_fcff=present_value_fcff,
            )
        )

        prior_revenue = revenue

    return projected_years


def calculate_dcf(dcf_input: DCFInput) -> DCFOutput:
    """Run a DCF valuation using yearly operating assumptions."""
    _validate_inputs(dcf_input)

    projected_years = _project_years(dcf_input)
    if not projected_years:
        raise ValueError("DCF projection produced no projected years.")

    assumptions = dcf_input.assumptions
    market_data = dcf_input.market_data
    final_year = projected_years[-1]

    terminal_ebitda = final_year.ebitda
    terminal_value = terminal_ebitda * assumptions.exit_multiple
    present_value_terminal_value = terminal_value * final_year.discount_factor
    pv_of_projected_fcff = sum(year.present_value_fcff for year in projected_years)
    enterprise_value = pv_of_projected_fcff + present_value_terminal_value
    equity_value = enterprise_value + market_data.cash - market_data.total_debt
    fair_value_per_share = equity_value / market_data.shares_outstanding

    upside_downside_pct: float | None = None
    if market_data.current_price is not None:
        if market_data.current_price <= 0:
            raise ValueError("current_price must be greater than 0 when provided.")
        upside_downside_pct = (
            fair_value_per_share - market_data.current_price
        ) / market_data.current_price

    terminal_value_pct_of_enterprise_value = 0.0
    if enterprise_value != 0:
        terminal_value_pct_of_enterprise_value = terminal_value / enterprise_value

    return DCFOutput(
        projected_years=projected_years,
        terminal_ebitda=terminal_ebitda,
        exit_multiple=assumptions.exit_multiple,
        terminal_value=terminal_value,
        present_value_terminal_value=present_value_terminal_value,
        pv_of_projected_fcff=pv_of_projected_fcff,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        fair_value_per_share=fair_value_per_share,
        current_price=market_data.current_price,
        upside_downside_pct=upside_downside_pct,
        terminal_value_pct_of_enterprise_value=terminal_value_pct_of_enterprise_value,
        assumptions_used=assumptions,
    )
