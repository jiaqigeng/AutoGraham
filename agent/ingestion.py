from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

try:
	from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
	def load_dotenv(*args, **kwargs):
		return False


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CACHE_DIR = _REPO_ROOT / "data" / "cache" / "research_ingestion"
_DEFAULT_SQLITE_DB_PATH = _REPO_ROOT / "data" / "warehouse" / "autograham.db"
_DEFAULT_CHROMA_PATH = _REPO_ROOT / "data" / "chroma"
_DEFAULT_SEC_SECTION_LIMIT = 6
_DEFAULT_FMP_COMPANY_NEWS_LIMIT = 10
_DEFAULT_FMP_MARKET_NEWS_LIMIT = 10
_DEFAULT_FMP_TIMEOUT_SECONDS = 20
_DEFAULT_FRED_TIMEOUT_SECONDS = 20
_CACHE_TTLS_SECONDS = {
	"sec": 7 * 24 * 60 * 60,
	"financials": 6 * 60 * 60,
	"company_news": 3 * 60 * 60,
	"market_news": 3 * 60 * 60,
	"company_profile": 24 * 60 * 60,
	"macro": 12 * 60 * 60,
}
_FMP_BASE_URL = "https://financialmodelingprep.com"
_FRED_SERIES_URL = "https://api.stlouisfed.org/fred/series/observations"
_DEFAULT_FRED_SERIES: dict[str, str] = {
	"FEDFUNDS": "Effective Federal Funds Rate",
	"DGS10": "10-Year Treasury Constant Maturity Rate",
	"CPIAUCSL": "Consumer Price Index for All Urban Consumers",
	"UNRATE": "Civilian Unemployment Rate",
}
_SERIES_SPECS: dict[str, tuple[str, tuple[str, ...], str | None]] = {
	"revenue": ("income_statement", ("Total Revenue", "Revenue"), "USD"),
	"gross_profit": ("income_statement", ("Gross Profit",), "USD"),
	"operating_income": ("income_statement", ("Operating Income", "EBIT"), "USD"),
	"net_income": ("income_statement", ("Net Income", "Net Income Common Stockholders"), "USD"),
	"depreciation": ("cashflow", ("Depreciation", "Depreciation And Amortization"), "USD"),
	"operating_cash_flow": (
		"cashflow",
		("Operating Cash Flow", "Cash Flow From Continuing Operating Activities", "Net Cash Provided By Operating Activities"),
		"USD",
	),
	"free_cash_flow": ("cashflow", ("Free Cash Flow",), "USD"),
	"capital_expenditure": ("cashflow", ("Capital Expenditure", "Capital Expenditures"), "USD"),
	"cash_and_equivalents": (
		"balance_sheet",
		("Cash And Cash Equivalents", "Cash And Cash Equivalents, At Carrying Value", "Cash"),
		"USD",
	),
	"total_debt": ("balance_sheet", ("Total Debt", "Long Term Debt And Capital Lease Obligation"), "USD"),
	"total_equity": ("balance_sheet", ("Stockholders Equity", "Total Equity Gross Minority Interest"), "USD"),
}


def _utc_now_iso() -> str:
	return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize_ticker(ticker: str) -> str:
	return ticker.strip().upper()


def _json_default(value: Any) -> Any:
	if isinstance(value, Path):
		return str(value)
	return str(value)


def _json_dumps(payload: Any) -> str:
	return json.dumps(payload, indent=2, default=_json_default, sort_keys=True)


def _coerce_float(value: Any) -> float | None:
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _hash_payload(payload: str) -> str:
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _content_hash(text: str) -> str:
	return _hash_payload(text.strip())


def _ensure_parent(path: Path) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)


def _cache_path(cache_dir: Path, ticker: str, source: str) -> Path:
	return cache_dir / _normalize_ticker(ticker) / f"{source}.json"


def _cache_is_fresh(path: Path, ttl_seconds: int) -> bool:
	if not path.exists():
		return False
	modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
	return (datetime.now(UTC) - modified_at).total_seconds() <= ttl_seconds


def _first_non_empty(mapping: Mapping[str, Any], *keys: str) -> Any:
	for key in keys:
		value = mapping.get(key)
		if value not in (None, "", [], {}):
			return value
	return None


def _column_label(column: Any) -> str:
	if hasattr(column, "strftime"):
		return column.strftime("%Y-%m-%d")
	return str(column)


@dataclass(slots=True)
class SourceNote:
	title: str
	url: str | None = None
	snippet: str = ""
	source_type: str = "reference"
	confidence: float | None = None
	metadata: dict[str, Any] = field(default_factory=dict)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)

	@classmethod
	def from_dict(cls, payload: Mapping[str, Any]) -> "SourceNote":
		return cls(
			title=str(payload.get("title") or ""),
			url=str(payload.get("url")) if payload.get("url") else None,
			snippet=str(payload.get("snippet") or ""),
			source_type=str(payload.get("source_type") or "reference"),
			confidence=_coerce_float(payload.get("confidence")),
			metadata=dict(payload.get("metadata") or {}),
		)


@dataclass(slots=True)
class DocumentRecord:
	document_id: str
	ticker: str
	source: str
	document_type: str
	title: str
	text: str
	published_at: str | None = None
	url: str | None = None
	metadata: dict[str, Any] = field(default_factory=dict)
	content_hash: str = ""

	def __post_init__(self) -> None:
		self.ticker = _normalize_ticker(self.ticker)
		if not self.content_hash:
			self.content_hash = _content_hash(self.text)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)

	@classmethod
	def from_dict(cls, payload: Mapping[str, Any]) -> "DocumentRecord":
		return cls(
			document_id=str(payload.get("document_id") or ""),
			ticker=str(payload.get("ticker") or ""),
			source=str(payload.get("source") or ""),
			document_type=str(payload.get("document_type") or ""),
			title=str(payload.get("title") or ""),
			text=str(payload.get("text") or ""),
			published_at=str(payload.get("published_at")) if payload.get("published_at") else None,
			url=str(payload.get("url")) if payload.get("url") else None,
			metadata=dict(payload.get("metadata") or {}),
			content_hash=str(payload.get("content_hash") or ""),
		)


