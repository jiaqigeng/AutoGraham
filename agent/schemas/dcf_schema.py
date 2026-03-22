from __future__ import annotations

from typing import Literal

from agent.schemas.common import FlexibleSchema


class DCFSchema(FlexibleSchema):
	"""Model-ready DCF boundary schema."""

	calculation_model: Literal["FCFF", "FCFE"] = "FCFF"
	selected_variant: str | None = None
	current_price: float | None = None
	shares_outstanding: float | None = None
	starting_fcff: float | None = None
	starting_fcfe: float | None = None
	total_debt: float | None = None
	cash: float | None = None
	wacc: float | list[float] | None = None
	terminal_wacc: float | None = None
	cost_of_equity: float | None = None
	growth_rate: float | None = None
	stable_growth: float | None = None
	high_growth: float | None = None
	projection_years: float | None = None
	high_growth_years: float | None = None
	transition_years: float | None = None
	terminal_growth: float | None = None
