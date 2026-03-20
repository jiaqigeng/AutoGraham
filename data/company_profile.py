from __future__ import annotations

from typing import Any, Mapping

from valuation.common import safe_number


def company_descriptor(info: Mapping[str, Any]) -> str:
	return " ".join(
		str(info.get(key) or "").lower()
		for key in ("sector", "industry", "longBusinessSummary", "shortName", "longName")
	)


def info_supports_analysis(info: Mapping[str, Any]) -> bool:
	quote_type = str(info.get("quoteType") or "").upper()
	if quote_type and quote_type != "EQUITY":
		return False
	if info.get("shortName") or info.get("longName"):
		return True
	if info.get("currentPrice") is not None or info.get("regularMarketPrice") is not None:
		return True
	return False


def is_financial_company(info: Mapping[str, Any]) -> bool:
	descriptor = company_descriptor(info)
	financial_keywords = (
		"financial services",
		"bank",
		"insurance",
		"asset management",
		"capital markets",
		"credit services",
		"brokerage",
		"exchange",
		"payment processing",
	)
	return any(keyword in descriptor for keyword in financial_keywords)


def is_tech_or_platform_company(info: Mapping[str, Any]) -> bool:
	descriptor = company_descriptor(info)
	tech_keywords = (
		"technology",
		"software",
		"internet",
		"semiconductor",
		"cloud",
		"communication services",
		"interactive media",
		"digital advertising",
		"consumer electronics",
	)
	return any(keyword in descriptor for keyword in tech_keywords)


def is_dividend_model_candidate(info: Mapping[str, Any], defaults: Mapping[str, float], focus_text: str) -> bool:
	descriptor = company_descriptor(info)
	dividend_positive = defaults["dividend_per_share"] > 0
	payout_meaningful = defaults["payout_ratio"] >= 0.25 or safe_number(info.get("dividendYield")) >= 0.015
	income_focus = any(keyword in focus_text for keyword in ("income", "yield", "dividend"))
	mature_income_profile = any(
		keyword in descriptor
		for keyword in ("utility", "telecom", "reit", "real estate", "pipeline", "consumer defensive", "insurance", "bank")
	)
	return dividend_positive and (payout_meaningful or income_focus or mature_income_profile)