@dataclass(slots=True)
class FinancialFact:
	ticker: str
	source: str
	metric_name: str
	value: float
	period: str = ""
	as_of_date: str | None = None
	statement_type: str = ""
	unit: str | None = None
	currency: str | None = "USD"
	metadata: dict[str, Any] = field(default_factory=dict)

	def __post_init__(self) -> None:
		self.ticker = _normalize_ticker(self.ticker)
		self.value = float(self.value)

	def to_dict(self) -> dict[str, Any]:
		return asdict(self)

	@classmethod
	def from_dict(cls, payload: Mapping[str, Any]) -> "FinancialFact":
		return cls(
			ticker=str(payload.get("ticker") or ""),
			source=str(payload.get("source") or ""),
			metric_name=str(payload.get("metric_name") or ""),
			value=float(payload.get("value") or 0.0),
			period=str(payload.get("period") or ""),
			as_of_date=str(payload.get("as_of_date")) if payload.get("as_of_date") else None,
			statement_type=str(payload.get("statement_type") or ""),
			unit=str(payload.get("unit")) if payload.get("unit") else None,
			currency=str(payload.get("currency")) if payload.get("currency") else None,
			metadata=dict(payload.get("metadata") or {}),
		)


@dataclass(slots=True)
class FetchArtifact:
	source: str
	status: str
	payload: dict[str, Any] = field(default_factory=dict)
	documents: list[DocumentRecord] = field(default_factory=list)
	financial_facts: list[FinancialFact] = field(default_factory=list)
	source_links: list[str] = field(default_factory=list)
	source_notes: list[SourceNote] = field(default_factory=list)
	fetched_at: str = field(default_factory=_utc_now_iso)
	error: str = ""
	cache_path: str = ""
	metadata: dict[str, Any] = field(default_factory=dict)

	def to_dict(self) -> dict[str, Any]:
		return {
			"source": self.source,
			"status": self.status,
			"payload": dict(self.payload),
			"documents": [item.to_dict() for item in self.documents],
			"financial_facts": [item.to_dict() for item in self.financial_facts],
			"source_links": list(self.source_links),
			"source_notes": [item.to_dict() for item in self.source_notes],
			"fetched_at": self.fetched_at,
			"error": self.error,
			"cache_path": self.cache_path,
			"metadata": dict(self.metadata),
		}

	@classmethod
	def from_dict(cls, payload: Mapping[str, Any]) -> "FetchArtifact":
		return cls(
			source=str(payload.get("source") or ""),
			status=str(payload.get("status") or "empty"),
			payload=dict(payload.get("payload") or {}),
			documents=[DocumentRecord.from_dict(item) for item in list(payload.get("documents") or [])],
			financial_facts=[FinancialFact.from_dict(item) for item in list(payload.get("financial_facts") or [])],
			source_links=[str(item) for item in list(payload.get("source_links") or []) if str(item).strip()],
			source_notes=[SourceNote.from_dict(item) for item in list(payload.get("source_notes") or [])],
			fetched_at=str(payload.get("fetched_at") or _utc_now_iso()),
			error=str(payload.get("error") or ""),
			cache_path=str(payload.get("cache_path") or ""),
			metadata=dict(payload.get("metadata") or {}),
		)


@dataclass(slots=True)
class DataIngestionPacket:
	ticker: str
	sec_data: FetchArtifact
	financials_data: FetchArtifact
	company_news_data: FetchArtifact
	market_news_data: FetchArtifact
	company_profile_data: FetchArtifact
	macro_data: FetchArtifact
	raw_research_packet: dict[str, Any]
	source_links: list[str]
	source_notes: list[SourceNote]
	cache_dir: str
	sqlite_db_path: str
	chroma_path: str
	created_at: str = field(default_factory=_utc_now_iso)

	def __post_init__(self) -> None:
		self.ticker = _normalize_ticker(self.ticker)

	def to_dict(self) -> dict[str, Any]:
		return {
			"ticker": self.ticker,
			"sec_data": self.sec_data.to_dict(),
			"financials_data": self.financials_data.to_dict(),
			"company_news_data": self.company_news_data.to_dict(),
			"market_news_data": self.market_news_data.to_dict(),
			"company_profile_data": self.company_profile_data.to_dict(),
			"macro_data": self.macro_data.to_dict(),
			"raw_research_packet": dict(self.raw_research_packet),
			"source_links": list(self.source_links),
			"source_notes": [item.to_dict() for item in self.source_notes],
			"cache_dir": self.cache_dir,
			"sqlite_db_path": self.sqlite_db_path,
			"chroma_path": self.chroma_path,
			"created_at": self.created_at,
		}


@dataclass(slots=True)
class IngestionConfig:
	cache_dir: Path = _DEFAULT_CACHE_DIR
	sqlite_db_path: Path = _DEFAULT_SQLITE_DB_PATH
	chroma_path: Path = _DEFAULT_CHROMA_PATH
	sec_section_limit: int = _DEFAULT_SEC_SECTION_LIMIT
	fmp_company_news_limit: int = _DEFAULT_FMP_COMPANY_NEWS_LIMIT
	fmp_market_news_limit: int = _DEFAULT_FMP_MARKET_NEWS_LIMIT
	fmp_timeout_seconds: int = _DEFAULT_FMP_TIMEOUT_SECONDS
	fred_timeout_seconds: int = _DEFAULT_FRED_TIMEOUT_SECONDS


