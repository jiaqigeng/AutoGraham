from __future__ import annotations

from agent.schemas.common import FlexibleSchema


class RIMSchema(FlexibleSchema):
	"""Model-ready RIM boundary schema."""

	current_price: float | None = None
	shares_outstanding: float | None = None
	book_value_per_share: float | None = None
	return_on_equity: float | None = None
	cost_of_equity: float | None = None
	payout_ratio: float | None = None
	projection_years: float | None = None
	terminal_growth: float | None = None
