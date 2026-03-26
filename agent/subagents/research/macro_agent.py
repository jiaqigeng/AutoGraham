from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent.llm_utils import invoke_text_prompt
from agent.schemas import CandidateFact
from agent.skill_prompt_loader import build_macro_analysis_prompts
from agent.subagents.research.common import (
	build_analysis_artifact,
	dedupe_links,
	headline_lines,
	infer_competitors,
	load_ingested_artifact,
	note_payload,
	strategic_phase,
	summary_sentence,
)
from agent.tools.finance_tools import build_company_snapshot, build_source_links, resolve_stock_info
from agent.tools.sec_tools import build_source_hints
from valuation.common import safe_number


def _macro_sensitivity(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> str:
	sector = str(snapshot.get("sector") or info.get("sector") or "").strip().lower()
	if sector in {"financial services", "real estate"}:
		return "Interest-rate and credit conditions likely matter more than a typical operating-company cycle."
	if sector in {"energy", "materials", "industrials"}:
		return "Demand, industrial production, and commodity or input-cost swings can materially affect results."
	if sector in {"consumer cyclical", "consumer discretionary"}:
		return "Consumer spending and employment conditions can meaningfully influence performance."
	if sector in {"utilities", "consumer defensive", "healthcare"}:
		return "The business mix looks relatively defensive versus the broader market."
	return "Macro sensitivity appears mixed, with company execution likely mattering as much as the broad cycle."


def _macro_series_lines(macro_payload: Mapping[str, Any]) -> list[str]:
	lines: list[str] = []
	for series in list(macro_payload.get("fred_series") or [])[:4]:
		if not isinstance(series, Mapping):
			continue
		observations = [item for item in list(series.get("observations") or []) if isinstance(item, Mapping)]
		if not observations:
			continue
		latest = observations[0]
		prior = observations[1] if len(observations) > 1 else None
		direction = ""
		latest_value = safe_number(latest.get("value"))
		prior_value = safe_number(prior.get("value")) if prior else None
		if latest_value is not None and prior_value is not None:
			if latest_value > prior_value:
				direction = "up versus the prior reading"
			elif latest_value < prior_value:
				direction = "down versus the prior reading"
		label = str(series.get("label") or series.get("series_id") or "Macro series").strip()
		line = f"- {label}: {latest.get('value')} as of {latest.get('date')}."
		if direction:
			line = f"{line[:-1]}; {direction}."
		lines.append(line)
	return lines


def _signal_bullets(notes: Sequence[Mapping[str, Any]], keywords: Sequence[str], *, max_items: int = 3) -> list[str]:
	lines: list[str] = []
	for note in notes:
		title = str(note.get("title") or "").strip()
		snippet = str(note.get("snippet") or "").strip()
		text = f"{title} {snippet}".lower()
		if any(keyword in text for keyword in keywords):
			lines.append(f"- {title}: {summary_sentence(snippet, max_len=180)}")
		if len(lines) >= max_items:
			break
	return lines


def _macro_candidate_facts(
	snapshot: Mapping[str, Any],
	info: Mapping[str, Any],
	profile: Mapping[str, Any],
	competitors: list[str],
	tailwinds: list[str],
	headwinds: list[str],
) -> list[dict[str, Any]]:
	company_name = str(profile.get("companyName") or snapshot.get("company_name") or info.get("longName") or "").strip()
	sector = str(profile.get("sector") or snapshot.get("sector") or info.get("sector") or "").strip()
	industry = str(profile.get("industry") or snapshot.get("industry") or info.get("industry") or "").strip()
	facts = [
		CandidateFact(
			key="macro_sensitivity",
			label="Macro Sensitivity",
			value=_macro_sensitivity(snapshot, info),
			source="Macro Agent",
			confidence=0.58,
		).model_dump(),
		CandidateFact(
			key="strategic_phase",
			label="Strategic Phase",
			value=strategic_phase(snapshot, info),
			source="Macro Agent",
			confidence=0.6,
		).model_dump(),
	]
	if company_name:
		facts.append(CandidateFact(key="company_name", label="Company Name", value=company_name, source="Company Profile", confidence=0.85).model_dump())
	if sector:
		facts.append(CandidateFact(key="sector", label="Sector", value=sector, source="Company Profile", confidence=0.85).model_dump())
	if industry:
		facts.append(CandidateFact(key="industry", label="Industry", value=industry, source="Company Profile", confidence=0.85).model_dump())
	if competitors:
		facts.append(
			CandidateFact(
				key="competitors",
				label="Primary Competitors",
				value=competitors,
				source="Macro Agent",
				confidence=0.55,
				note="Inferred from stored news and macro-context search results.",
			).model_dump()
		)
	if tailwinds:
		facts.append(CandidateFact(key="tailwinds", label="Tailwinds", value=tailwinds, source="Macro Agent", confidence=0.52).model_dump())
	if headwinds:
		facts.append(CandidateFact(key="headwinds", label="Headwinds", value=headwinds, source="Macro Agent", confidence=0.52).model_dump())
	return facts


def _macro_fallback_report(
	company_name: str,
	sector: str,
	industry: str,
	competitors: list[str],
	macro_lines: list[str],
	company_news_lines: list[str],
	market_news_lines: list[str],
	tailwind_lines: list[str],
	headwind_lines: list[str],
	snapshot: Mapping[str, Any],
	info: Mapping[str, Any],
) -> str:
	return "\n".join(
		[
			"### Sector Setup",
			f"- Company: {company_name}.",
			f"- Sector / industry: {sector or 'Unknown'} / {industry or 'Unknown'}.",
			f"- Strategic phase: {strategic_phase(snapshot, info)}.",
			f"- Macro sensitivity: {_macro_sensitivity(snapshot, info)}",
			"### Competitor Read",
			f"- Primary competitors (inferred): {', '.join(competitors)}." if competitors else "- Competitor inference was limited in the cached evidence.",
			"### Macro Data",
			"\n".join(macro_lines) or "- No FRED macro series were available in the cached ingestion packet.",
			"### Tailwinds (3-5 Years)",
			"\n".join(tailwind_lines) or "- Available evidence points to demand resilience and product-cycle or platform-expansion support, but explicit TAM evidence was limited.",
			"### Headwinds (3-5 Years)",
			"\n".join(headwind_lines) or "- The evidence set did not surface a dominant sector headwind beyond normal competitive and macro uncertainty.",
			"### News Context",
			"\n".join(company_news_lines + market_news_lines) or "- News context was limited in the cached ingestion packet.",
		]
	).strip()


def run_macro_analysis(
	target_ticker: str,
	stock_data: Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	snapshot = build_company_snapshot(target_ticker, stock_data)
	info = resolve_stock_info(stock_data)
	company_news = load_ingested_artifact(target_ticker, "company_news")
	market_news = load_ingested_artifact(target_ticker, "market_news")
	company_profile = load_ingested_artifact(target_ticker, "company_profile")
	macro_artifact = load_ingested_artifact(target_ticker, "macro")
	profile_payload = dict(company_profile.payload.get("profile") or {})
	macro_payload = dict(macro_artifact.payload or {})
	company_name = str(profile_payload.get("companyName") or snapshot.get("company_name") or info.get("longName") or target_ticker).strip()
	sector = str(profile_payload.get("sector") or snapshot.get("sector") or info.get("sector") or macro_payload.get("sector") or "Unknown").strip()
	industry = str(profile_payload.get("industry") or snapshot.get("industry") or info.get("industry") or macro_payload.get("industry") or "Unknown").strip()
	source_links = dedupe_links(
		build_source_links(target_ticker, stock_data),
		list(company_news.source_links or []),
		list(market_news.source_links or []),
		list(company_profile.source_links or []),
		list(macro_artifact.source_links or []),
	)
	source_notes: list[Mapping[str, Any]] = []
	source_notes.extend(build_source_hints(target_ticker, info))
	source_notes.extend(company_news.source_notes)
	source_notes.extend(market_news.source_notes)
	source_notes.extend(company_profile.source_notes)
	source_notes.extend(macro_artifact.source_notes)
	company_news_lines = headline_lines(company_news.source_notes, max_items=3)
	market_news_lines = headline_lines(market_news.source_notes, max_items=3)
	macro_lines = _macro_series_lines(macro_payload)
	competitors = infer_competitors(
		target_ticker.strip().upper(),
		[str(note_payload(note).get("title") or "") for note in company_news.source_notes],
		[str(note_payload(note).get("snippet") or "") for note in company_news.source_notes],
		[str(note_payload(note).get("title") or "") for note in macro_artifact.source_notes],
		[str(note_payload(note).get("snippet") or "") for note in macro_artifact.source_notes],
	)
	tailwind_lines = _signal_bullets(
		[note_payload(note) for note in source_notes],
		["growth", "adoption", "demand", "upgrade", "expansion", "ai", "cloud", "share", "subscriptions"],
	)
	headwind_lines = _signal_bullets(
		[note_payload(note) for note in source_notes],
		["rate", "inflation", "regulation", "tariff", "supply", "competition", "privacy", "soft", "slowdown"],
	)
	report_markdown = _macro_fallback_report(
		company_name,
		sector,
		industry,
		competitors,
		macro_lines,
		company_news_lines,
		market_news_lines,
		tailwind_lines,
		headwind_lines,
		snapshot,
		info,
	)
	system_prompt, user_prompt = build_macro_analysis_prompts(
		ticker=target_ticker,
		company_name=company_name,
		sector=sector,
		industry=industry,
		competitors=competitors,
		macro_lines=macro_lines,
		company_news_lines=company_news_lines,
		market_news_lines=market_news_lines,
		tailwind_lines=tailwind_lines,
		headwind_lines=headwind_lines,
		analysis_focus=analysis_focus,
	)
	llm_report = invoke_text_prompt(
		system_prompt,
		user_prompt,
		model_name=model_name,
		temperature=0.1,
	)
	return build_analysis_artifact(
		"macro",
		llm_report or report_markdown,
		source_links=source_links,
		source_notes=source_notes,
		candidate_facts=_macro_candidate_facts(snapshot, info, profile_payload, competitors, tailwind_lines, headwind_lines),
		confidence=0.8 if (macro_artifact.documents or macro_payload.get("fred_series") or company_news.documents or market_news.documents) else 0.56,
		summary=f"Macro read completed for {company_name}.",
	)


__all__ = ["run_macro_analysis"]
