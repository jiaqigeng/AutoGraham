from __future__ import annotations

from dataclasses import dataclass, field


ScalarOrList = float | list[float]


def _validate_projection_series_length(
    value: ScalarOrList,
    projection_years: int,
    field_name: str,
) -> None:
    if isinstance(value, list) and len(value) != projection_years:
        raise ValueError(
            f"{field_name} must contain {projection_years} values when provided as a list."
        )


@dataclass(slots=True)
class DCFMarketData:
    current_revenue: float
    current_ebit: float
    tax_rate: float
    depreciation_amortization: float
    capex: float
    change_in_nwc: float
    cash: float
    total_debt: float
    shares_outstanding: float
    current_price: float | None = None

    def __post_init__(self) -> None:
        if self.shares_outstanding <= 0:
            raise ValueError("shares_outstanding must be greater than 0.")


@dataclass(slots=True)
class DCFAssumptions:
    projection_years: int
    revenue_growth_rates: list[float]
    ebit_margins: list[float]
    tax_rates: ScalarOrList
    da_as_pct_revenue: ScalarOrList
    capex_as_pct_revenue: ScalarOrList
    nwc_as_pct_revenue: ScalarOrList
    wacc: float
    exit_multiple: float

    def __post_init__(self) -> None:
        if self.projection_years <= 0:
            raise ValueError("projection_years must be greater than 0.")

        if len(self.revenue_growth_rates) != self.projection_years:
            raise ValueError(
                "revenue_growth_rates must contain one value per projected year."
            )

        if len(self.ebit_margins) != self.projection_years:
            raise ValueError("ebit_margins must contain one value per projected year.")

        _validate_projection_series_length(
            self.tax_rates, self.projection_years, "tax_rates"
        )
        _validate_projection_series_length(
            self.da_as_pct_revenue, self.projection_years, "da_as_pct_revenue"
        )
        _validate_projection_series_length(
            self.capex_as_pct_revenue, self.projection_years, "capex_as_pct_revenue"
        )
        _validate_projection_series_length(
            self.nwc_as_pct_revenue, self.projection_years, "nwc_as_pct_revenue"
        )


@dataclass(slots=True)
class DCFInput:
    market_data: DCFMarketData
    assumptions: DCFAssumptions


@dataclass(slots=True)
class DCFProjectedYear:
    year: int
    revenue: float
    ebit: float
    ebit_margin: float
    taxes: float
    nopat: float
    depreciation_amortization: float
    ebitda: float
    capex: float
    change_in_nwc: float
    fcff: float
    discount_factor: float
    present_value_fcff: float


@dataclass(slots=True)
class DCFOutput:
    projected_years: list[DCFProjectedYear] = field(default_factory=list)
    terminal_ebitda: float = 0.0
    exit_multiple: float = 0.0
    terminal_value: float = 0.0
    present_value_terminal_value: float = 0.0
    pv_of_projected_fcff: float = 0.0
    enterprise_value: float = 0.0
    equity_value: float = 0.0
    fair_value_per_share: float = 0.0
    current_price: float | None = None
    upside_downside_pct: float | None = None
    terminal_value_pct_of_enterprise_value: float = 0.0
    assumptions_used: DCFAssumptions | None = None
