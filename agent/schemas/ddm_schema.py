from __future__ import annotations

from agent.schemas.common import FlexibleSchema


class DDMSchema(FlexibleSchema):
	"""Model-ready DDM boundary schema."""

	selected_variant: str | None = None
	current_price: float | None = None
	shares_outstanding: float | None = None
	current_dividend_per_share: float | None = None
	required_return: float | None = None
	high_growth: float | None = None
	stable_growth: float | None = None
	terminal_growth: float | None = None
	short_term_growth: float | None = None
	projection_years: float | None = None
	high_growth_years: float | None = None
	transition_years: float | None = None
	half_life_years: float | None = None