def _load_config(
	*,
	cache_dir: str | Path | None = None,
	sqlite_db_path: str | Path | None = None,
	chroma_path: str | Path | None = None,
) -> IngestionConfig:
	load_dotenv()
	return IngestionConfig(
		cache_dir=Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR,
		sqlite_db_path=Path(sqlite_db_path) if sqlite_db_path is not None else _DEFAULT_SQLITE_DB_PATH,
		chroma_path=Path(chroma_path) if chroma_path is not None else _DEFAULT_CHROMA_PATH,
		sec_section_limit=int(os.getenv("AUTOGRAHAM_SEC_SECTION_LIMIT") or _DEFAULT_SEC_SECTION_LIMIT),
		fmp_company_news_limit=int(os.getenv("AUTOGRAHAM_FMP_COMPANY_NEWS_LIMIT") or _DEFAULT_FMP_COMPANY_NEWS_LIMIT),
		fmp_market_news_limit=int(os.getenv("AUTOGRAHAM_FMP_MARKET_NEWS_LIMIT") or _DEFAULT_FMP_MARKET_NEWS_LIMIT),
		fmp_timeout_seconds=int(os.getenv("AUTOGRAHAM_FMP_TIMEOUT_SECONDS") or _DEFAULT_FMP_TIMEOUT_SECONDS),
		fred_timeout_seconds=int(os.getenv("AUTOGRAHAM_FRED_TIMEOUT_SECONDS") or _DEFAULT_FRED_TIMEOUT_SECONDS),
	)


def _artifact_note_signature(note: SourceNote) -> tuple[str, str, str, str]:
	return (
		note.title.strip(),
		str(note.url or "").strip(),
		note.snippet.strip(),
		note.source_type.strip(),
	)


def _dedupe_links(*groups: list[str]) -> list[str]:
	return list(
		dict.fromkeys(
			item.strip()
			for group in groups
			for item in group
			if isinstance(item, str) and item.strip()
		)
	)


def _dedupe_notes(*groups: list[SourceNote]) -> list[SourceNote]:
	seen: set[tuple[str, str, str, str]] = set()
	deduped: list[SourceNote] = []
	for group in groups:
		for note in group:
			signature = _artifact_note_signature(note)
			if signature in seen:
				continue
			seen.add(signature)
			deduped.append(note)
	return deduped


def read_cached_artifact(path: Path, ttl_seconds: int) -> FetchArtifact | None:
	if not _cache_is_fresh(path, ttl_seconds):
		return None
	try:
		payload = json.loads(path.read_text(encoding="utf-8"))
	except Exception:
		return None
	artifact = FetchArtifact.from_dict(payload)
	artifact.metadata["cache_hit"] = True
	artifact.cache_path = str(path)
	return artifact


def write_cached_artifact(path: Path, artifact: FetchArtifact) -> FetchArtifact:
	artifact.cache_path = str(path)
	artifact.metadata["cache_hit"] = False
	_ensure_parent(path)
	path.write_text(_json_dumps(artifact.to_dict()), encoding="utf-8")
	return artifact


def _empty_artifact(source: str, *, status: str = "empty", error: str = "") -> FetchArtifact:
	return FetchArtifact(source=source, status=status, error=error)


def _sec_documents_from_notes(ticker: str, notes: list[Mapping[str, Any]]) -> list[DocumentRecord]:
	documents: list[DocumentRecord] = []
	for index, note in enumerate(notes, start=1):
		snippet = str(note.get("snippet") or "").strip()
		if not snippet:
			continue
		documents.append(
			DocumentRecord(
				document_id=f"{_normalize_ticker(ticker)}::sec::{index}",
				ticker=ticker,
				source="sec",
				document_type=str(note.get("section_key") or "filing_section"),
				title=str(note.get("title") or f"{ticker} SEC section {index}"),
				text=snippet,
				published_at=str(note.get("filing_date") or "") or None,
				url=str(note.get("url")) if note.get("url") else None,
				metadata={
					"form_type": note.get("form_type"),
					"section_key": note.get("section_key"),
				},
			)
		)
	return documents


async def fetch_sec_artifact(ticker: str, config: IngestionConfig) -> FetchArtifact:
	from agent.tools.sec_tools import build_sec_company_url, get_recent_filing_metadata, get_relevant_filing_section_notes

	cache_path = _cache_path(config.cache_dir, ticker, "sec")
	cached = read_cached_artifact(cache_path, _CACHE_TTLS_SECONDS["sec"])
	if cached is not None:
		return cached
	try:
		filings = await asyncio.to_thread(get_recent_filing_metadata, ticker, ("10-K", "10-Q"))
		notes_payload = await asyncio.to_thread(get_relevant_filing_section_notes, ticker, config.sec_section_limit)
	except Exception as exc:
		return write_cached_artifact(
			cache_path,
			FetchArtifact(
				source="sec",
				status="error",
				error=str(exc),
				source_links=[build_sec_company_url(ticker)],
			),
		)
	documents = _sec_documents_from_notes(ticker, notes_payload)
	notes = [
		SourceNote(
			title=str(item.get("title") or "SEC filing"),
			url=str(item.get("url")) if item.get("url") else None,
			snippet=str(item.get("snippet") or ""),
			source_type=str(item.get("source_type") or "sec_section"),
			confidence=_coerce_float(item.get("confidence")),
			metadata={"form_type": item.get("form_type"), "section_key": item.get("section_key")},
		)
		for item in notes_payload
	]
	links = [build_sec_company_url(ticker), *[str(item.get("document_url") or "") for item in filings], *[str(item.get("url") or "") for item in notes_payload]]
	status = "success" if filings or documents else "empty"
	artifact = FetchArtifact(
		source="sec",
		status=status,
		payload={"filings": filings, "section_count": len(documents)},
		documents=documents,
		source_links=[item for item in links if item],
		source_notes=notes,
	)
	return write_cached_artifact(cache_path, artifact)


