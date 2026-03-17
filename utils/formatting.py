from __future__ import annotations

import math


def safe_number(value: object) -> float:
	if value is None:
		return 0.0
	try:
		numeric_value = float(value)
	except (TypeError, ValueError):
		return 0.0
	if math.isnan(numeric_value):
		return 0.0
	return numeric_value


def format_compact_currency(value: object) -> str:
	amount = safe_number(value)
	if amount == 0:
		return "$0.00"
	prefix = "-" if amount < 0 else ""
	abs_amount = abs(amount)
	if abs_amount >= 1_000_000_000_000:
		return f"{prefix}${abs_amount / 1_000_000_000_000:,.2f}T"
	if abs_amount >= 1_000_000_000:
		return f"{prefix}${abs_amount / 1_000_000_000:,.2f}B"
	if abs_amount >= 1_000_000:
		return f"{prefix}${abs_amount / 1_000_000:,.2f}M"
	return f"{prefix}${abs_amount:,.2f}"


def format_market_cap(value: object) -> str:
	market_cap = safe_number(value)
	if market_cap <= 0:
		return "N/A"
	return format_compact_currency(market_cap)


def format_price(value: object) -> str:
	price = safe_number(value)
	if price <= 0:
		return "N/A"
	return f"${price:,.2f}"


def format_ratio(value: object) -> str:
	ratio = safe_number(value)
	if ratio <= 0:
		return "N/A"
	return f"{ratio:,.2f}"


def format_percent(value: object, *, allow_negative: bool = False) -> str:
	rate = safe_number(value)
	if not allow_negative and rate < 0:
		return "N/A"
	if abs(rate) > 0.25:
		rate = rate / 100
	return f"{rate:.2%}"


def format_shares(value: object) -> str:
	shares = safe_number(value)
	if shares <= 0:
		return "N/A"
	return f"{shares:,.0f}"
