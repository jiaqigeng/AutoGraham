from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ValuationResult:
	"""Deterministic valuation output shared by manual and AI workflows."""

	model_label: str
	stage_label: str
	equity_value: float
	fair_value_per_share: float
	current_price: float
	margin_of_safety: float | None
	present_value_of_cash_flows: float
	discounted_terminal_value: float
	schedule: list[dict[str, float | int | str]] = field(default_factory=list)
	enterprise_value: float | None = None
	tax_shield_value: float | None = None
