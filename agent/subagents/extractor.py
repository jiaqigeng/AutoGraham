from __future__ import annotations

import re
from typing import Any, Mapping

from agent.deep_agent import invoke_text_prompt
from agent.prompts.extraction_prompts import build_extraction_prompt
from agent.schemas import CandidateFact
from agent.tools.finance_tools import resolve_stock_info
from agent.tools.validation_tools import extract_json_array
from valuation.common import default_valuation_inputs


def _base_candidate_facts(stock_data: Any) -> list[dict[str, Any]]:
	"""Create deterministic candidate facts from the available market-data bundle."""

	info = resolve_stock_info(stock_data)
	defaults = default_valuation_inputs(
		info,
		annual_cashflow=getattr(stock_data, "annual_cashflow", None),
		annual_balance_sheet=getattr(stock_data, "annual_balance_sheet", None),
		annual_income_stmt=getattr(stock_data, "annual_income_stmt", None),
	)
	facts = [
		CandidateFact(key="sector", label="Sector", value=str(info.get("sector") or "N/A"), source="Yahoo Finance", confidence=0.9),
		CandidateFact(key="industry", label="Industry", value=str(info.get("industry") or "N/A"), source="Yahoo Finance", confidence=0.9),
		CandidateFact(key="current_price", label="Current Price", value=defaults["current_price"], numeric_value=defaults["current_price"], source="Yahoo Finance", confidence=0.95),
		CandidateFact(key="shares_outstanding", label="Shares Outstanding", value=defaults["shares_outstanding"], numeric_value=defaults["shares_outstanding"], source="Derived from market data", confidence=0.8),
		CandidateFact(key="starting_fcff", label="Starting FCFF", value=defaults["starting_fcff"], numeric_value=defaults["starting_fcff"], source="Derived from financial statements", confidence=0.8),
		CandidateFact(key="starting_fcfe", label="Starting FCFE", value=defaults["starting_fcfe"], numeric_value=defaults["starting_fcfe"], source="Derived from financial statements", confidence=0.8),
		CandidateFact(key="dividend_per_share", label="Dividend Per Share", value=defaults["dividend_per_share"], numeric_value=defaults["dividend_per_share"], source="Yahoo Finance", confidence=0.9),
		CandidateFact(key="book_value_per_share", label="Book Value Per Share", value=defaults["book_value_per_share"], numeric_value=defaults["book_value_per_share"], source="Yahoo Finance / balance sheet", confidence=0.85),
		CandidateFact(key="return_on_equity", label="Observed ROE", value=defaults["return_on_equity"], numeric_value=defaults["return_on_equity"], source="Yahoo Finance / derived", confidence=0.8),
		CandidateFact(key="payout_ratio", label="Observed Payout Ratio", value=defaults["payout_ratio"], numeric_value=defaults["payout_ratio"], source="Yahoo Finance / derived", confidence=0.8),
	]
	return [fact.model_dump() for fact in facts]


def _extract_target_mentions(research_report: str) -> list[dict[str, Any]]:
	"""Capture loose management-target clues from free-form research text."""

	facts: list[dict[str, Any]] = []
	for match in re.finditer(r"(?P<context>.{0,40})(?P<value>\d+(?:\.\d+)?)%(?P<trailing>.{0,40})", research_report, flags=re.IGNORECASE):
		context = f"{match.group('context')}{match.group('value')}%{match.group('trailing')}".strip()
		facts.append(
			CandidateFact(
				key="management_target_hint",
				label="Management Target Mention",
				value=context,
				source="Research memo",
				citation=context[:160],
				confidence=0.35,
				note="Loose percentage mention extracted from messy text; treat as directional context only.",
			).model_dump()
		)
		if len(facts) >= 3:
			break
	return facts


def _merge_candidate_facts(*fact_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Merge fact lists by key while preserving the highest-confidence entries."""

	merged: dict[str, dict[str, Any]] = {}
	for group in fact_groups:
		for fact in group:
			key = str(fact.get("key") or fact.get("label") or "").strip()
			if not key:
				continue
			current = merged.get(key)
			if current is None or float(fact.get("confidence") or 0) >= float(current.get("confidence") or 0):
				merged[key] = fact
	return list(merged.values())


def extract_candidate_facts(
	ticker: str,
	stock_data: Any,
	research_report: str,
	source_notes: list[Mapping[str, Any]],
	model_name: str | None = None,
) -> list[dict[str, Any]]:
	"""Turn messy source text into candidate facts that tolerate uncertainty."""

	base_facts = _base_candidate_facts(stock_data)
	narrative_facts = _extract_target_mentions(research_report)
	llm_facts: list[dict[str, Any]] = []

	llm_text = invoke_text_prompt(
		system_prompt="Return JSON only.",
		user_prompt=build_extraction_prompt(ticker, research_report, source_notes),
		model_name=model_name,
		temperature=0.0,
	)
	if llm_text:
		try:
			llm_facts = [
				CandidateFact.model_validate(item).model_dump()
				for item in extract_json_array(llm_text)
			]
		except Exception:
			llm_facts = []

	return _merge_candidate_facts(base_facts, narrative_facts, llm_facts)