def _fmp_api_key() -> str | None:
	return (os.getenv("FMP_API_KEY") or os.getenv("AUTOGRAHAM_FMP_API_KEY") or "").strip() or None


def _fmp_get_json(path: str, *, params: Mapping[str, Any], timeout_seconds: int) -> Any:
	import requests

	api_key = _fmp_api_key()
	if not api_key:
		raise RuntimeError("FMP_API_KEY is not configured")
	response = requests.get(
		f"{_FMP_BASE_URL}{path}",
		params={**dict(params), "apikey": api_key},
		headers={"User-Agent": "AutoGraham data ingestion"},
		timeout=timeout_seconds,
	)
	response.raise_for_status()
	return response.json()


def _fred_api_key() -> str | None:
	return (os.getenv("FRED_API_KEY") or os.getenv("AUTOGRAHAM_FRED_API_KEY") or "").strip() or None


def _fred_get_json(series_id: str, *, timeout_seconds: int, limit: int = 12) -> Mapping[str, Any]:
	import requests

	api_key = _fred_api_key()
	if not api_key:
		raise RuntimeError("FRED_API_KEY is not configured")
	response = requests.get(
		_FRED_SERIES_URL,
		params={
			"series_id": series_id,
			"api_key": api_key,
			"file_type": "json",
			"sort_order": "desc",
			"limit": limit,
		},
		headers={"User-Agent": "AutoGraham data ingestion"},
		timeout=timeout_seconds,
	)
	response.raise_for_status()
	payload = response.json()
	return payload if isinstance(payload, Mapping) else {}


def _string_value(payload: Mapping[str, Any], *keys: str) -> str:
	value = _first_non_empty(payload, *keys)
	if value is None:
		return ""
	return str(value).strip()


def _article_title(article: Mapping[str, Any]) -> str:
	return _string_value(article, "title", "headline")


def _article_snippet(article: Mapping[str, Any]) -> str:
	return _string_value(article, "text", "content", "snippet")


def _article_published_at(article: Mapping[str, Any]) -> str | None:
	value = _string_value(article, "publishedDate", "publishedAt", "date")
	return value or None


def _article_url(article: Mapping[str, Any]) -> str | None:
	value = _string_value(article, "url", "link")
	return value or None


def _article_site(article: Mapping[str, Any]) -> str:
	return _string_value(article, "site", "source")


def _news_documents_from_articles(ticker: str, source: str, articles: list[Mapping[str, Any]]) -> list[DocumentRecord]:
	documents: list[DocumentRecord] = []
	for index, article in enumerate(articles, start=1):
		title = _article_title(article) or f"{ticker} news {index}"
		snippet = _article_snippet(article)
		if not snippet and not title:
			continue
		text_parts = [title]
		site = _article_site(article)
		if site:
			text_parts.append(f"Source: {site}")
		if snippet:
			text_parts.append(snippet)
		documents.append(
			DocumentRecord(
				document_id=f"{_normalize_ticker(ticker)}::{source}::{index}",
				ticker=ticker,
				source=source,
				document_type="news_article",
				title=title,
				text="\n\n".join(part for part in text_parts if part),
				published_at=_article_published_at(article),
				url=_article_url(article),
				metadata={
					"site": site,
					"symbol": _string_value(article, "symbol"),
					"tickers": list(article.get("tickers") or []),
				},
			)
		)
	return documents


def _news_notes_from_articles(source: str, articles: list[Mapping[str, Any]]) -> list[SourceNote]:
	return [
		SourceNote(
			title=_article_title(article) or "News article",
			url=_article_url(article),
			snippet=_article_snippet(article),
			source_type=source,
			metadata={"site": _article_site(article)},
		)
		for article in articles
		if _article_title(article) or _article_snippet(article)
	]


def _coerce_json_list(payload: Any) -> list[Mapping[str, Any]]:
	if isinstance(payload, list):
		return [item for item in payload if isinstance(item, Mapping)]
	if isinstance(payload, Mapping):
		for key in ("data", "items", "results", "articles"):
			value = payload.get(key)
			if isinstance(value, list):
				return [item for item in value if isinstance(item, Mapping)]
	return []


def _coerce_json_mapping(payload: Any) -> Mapping[str, Any]:
	if isinstance(payload, Mapping):
		return payload
	if isinstance(payload, list):
		for item in payload:
			if isinstance(item, Mapping):
				return item
	return {}


def _compact_snippet(text: str, *, max_len: int = 320) -> str:
	cleaned = " ".join(str(text or "").split()).strip()
	if len(cleaned) <= max_len:
		return cleaned
	return f"{cleaned[: max_len - 3].rstrip()}..."


def _macro_search_results(company_name: str, sector: str, industry: str) -> list[dict[str, Any]]:
	from agent.tools.web_search import search_web_payload

	queries = [
		" ".join(part for part in [industry or sector, "market size TAM growth outlook"] if part).strip(),
		" ".join(part for part in [sector or industry, "industry headwinds tailwinds next 3 years"] if part).strip(),
		" ".join(part for part in [company_name, industry or sector, "competitors market share"] if part).strip(),
	]
	results: list[dict[str, Any]] = []
	seen: set[str] = set()
	for query in queries:
		if not query:
			continue
		payload = search_web_payload(query, max_results=3)
		for item in list(payload.get("results") or []):
			url = str(item.get("url") or "").strip()
			key = url or f"{item.get('title')}|{item.get('snippet')}"
			if not key or key in seen:
				continue
			seen.add(key)
			results.append(dict(item))
	return results


