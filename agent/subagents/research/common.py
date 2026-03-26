from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
import re
from typing import Any, Mapping, Sequence

from agent.ingestion import FetchArtifact
from agent.schemas import CandidateFact
from agent.skill_prompt_loader import build_extraction_prompt
from agent.llm_utils import invoke_text_prompt
from agent.tools.validation_tools import extract_json_array
from data.company_profile import is_financial_company
from data.normalization import format_compact_currency, format_percent, format_price
from valuation.common import default_valuation_inputs, safe_number


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_INGESTION_CACHE_DIR = _REPO_ROOT / "data" / "cache" / "research_ingestion"
_IGNORED_TICKER_TOKENS = {"CEO", "CFO", "EPS", "AI", "IPO", "USD", "GDP", "CPI", "FED", "FRED", "IR"}


def dedupe_links(*groups: list[str]) -> list[str]:
	return list(
		dict.fromkeys(
			link.strip()
			for group in groups
			for link in group
			if isinstance(link, str) and link.strip()
		)
	)


def note_payload(note: Any) -> dict[str, Any]:
	if isinstance(note, Mapping):
		return dict(note)
	if hasattr(note, "to_dict"):
		return dict(note.to_dict())
	return {}


def annotate_source_notes(agent_name: str, notes: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
	annotated: list[dict[str, Any]] = []
	for note in notes:
		payload = note_payload(note)
		payload["analysis_agent"] = agent_name
		annotated.append(payload)
	return annotated


def build_analysis_artifact(
	agent_name: str,
	report_markdown: str,
	*,
	source_links: list[str] | None = None,
	source_notes: list[Mapping[str, Any]] | None = None,
	candidate_facts: list[Mapping[str, Any]] | None = None,
	confidence: float | None = None,
	summary: str | None = None,
	error: str | None = None,
	extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	artifact = {
		"analysis_agent": agent_name,
		"summary": str(summary or "").strip(),
		"report_markdown": str(report_markdown or "").strip(),
		"source_links": dedupe_links(list(source_links or [])),
		"source_notes": annotate_source_notes(agent_name, list(source_notes or [])),
		"candidate_facts": [dict(item) for item in list(candidate_facts or [])],
		"confidence": confidence,
		"error": str(error or "").strip(),
	}
	if extra:
		artifact.update(dict(extra))
	return artifact


def load_ingested_artifact(ticker: str, source: str) -> FetchArtifact:
	path = _DEFAULT_INGESTION_CACHE_DIR / str(ticker or "").strip().upper() / f"{source}.json"
	if not path.exists():
		return FetchArtifact(source=source, status="empty", error=f"Missing cached artifact: {path}")
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except Exception as exc:
		return FetchArtifact(source=source, status="error", error=str(exc), cache_path=str(path))
	artifact = FetchArtifact.from_dict(payload)
	artifact.cache_path = str(path)
	return artifact


def artifact_to_chunks(artifact: FetchArtifact) -> list[dict[str, Any]]:
	return [
		{
			"id": document.document_id,
			"text": document.text,
			"metadata": {
				**dict(document.metadata or {}),
				"title": document.title,
				"url": document.url,
				"document_type": document.document_type,
				"published_at": document.published_at,
				"source": document.source,
			},
		}
		for document in artifact.documents
	]


def summary_sentence(text: str, max_len: int = 260) -> str:
	cleaned = " ".join(str(text or "").split()).strip()
	if len(cleaned) <= max_len:
		return cleaned
	return f"{cleaned[: max_len - 3].rstrip()}..."


def load_retrieval_chunks(
	ticker: str,
	source: str,
	chunk_loader: Any,
) -> tuple[list[dict[str, Any]], FetchArtifact]:
	artifact = load_ingested_artifact(ticker, source)
	chunks = chunk_loader(ticker, source=source, limit=30)
	if not chunks:
		chunks = artifact_to_chunks(artifact)
	return chunks, artifact


def headline_lines(notes: list[Any], *, max_items: int = 3) -> list[str]:
	lines: list[str] = []
	for note in notes[:max_items]:
		payload = note_payload(note)
		title = str(payload.get("title") or "News item").strip()
		snippet = summary_sentence(str(payload.get("snippet") or ""), max_len=180)
		if snippet:
			lines.append(f"- {title}: {snippet}")
		else:
			lines.append(f"- {title}")
	return lines


def fmt_price(value: Any) -> str:
	try:
		return format_price(value)
	except Exception:
		return str(value if value not in (None, "") else "N/A")


def fmt_money(value: Any) -> str:
	try:
		return format_compact_currency(value)
	except Exception:
		return str(value if value not in (None, "") else "N/A")


def fmt_percent(value: Any) -> str:
	try:
		return format_percent(value)
	except Exception:
		return str(value if value not in (None, "") else "N/A")


def clean_period_label(value: str | None) -> str:
	text = str(value or "").strip()
	return text or "N/A"


def top_keyword_chunks(chunks: list[dict[str, Any]], keywords: Sequence[str], *, max_items: int = 3) -> list[dict[str, Any]]:
	scored: list[tuple[int, int, dict[str, Any]]] = []
	for index, chunk in enumerate(chunks):
		text = str(chunk.get("text") or "").lower()
		score = sum(text.count(keyword.lower()) for keyword in keywords)
		if score <= 0:
			continue
		scored.append((score, -index, chunk))
	scored.sort(reverse=True)
	return [item[2] for item in scored[:max_items]]


def chunk_line(chunk: Mapping[str, Any], *, max_len: int = 180) -> str:
	metadata = dict(chunk.get("metadata") or {})
	title = str(metadata.get("title") or metadata.get("document_type") or "Research chunk").strip()
	text = summary_sentence(str(chunk.get("text") or ""), max_len=max_len)
	if text:
		return f"- {title}: {text}"
	return f"- {title}"


def chunk_source_note(chunk: Mapping[str, Any], source_type: str) -> dict[str, Any]:
	metadata = dict(chunk.get("metadata") or {})
	return {
		"title": str(metadata.get("title") or metadata.get("document_type") or "Research chunk"),
		"url": metadata.get("url"),
		"snippet": summary_sentence(str(chunk.get("text") or ""), max_len=180),
		"source_type": source_type,
		"confidence": 0.74,
	}


def chunk_type(chunk: Mapping[str, Any]) -> str:
	metadata = dict(chunk.get("metadata") or {})
	return str(metadata.get("document_type") or metadata.get("section_key") or "").strip().lower()


def chunk_title(chunk: Mapping[str, Any]) -> str:
	return str(dict(chunk.get("metadata") or {}).get("title") or "").strip().lower()


def select_chunks(chunks: list[dict[str, Any]], predicates: Sequence[str]) -> list[dict[str, Any]]:
	selected: list[dict[str, Any]] = []
	for chunk in chunks:
		haystack = f"{chunk_type(chunk)} {chunk_title(chunk)}".strip()
		if any(token in haystack for token in predicates):
			selected.append(chunk)
	return selected


def extract_uppercase_mentions(text: str, *, target_ticker: str) -> list[str]:
	tokens = re.findall(r"\b[A-Z]{2,5}\b", str(text or ""))
	return [
		token
		for token in tokens
		if token != target_ticker and token not in _IGNORED_TICKER_TOKENS and not token.isdigit()
	]


def infer_competitors(target_ticker: str, *text_groups: Sequence[str], max_items: int = 4) -> list[str]:
	counter: Counter[str] = Counter()
	for group in text_groups:
		for text in group:
			for token in extract_uppercase_mentions(text, target_ticker=target_ticker):
				counter[token] += 1
	return [name for name, _count in counter.most_common(max_items)]


def company_type(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> str:
	sector = str(snapshot.get("sector") or "Unknown sector")
	industry = str(snapshot.get("industry") or "Unknown industry")
	if is_financial_company(info):
		return f"Financial company in {sector} / {industry}"
	return f"Operating company in {sector} / {industry}"


def strategic_phase(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> str:
	revenue_growth = safe_number(info.get("revenueGrowth"))
	profit_margin = safe_number(info.get("profitMargins"))
	dividend_yield = safe_number(info.get("dividendYield"))

	if revenue_growth >= 0.15:
		return "High-growth / scaling"
	if revenue_growth < 0 and profit_margin <= 0:
		return "Turnaround / under pressure"
	if dividend_yield > 0.02 and profit_margin > 0:
		return "Mature / capital-return oriented"
	if is_financial_company(info):
		return "Balance-sheet driven / mature financial"
	return "Maturing operator"


def special_flags(snapshot: Mapping[str, Any], info: Mapping[str, Any]) -> list[str]:
	flags: list[str] = []
	if is_financial_company(info):
		flags.append("Financial business: book value and returns on equity may matter more than conventional operating cash-flow framing.")
	if safe_number(snapshot.get("dividend_per_share")) > 0:
		flags.append("Meaningful dividend history is present, so capital return may matter for later model selection.")
	if safe_number(snapshot.get("starting_fcff")) <= 0 and safe_number(snapshot.get("starting_fcfe")) <= 0:
		flags.append("Cash-flow anchors look weak or negative, which may complicate a clean DCF setup.")
	if safe_number(info.get("profitMargins")) <= 0:
		flags.append("Current profitability appears weak or negative.")
	if safe_number(info.get("totalDebt")) > safe_number(info.get("totalCash")) * 2 and safe_number(info.get("totalDebt")) > 0:
		flags.append("Leverage looks elevated relative to cash.")
	if not flags:
		flags.append("No obvious special situation stands out from the lightweight context pass.")
	return flags[:4]


def base_candidate_facts(stock_data: Any) -> list[dict[str, Any]]:
	"""Create deterministic candidate facts from the available market-data bundle."""

	info = getattr(stock_data, "info", stock_data) or {}
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


def extract_target_mentions(research_report: str) -> list[dict[str, Any]]:
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


def merge_candidate_facts(*fact_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

	base_facts = base_candidate_facts(stock_data)
	narrative_facts = extract_target_mentions(research_report)
	llm_facts: list[dict[str, Any]] = []
	system_prompt, user_prompt = build_extraction_prompt(ticker, research_report, source_notes)

	llm_text = invoke_text_prompt(
		system_prompt=system_prompt,
		user_prompt=user_prompt,
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

	return merge_candidate_facts(base_facts, narrative_facts, llm_facts)


__all__ = [
	"annotate_source_notes",
	"artifact_to_chunks",
	"build_analysis_artifact",
	"chunk_line",
	"chunk_source_note",
	"clean_period_label",
	"company_type",
	"dedupe_links",
	"extract_candidate_facts",
	"extract_target_mentions",
	"fmt_money",
	"fmt_percent",
	"fmt_price",
	"headline_lines",
	"infer_competitors",
	"load_ingested_artifact",
	"load_retrieval_chunks",
	"merge_candidate_facts",
	"note_payload",
	"select_chunks",
	"special_flags",
	"strategic_phase",
	"summary_sentence",
	"top_keyword_chunks",
	"base_candidate_facts",
]
