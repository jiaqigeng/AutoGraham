from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent.llm_utils import invoke_text_prompt
from agent.schemas import CandidateFact
from agent.skill_prompt_loader import build_qualitative_analysis_prompts
from agent.storage import get_chroma_chunks
from agent.subagents.research.common import (
	company_type,
	build_analysis_artifact,
	chunk_line,
	chunk_source_note,
	dedupe_links,
	extract_target_mentions,
	load_retrieval_chunks,
	merge_candidate_facts,
	select_chunks,
	special_flags,
	strategic_phase,
	summary_sentence,
	top_keyword_chunks,
)
from agent.tools.finance_tools import build_company_snapshot, build_source_links, resolve_stock_info
from agent.tools.sec_tools import build_source_hints


def _management_tone(chunks: Sequence[Mapping[str, Any]]) -> str:
	positive_keywords = ("confident", "opportunity", "resilient", "strong", "momentum", "improve", "durable")
	caution_keywords = ("risk", "headwind", "challenging", "pressure", "uncertain", "soft", "volatile", "macro")
	positive = 0
	caution = 0
	for chunk in chunks:
		text = str(chunk.get("text") or "").lower()
		positive += sum(text.count(keyword) for keyword in positive_keywords)
		caution += sum(text.count(keyword) for keyword in caution_keywords)
	if caution > positive * 1.25:
		return "Management tone looks cautious and explicitly risk-aware based on the selected filing excerpts."
	if positive > caution * 1.25:
		return "Management tone looks constructive, with more emphasis on execution and opportunity than near-term risk."
	return "Management tone looks balanced, mixing growth commentary with explicit discussion of near-term risks."


def _qualitative_candidate_facts(
	snapshot: Mapping[str, Any],
	info: Mapping[str, Any],
	report_markdown: str,
	revenue_driver_summary: str,
	moat_summary: str,
	risk_summary: str,
	management_tone: str,
) -> list[dict[str, Any]]:
	flag_facts = [
		CandidateFact(
			key=f"qualitative_flag_{index}",
			label="Qualitative Flag",
			value=flag,
			source="Qualitative Agent",
			confidence=0.55,
		).model_dump()
		for index, flag in enumerate(special_flags(snapshot, info)[:2], start=1)
	]
	base_facts = [
		CandidateFact(key="company_type", label="Company Type", value=company_type(snapshot, info), source="Qualitative Agent", confidence=0.7).model_dump(),
		CandidateFact(key="strategic_phase", label="Strategic Phase", value=strategic_phase(snapshot, info), source="Qualitative Agent", confidence=0.65).model_dump(),
	]
	extra_facts: list[dict[str, Any]] = []
	if revenue_driver_summary:
		extra_facts.append(
			CandidateFact(key="revenue_drivers", label="Primary Revenue Drivers", value=revenue_driver_summary, source="Qualitative Agent", confidence=0.72).model_dump()
		)
	if moat_summary:
		extra_facts.append(CandidateFact(key="moat_summary", label="Moat Summary", value=moat_summary, source="Qualitative Agent", confidence=0.7).model_dump())
	if risk_summary:
		extra_facts.append(CandidateFact(key="risk_summary", label="Risk Summary", value=risk_summary, source="Qualitative Agent", confidence=0.72).model_dump())
	if management_tone:
		extra_facts.append(
			CandidateFact(key="management_tone", label="Management Tone", value=management_tone, source="Qualitative Agent", confidence=0.66).model_dump()
		)
	return merge_candidate_facts(base_facts, flag_facts, extra_facts, extract_target_mentions(report_markdown))