def _macro_documents_from_results(ticker: str, results: list[Mapping[str, Any]]) -> list[DocumentRecord]:
	documents: list[DocumentRecord] = []
	for index, item in enumerate(results, start=1):
		title = str(item.get("title") or "").strip() or f"{ticker} macro context {index}"
		snippet = str(item.get("snippet") or "").strip()
		source_domain = str(item.get("source_domain") or "").strip()
		text = "\n\n".join(part for part in [title, f"Source: {source_domain}" if source_domain else "", snippet] if part)
		documents.append(
			DocumentRecord(
				document_id=f"{_normalize_ticker(ticker)}::macro::{index}",
				ticker=ticker,
				source="macro",
				document_type="macro_context",
				title=title,
				text=text,
				published_at=str(item.get("published") or "") or None,
				url=str(item.get("url") or "") or None,
				metadata={"source_domain": source_domain, "query": item.get("query")},
			)
		)
	return documents


def _macro_notes_from_results(results: list[Mapping[str, Any]]) -> list[SourceNote]:
	return [
		SourceNote(
			title=str(item.get("title") or "Macro context"),
			url=str(item.get("url") or "") or None,
			snippet=str(item.get("snippet") or ""),
			source_type="macro_search",
			metadata={"source_domain": item.get("source_domain"), "query": item.get("query")},
		)
		for item in results
	]


async def fetch_company_news_artifact(ticker: str, config: IngestionConfig) -> FetchArtifact:
	cache_path = _cache_path(config.cache_dir, ticker, "company_news")
	cached = read_cached_artifact(cache_path, _CACHE_TTLS_SECONDS["company_news"])
	if cached is not None:
		return cached
	if not _fmp_api_key():
		return _empty_artifact("company_news", status="skipped", error="FMP_API_KEY is not configured")
	try:
		payload = await asyncio.to_thread(
			_fmp_get_json,
			"/stable/news/stock",
			params={"symbols": _normalize_ticker(ticker), "limit": config.fmp_company_news_limit},
			timeout_seconds=config.fmp_timeout_seconds,
		)
		articles = _coerce_json_list(payload)
		documents = _news_documents_from_articles(ticker, "company_news", articles)
		notes = _news_notes_from_articles("company_news", articles)
		artifact = FetchArtifact(
			source="company_news",
			status="success" if articles else "empty",
			payload={"articles": articles, "article_count": len(articles)},
			documents=documents,
			source_links=[item for item in (_article_url(article) for article in articles) if item],
			source_notes=notes,
		)
		return write_cached_artifact(cache_path, artifact)
	except Exception as exc:
		return write_cached_artifact(
			cache_path,
			FetchArtifact(source="company_news", status="error", error=str(exc)),
		)


async def fetch_market_news_artifact(ticker: str, config: IngestionConfig) -> FetchArtifact:
	cache_path = _cache_path(config.cache_dir, ticker, "market_news")
	cached = read_cached_artifact(cache_path, _CACHE_TTLS_SECONDS["market_news"])
	if cached is not None:
		return cached
	if not _fmp_api_key():
		return _empty_artifact("market_news", status="skipped", error="FMP_API_KEY is not configured")
	try:
		payload = await asyncio.to_thread(
			_fmp_get_json,
			"/stable/news/general-latest",
			params={"page": 0, "limit": config.fmp_market_news_limit},
			timeout_seconds=config.fmp_timeout_seconds,
		)
		articles = _coerce_json_list(payload)
		documents = _news_documents_from_articles(ticker, "market_news", articles)
		notes = _news_notes_from_articles("market_news", articles)
		artifact = FetchArtifact(
			source="market_news",
			status="success" if articles else "empty",
			payload={"articles": articles, "article_count": len(articles)},
			documents=documents,
			source_links=[item for item in (_article_url(article) for article in articles) if item],
			source_notes=notes,
		)
		return write_cached_artifact(cache_path, artifact)
	except Exception as exc:
		return write_cached_artifact(
			cache_path,
			FetchArtifact(source="market_news", status="error", error=str(exc)),
		)


async def fetch_macro_artifact(
	ticker: str,
	config: IngestionConfig,
	*,
	company_profile_data: FetchArtifact | None = None,
) -> FetchArtifact:
	cache_path = _cache_path(config.cache_dir, ticker, "macro")
	cached = read_cached_artifact(cache_path, _CACHE_TTLS_SECONDS["macro"])
	if cached is not None:
		return cached
	profile_payload = dict((company_profile_data or _empty_artifact("company_profile")).payload.get("profile") or {})
	company_name = _string_value(profile_payload, "companyName", "name") or _normalize_ticker(ticker)
	sector = _string_value(profile_payload, "sector")
	industry = _string_value(profile_payload, "industry")
	search_results = _macro_search_results(company_name, sector, industry)
	documents = _macro_documents_from_results(ticker, search_results)
	source_notes = _macro_notes_from_results(search_results)
	source_links = [str(item.get("url") or "") for item in search_results if str(item.get("url") or "").strip()]
	fred_series: list[dict[str, Any]] = []
	if _fred_api_key():
		for series_id, label in _DEFAULT_FRED_SERIES.items():
			try:
				payload = await asyncio.to_thread(
					_fred_get_json,
					series_id,
					timeout_seconds=config.fred_timeout_seconds,
					limit=12,
				)
			except Exception:
				continue
			observations = [
				{
					"date": str(item.get("date") or ""),
					"value": _coerce_float(item.get("value")),
				}
				for item in list(payload.get("observations") or [])
				if str(item.get("value") or "").strip() not in {"", "."}
			]
			observations = [item for item in observations if item["value"] is not None]
			if not observations:
				continue
			fred_series.append({"series_id": series_id, "label": label, "observations": observations})
			latest = observations[0]
			source_notes.append(
				SourceNote(
					title=label,
					url=f"https://fred.stlouisfed.org/series/{series_id}",
					snippet=f"Latest observation for {label}: {latest['value']} as of {latest['date']}.",
					source_type="fred_macro",
					confidence=0.85,
					metadata={"series_id": series_id},
				)
			)
			source_links.append(f"https://fred.stlouisfed.org/series/{series_id}")
	artifact = FetchArtifact(
		source="macro",
		status="success" if (documents or fred_series or sector or industry) else "empty",
		payload={
			"company_name": company_name,
			"sector": sector,
			"industry": industry,
			"search_results": search_results,
			"fred_series": fred_series,
		},
		documents=documents,
		source_links=source_links,
		source_notes=source_notes,
	)
	return write_cached_artifact(cache_path, artifact)


