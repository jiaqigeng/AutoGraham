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
class RIMMarketData:
    current_book_value_per_share: float
    shares_outstanding: float
    current_price: float | None = None

    def __post_init__(self) -> None:
        if self.current_book_value_per_share < 0:
            raise ValueError("current_book_value_per_share must be non-negative.")

        if self.shares_outstanding <= 0:
            raise ValueError("shares_outstanding must be greater than 0.")


@dataclass(slots=True)
class RIMAssumptions:
    projection_years: int
    return_on_equity: list[float]
    payout_ratios: ScalarOrList
    cost_of_equity: float
    terminal_return_on_equity: float
    terminal_growth_rate: float

    def __post_init__(self) -> None:
        if self.projection_years <= 0:
            raise ValueError("projection_years must be greater than 0.")

        if len(self.return_on_equity) != self.projection_years:
            raise ValueError(
                "return_on_equity must contain one value per projected year."
            )

        _validate_projection_series_length(
            self.payout_ratios, self.projection_years, "payout_ratios"
        )

        if self.cost_of_equity <= -1:
            raise ValueError("cost_of_equity must be greater than -1.0.")

        if self.terminal_growth_rate <= -1:
            raise ValueError("terminal_growth_rate must be greater than -1.0.")

        if self.terminal_growth_rate >= self.cost_of_equity:
            raise ValueError(
                "terminal_growth_rate must be less than cost_of_equity."
            )


@dataclass(slots=True)
class RIMInput:
    market_data: RIMMarketData
    assumptions: RIMAssumptions


@dataclass(slots=True)
class RIMProjectedYear:
    year: int
    beginning_book_value_per_share: float
    ending_book_value_per_share: float
    return_on_equity: float
    earnings_per_share: float
    payout_ratio: float
    dividends_per_share: float
    retained_earnings_per_share: float
    residual_income_per_share: float
    discount_factor: float
    present_value_residual_income: float


@dataclass(slots=True)
class RIMOutput:
    projected_years: list[RIMProjectedYear] = field(default_factory=list)
    terminal_book_value_per_share: float = 0.0
    terminal_return_on_equity: float = 0.0
    terminal_residual_income_per_share: float = 0.0
    terminal_value_per_share: float = 0.0
    present_value_terminal_value: float = 0.0
    pv_of_projected_residual_income: float = 0.0
    equity_value: float = 0.0
    fair_value_per_share: float = 0.0
    current_price: float | None = None
    upside_downside_pct: float | None = None
    terminal_value_pct_of_fair_value: float = 0.0
    assumptions_used: RIMAssumptions | None = None