def run_qualitative_analysis(
	target_ticker: str,
	stock_data: Any,
	model_name: str | None = None,
	analysis_focus: str | None = None,
) -> dict[str, Any]:
	snapshot = build_company_snapshot(target_ticker, stock_data)
	info = resolve_stock_info(stock_data)
	source_links = build_source_links(target_ticker, stock_data)
	source_notes: list[Mapping[str, Any]] = build_source_hints(target_ticker, info)
	sec_chunks, sec_artifact = load_retrieval_chunks(target_ticker, "sec", get_chroma_chunks)
	source_links = dedupe_links(source_links, list(sec_artifact.source_links or []))
	source_notes.extend(sec_artifact.source_notes)
	business_chunks = select_chunks(sec_chunks, ("business",))
	risk_chunks = select_chunks(sec_chunks, ("risk",))
	revenue_driver_chunks = top_keyword_chunks(
		business_chunks,
		["revenue", "sales", "services", "subscription", "installed base", "volume", "pricing", "customers", "advertising"],
		max_items=4,
	)
	moat_chunks = top_keyword_chunks(
		business_chunks,
		["network effect", "switching cost", "switching costs", "ecosystem", "platform", "scale", "cost advantage", "brand", "loyal"],
		max_items=3,
	)
	management_risk_chunks = top_keyword_chunks(
		risk_chunks,
		["risk", "pressure", "headwind", "regulation", "competition", "supply", "macro", "uncertain", "challenging", "fx"],
		max_items=4,
	)
	selected_chunks = revenue_driver_chunks + moat_chunks + management_risk_chunks
	for chunk in selected_chunks:
		source_notes.append(chunk_source_note(chunk, "sec_retrieval"))
		url = str(dict(chunk.get("metadata") or {}).get("url") or "").strip()
		if url:
			source_links.append(url)
	revenue_driver_summary = summary_sentence(" ".join(str(chunk.get("text") or "") for chunk in revenue_driver_chunks), max_len=260)
	moat_summary = summary_sentence(" ".join(str(chunk.get("text") or "") for chunk in moat_chunks), max_len=260)
	risk_summary = summary_sentence(" ".join(str(chunk.get("text") or "") for chunk in management_risk_chunks), max_len=260)
	management_tone = _management_tone(management_risk_chunks)
	fallback_report = "\n".join(
		[
			"### Business Model and Revenue Drivers",
			"\n".join(chunk_line(chunk) for chunk in revenue_driver_chunks)
			or f"- {revenue_driver_summary or 'The cached SEC evidence did not surface clear revenue-driver excerpts.'}",
			"### Moat Signals",
			"\n".join(chunk_line(chunk) for chunk in moat_chunks)
			or f"- {moat_summary or 'Evidence for a durable moat was limited in the selected excerpts.'}",
			"### Risk Factors and Management Tone",
			"\n".join(chunk_line(chunk) for chunk in management_risk_chunks)
			or f"- {risk_summary or 'The selected filing excerpts did not surface a dominant risk theme.'}",
			f"- Management tone: {management_tone}",
		]
	).strip()
	system_prompt, user_prompt = build_qualitative_analysis_prompts(
		ticker=target_ticker,
		company_summary=summary_sentence(str(info.get("longBusinessSummary") or ""), max_len=300),
		revenue_driver_lines=[chunk_line(chunk, max_len=220) for chunk in revenue_driver_chunks],
		moat_lines=[chunk_line(chunk, max_len=220) for chunk in moat_chunks],
		risk_lines=[chunk_line(chunk, max_len=220) for chunk in management_risk_chunks],
		analysis_focus=analysis_focus,
	)
	llm_report = invoke_text_prompt(
		system_prompt,
		user_prompt,
		model_name=model_name,
		temperature=0.1,
	)
	report_markdown = llm_report or fallback_report
	return build_analysis_artifact(
		"qualitative",
		report_markdown,
		source_links=dedupe_links(source_links),
		source_notes=source_notes,
		candidate_facts=_qualitative_candidate_facts(snapshot, info, report_markdown, revenue_driver_summary, moat_summary, risk_summary, management_tone),
		confidence=0.82 if sec_chunks else 0.58,
		summary=f"Qualitative read completed for {snapshot.get('company_name') or target_ticker}.",
	)


__all__ = ["run_qualitative_analysis"]