def _profile_document(ticker: str, profile: Mapping[str, Any]) -> DocumentRecord | None:
	company_name = _string_value(profile, "companyName", "name") or _normalize_ticker(ticker)
	sector = _string_value(profile, "sector")
	industry = _string_value(profile, "industry")
	description = _string_value(profile, "description")
	ceo = _string_value(profile, "ceo")
	exchange = _string_value(profile, "exchangeShortName", "exchange")
	website = _string_value(profile, "website")
	lines = [
		f"{company_name} operates in the {industry or 'unknown'} industry within the {sector or 'unknown'} sector.",
	]
	if description:
		lines.append(description)
	if ceo:
		lines.append(f"CEO: {ceo}")
	if exchange:
		lines.append(f"Exchange: {exchange}")
	if website:
		lines.append(f"Website: {website}")
	text = "\n\n".join(line for line in lines if line)
	if not text.strip():
		return None
	return DocumentRecord(
		document_id=f"{_normalize_ticker(ticker)}::company_profile::1",
		ticker=ticker,
		source="company_profile",
		document_type="company_profile",
		title=f"{company_name} company profile",
		text=text,
		url=website or None,
		metadata={
			"sector": sector,
			"industry": industry,
			"ceo": ceo,
			"exchange": exchange,
		},
	)


async def fetch_company_profile_artifact(ticker: str, config: IngestionConfig) -> FetchArtifact:
	cache_path = _cache_path(config.cache_dir, ticker, "company_profile")
	cached = read_cached_artifact(cache_path, _CACHE_TTLS_SECONDS["company_profile"])
	if cached is not None:
		return cached
	if not _fmp_api_key():
		return _empty_artifact("company_profile", status="skipped", error="FMP_API_KEY is not configured")
	try:
		payload = await asyncio.to_thread(
			_fmp_get_json,
			"/stable/profile",
			params={"symbol": _normalize_ticker(ticker)},
			timeout_seconds=config.fmp_timeout_seconds,
		)
		profile = dict(_coerce_json_mapping(payload))
		document = _profile_document(ticker, profile)
		artifact = FetchArtifact(
			source="company_profile",
			status="success" if profile else "empty",
			payload={"profile": profile},
			documents=[document] if document is not None else [],
			source_links=[item for item in (_string_value(profile, "website"),) if item],
			source_notes=[
				SourceNote(
					title=f"{_normalize_ticker(ticker)} company profile",
					url=_string_value(profile, "website") or None,
					snippet=_string_value(profile, "description"),
					source_type="company_profile",
					metadata={
						"sector": _string_value(profile, "sector"),
						"industry": _string_value(profile, "industry"),
					},
				)
			]
			if profile
			else [],
		)
		return write_cached_artifact(cache_path, artifact)
	except Exception as exc:
		return write_cached_artifact(
			cache_path,
			FetchArtifact(source="company_profile", status="error", error=str(exc)),
		)


def _statement_frame_map(stock_data: Any) -> dict[str, Any]:
	return {
		"income_statement": getattr(stock_data, "annual_income_stmt", None),
		"cashflow": getattr(stock_data, "annual_cashflow", None),
		"balance_sheet": getattr(stock_data, "annual_balance_sheet", None),
	}


def _series_facts_from_frame(ticker: str, source: str, frame: Any, metric_name: str, aliases: tuple[str, ...], statement_type: str, unit: str | None) -> list[FinancialFact]:
	if frame is None or getattr(frame, "empty", True):
		return []
	row_name = next((alias for alias in aliases if alias in getattr(frame, "index", [])), None)
	if row_name is None:
		return []
	facts: list[FinancialFact] = []
	series = frame.loc[row_name]
	for column, raw_value in series.items():
		value = _coerce_float(raw_value)
		if value is None:
			continue
		facts.append(
			FinancialFact(
				ticker=ticker,
				source=source,
				metric_name=metric_name,
				value=value,
				period=_column_label(column),
				as_of_date=_column_label(column),
				statement_type=statement_type,
				unit=unit,
			)
		)
	return facts


def _margin_facts(ticker: str, facts: list[FinancialFact]) -> list[FinancialFact]:
	revenue = {fact.period: fact for fact in facts if fact.metric_name == "revenue"}
	gross_profit = {fact.period: fact for fact in facts if fact.metric_name == "gross_profit"}
	operating_income = {fact.period: fact for fact in facts if fact.metric_name == "operating_income"}
	net_income = {fact.period: fact for fact in facts if fact.metric_name == "net_income"}
	margin_facts: list[FinancialFact] = []
	for period, revenue_fact in revenue.items():
		if revenue_fact.value == 0:
			continue
		if period in gross_profit:
			margin_facts.append(
				FinancialFact(
					ticker=ticker,
					source="financials",
					metric_name="gross_margin",
					value=gross_profit[period].value / revenue_fact.value,
					period=period,
					as_of_date=revenue_fact.as_of_date,
					statement_type="income_statement",
					unit="ratio",
				)
			)
		if period in operating_income:
			margin_facts.append(
				FinancialFact(
					ticker=ticker,
					source="financials",
					metric_name="operating_margin",
					value=operating_income[period].value / revenue_fact.value,
					period=period,
					as_of_date=revenue_fact.as_of_date,
					statement_type="income_statement",
					unit="ratio",
				)
			)
		if period in net_income:
			margin_facts.append(
				FinancialFact(
					ticker=ticker,
					source="financials",
					metric_name="net_margin",
					value=net_income[period].value / revenue_fact.value,
					period=period,
					as_of_date=revenue_fact.as_of_date,
					statement_type="income_statement",
					unit="ratio",
				)
			)
	return margin_facts


