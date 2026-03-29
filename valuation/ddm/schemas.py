from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DDMMarketData:
    current_dividend_per_share: float
    shares_outstanding: float
    current_price: float | None = None

    def __post_init__(self) -> None:
        if self.current_dividend_per_share < 0:
            raise ValueError("current_dividend_per_share must be non-negative.")

        if self.shares_outstanding <= 0:
            raise ValueError("shares_outstanding must be greater than 0.")


@dataclass(slots=True)
class DDMAssumptions:
    projection_years: int
    dividend_growth_rates: list[float]
    cost_of_equity: float
    terminal_growth_rate: float

    def __post_init__(self) -> None:
        if self.projection_years <= 0:
            raise ValueError("projection_years must be greater than 0.")

        if len(self.dividend_growth_rates) != self.projection_years:
            raise ValueError(
                "dividend_growth_rates must contain one value per projected year."
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
class DDMInput:
    market_data: DDMMarketData
    assumptions: DDMAssumptions


@dataclass(slots=True)
class DDMProjectedYear:
    year: int
    dividend_per_share: float
    growth_rate: float
    discount_factor: float
    present_value_dividend: float


@dataclass(slots=True)
class DDMOutput:
    projected_years: list[DDMProjectedYear] = field(default_factory=list)
    terminal_dividend_per_share: float = 0.0
    terminal_value_per_share: float = 0.0
    present_value_terminal_value: float = 0.0
    pv_of_projected_dividends: float = 0.0
    equity_value: float = 0.0
    fair_value_per_share: float = 0.0
    current_price: float | None = None
    upside_downside_pct: float | None = None
    terminal_value_pct_of_fair_value: float = 0.0
    assumptions_used: DDMAssumptions | None = None