def _free_cash_flow_facts(ticker: str, facts: list[FinancialFact]) -> list[FinancialFact]:
	if any(fact.metric_name == "free_cash_flow" for fact in facts):
		return []
	operating_cash_flow = {fact.period: fact for fact in facts if fact.metric_name == "operating_cash_flow"}
	capex = {fact.period: fact for fact in facts if fact.metric_name == "capital_expenditure"}
	free_cash_flow_facts: list[FinancialFact] = []
	for period, operating_cash_flow_fact in operating_cash_flow.items():
		capex_fact = capex.get(period)
		if capex_fact is None:
			continue
		free_cash_flow_facts.append(
			FinancialFact(
				ticker=ticker,
				source="financials",
				metric_name="free_cash_flow",
				value=operating_cash_flow_fact.value - abs(capex_fact.value),
				period=period,
				as_of_date=operating_cash_flow_fact.as_of_date,
				statement_type="cashflow",
				unit="USD",
			)
		)
	return free_cash_flow_facts


def _financial_snapshot_facts(ticker: str, stock_data: Any) -> list[FinancialFact]:
	from agent.tools.finance_tools import build_company_snapshot
	from data.financial_statements import extract_latest_quarter_metrics

	snapshot = build_company_snapshot(ticker, stock_data)
	info = getattr(stock_data, "info", stock_data) or {}
	facts: list[FinancialFact] = []
	for metric_name, value, unit in (
		("current_price", snapshot.get("current_price"), "USD"),
		("market_cap", snapshot.get("market_cap"), "USD"),
		("dividend_per_share", snapshot.get("dividend_per_share"), "USD"),
		("book_value_per_share", snapshot.get("book_value_per_share"), "USD"),
		("return_on_equity", snapshot.get("return_on_equity"), "ratio"),
		("payout_ratio", snapshot.get("payout_ratio"), "ratio"),
		("starting_fcff", snapshot.get("starting_fcff"), "USD"),
		("starting_fcfe", snapshot.get("starting_fcfe"), "USD"),
		("revenue_growth", info.get("revenueGrowth"), "ratio"),
		("profit_margin", info.get("profitMargins"), "ratio"),
	):
		coerced = _coerce_float(value)
		if coerced is None:
			continue
		facts.append(
				FinancialFact(
					ticker=ticker,
					source="financials",
					metric_name=metric_name,
				value=coerced,
				period="latest",
				statement_type="snapshot",
				unit=unit,
			)
		)
	try:
		latest_quarter = extract_latest_quarter_metrics(getattr(stock_data, "quarterly_income_stmt", None))
	except Exception:
		latest_quarter = {}
	for metric_name in ("revenue", "gross_margin", "operating_margin", "net_margin"):
		coerced = _coerce_float(latest_quarter.get(metric_name))
		if coerced is None:
			continue
		facts.append(
			FinancialFact(
				ticker=ticker,
				source="financials",
				metric_name=f"latest_quarter_{metric_name}",
				value=coerced,
				period=str(latest_quarter.get("period") or "latest_quarter"),
				statement_type="quarterly_income_statement",
				unit="ratio" if "margin" in metric_name else "USD",
			)
		)
	return facts


async def fetch_financials_artifact(ticker: str, config: IngestionConfig) -> FetchArtifact:
	from agent.tools.finance_tools import build_company_snapshot
	from data.cache import get_cached_stock_data

	_ = config
	cache_path = _cache_path(_DEFAULT_CACHE_DIR if config.cache_dir is None else config.cache_dir, ticker, "financials")
	cached = read_cached_artifact(cache_path, _CACHE_TTLS_SECONDS["financials"])
	if cached is not None:
		return cached
	try:
		stock_data = await asyncio.to_thread(get_cached_stock_data, ticker)
		snapshot = build_company_snapshot(ticker, stock_data)
		frames = _statement_frame_map(stock_data)
		facts = _financial_snapshot_facts(ticker, stock_data)
		for metric_name, (statement_type, aliases, unit) in _SERIES_SPECS.items():
			facts.extend(_series_facts_from_frame(ticker, "financials", frames.get(statement_type), metric_name, aliases, statement_type, unit))
		facts.extend(_free_cash_flow_facts(ticker, facts))
		facts.extend(_margin_facts(ticker, facts))
		notes = [
			SourceNote(
				title=f"{_normalize_ticker(ticker)} financial snapshot",
				url=f"https://finance.yahoo.com/quote/{_normalize_ticker(ticker)}",
				snippet="Normalized financial statements and market-data snapshot fetched for quantitative analysis.",
				source_type="financials",
				confidence=0.85,
			)
		]
		artifact = FetchArtifact(
			source="financials",
			status="success",
			payload={"snapshot": snapshot, "financial_fact_count": len(facts)},
			financial_facts=facts,
			source_links=[f"https://finance.yahoo.com/quote/{_normalize_ticker(ticker)}"],
			source_notes=notes,
		)
		return write_cached_artifact(cache_path, artifact)
	except Exception as exc:
		return write_cached_artifact(
			cache_path,
			FetchArtifact(
				source="financials",
				status="error",
				error=str(exc),
				source_links=[f"https://finance.yahoo.com/quote/{_normalize_ticker(ticker)}"],
			),
		)


def build_data_ingestion_packet(
	ticker: str,
	sec_data: FetchArtifact,
	financials_data: FetchArtifact,
	company_news_data: FetchArtifact | None = None,
	market_news_data: FetchArtifact | None = None,
	company_profile_data: FetchArtifact | None = None,
	macro_data: FetchArtifact | None = None,
	*,
	cache_dir: str | Path | None = None,
	sqlite_db_path: str | Path | None = None,
	chroma_path: str | Path | None = None,
) -> DataIngestionPacket:
	company_news_data = company_news_data or _empty_artifact("company_news")
	market_news_data = market_news_data or _empty_artifact("market_news")
	company_profile_data = company_profile_data or _empty_artifact("company_profile")
	macro_data = macro_data or _empty_artifact("macro")
	artifacts = {
		"sec": sec_data,
		"financials": financials_data,
		"company_news": company_news_data,
		"market_news": market_news_data,
		"company_profile": company_profile_data,
		"macro": macro_data,
	}
	links = _dedupe_links(*[artifact.source_links for artifact in artifacts.values()])
	notes = _dedupe_notes(*[artifact.source_notes for artifact in artifacts.values()])
	profile = dict(company_profile_data.payload.get("profile") or {})
	raw_research_packet = {
		"ticker": _normalize_ticker(ticker),
		"cache_dir": str(cache_dir or _DEFAULT_CACHE_DIR),
		"sqlite_db_path": str(sqlite_db_path or _DEFAULT_SQLITE_DB_PATH),
		"chroma_path": str(chroma_path or _DEFAULT_CHROMA_PATH),
		"source_status": {name: artifact.status for name, artifact in artifacts.items()},
		"document_refs": {
			name: [item.document_id for item in artifact.documents]
			for name, artifact in artifacts.items()
			if artifact.documents
		},
		"financial_fact_counts": {
			name: len(artifact.financial_facts)
			for name, artifact in artifacts.items()
			if artifact.financial_facts
		},
		"cache_manifest_paths": {name: artifact.cache_path for name, artifact in artifacts.items()},
		"errors": {name: artifact.error for name, artifact in artifacts.items()},
		"macro_context": {
			"company_name": _string_value(profile, "companyName", "name"),
			"sector": _string_value(profile, "sector"),
			"industry": _string_value(profile, "industry"),
			"company_news_document_ids": [item.document_id for item in company_news_data.documents],
			"market_news_document_ids": [item.document_id for item in market_news_data.documents],
			"company_profile_document_ids": [item.document_id for item in company_profile_data.documents],
			"macro_document_ids": [item.document_id for item in macro_data.documents],
		},
	}
	return DataIngestionPacket(
		ticker=ticker,
		sec_data=sec_data,
		financials_data=financials_data,
		company_news_data=company_news_data,
		market_news_data=market_news_data,
		company_profile_data=company_profile_data,
		macro_data=macro_data,
		raw_research_packet=raw_research_packet,
		source_links=links,
		source_notes=notes,
		cache_dir=str(cache_dir or _DEFAULT_CACHE_DIR),
		sqlite_db_path=str(sqlite_db_path or _DEFAULT_SQLITE_DB_PATH),
		chroma_path=str(chroma_path or _DEFAULT_CHROMA_PATH),
	)


async def run_data_ingestion(
	ticker: str,
	*,
	cache_dir: str | Path | None = None,
	sqlite_db_path: str | Path | None = None,
	chroma_path: str | Path | None = None,
	persist: bool = False,
	include_chroma: bool = True,
) -> DataIngestionPacket:
	config = _load_config(cache_dir=cache_dir, sqlite_db_path=sqlite_db_path, chroma_path=chroma_path)
	config.cache_dir.mkdir(parents=True, exist_ok=True)
	sec_data, financials_data, company_news_data, market_news_data, company_profile_data = await asyncio.gather(
		fetch_sec_artifact(ticker, config),
		fetch_financials_artifact(ticker, config),
		fetch_company_news_artifact(ticker, config),
		fetch_market_news_artifact(ticker, config),
		fetch_company_profile_artifact(ticker, config),
	)
	macro_data = await fetch_macro_artifact(ticker, config, company_profile_data=company_profile_data)
	packet = build_data_ingestion_packet(
		ticker,
		sec_data,
		financials_data,
		company_news_data,
		market_news_data,
		company_profile_data,
		macro_data,
		cache_dir=config.cache_dir,
		sqlite_db_path=config.sqlite_db_path,
		chroma_path=config.chroma_path,
	)
	if persist:
		from agent.storage import persist_data_ingestion_packet

		persist_data_ingestion_packet(packet, sqlite_db_path=config.sqlite_db_path, chroma_path=config.chroma_path, include_chroma=include_chroma)
	return packet


def run_data_ingestion_sync(
	ticker: str,
	*,
	cache_dir: str | Path | None = None,
	sqlite_db_path: str | Path | None = None,
	chroma_path: str | Path | None = None,
	persist: bool = False,
	include_chroma: bool = True,
) -> DataIngestionPacket:
	return asyncio.run(
		run_data_ingestion(
			ticker,
			cache_dir=cache_dir,
			sqlite_db_path=sqlite_db_path,
			chroma_path=chroma_path,
			persist=persist,
			include_chroma=include_chroma,
		)
	)


__all__ = [
	"DataIngestionPacket",
	"DocumentRecord",
	"FetchArtifact",
	"FinancialFact",
	"IngestionConfig",
	"SourceNote",
	"build_data_ingestion_packet",
	"fetch_company_news_artifact",
	"fetch_company_profile_artifact",
	"fetch_financials_artifact",
	"fetch_macro_artifact",
	"fetch_market_news_artifact",
	"fetch_sec_artifact",
	"read_cached_artifact",
	"run_data_ingestion",
	"run_data_ingestion_sync",
	"write_cached_artifact",
]
