from __future__ import annotations

import logging
import math
import re
import warnings
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

try:
	from langchain_core.tools import tool
except ImportError:
	def tool(*decorator_args, **decorator_kwargs):
		def decorator(func):
			return func

		if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
			return decorator(decorator_args[0])
		return decorator


logger = logging.getLogger(__name__)

_ALLOWED_URL_SCHEMES = {"http", "https"}
_MAX_TITLE_LENGTH = 180
_MAX_SNIPPET_LENGTH = 320
_MAX_QUERY_LENGTH = 240

_PARAMETER_SEARCH_TOPICS = {
	"revenue": "revenue sales demand outlook",
	"revenue_growth": "revenue growth sales growth demand outlook",
	"growth_rate": "growth outlook revenue growth earnings growth trend",
	"ebit_margin": "operating margin EBIT margin profitability outlook",
	"operating_margin": "operating margin profitability outlook",
	"gross_margin": "gross margin pricing mix costs outlook",
	"tax_rate": "effective tax rate tax outlook normalized rate",
	"capex": "capex capital expenditure investment plans outlook",
	"depreciation": "depreciation amortization asset base trend",
	"change_in_nwc": "working capital inventory receivables payables trend",
	"net_borrowing": "net borrowing debt issuance leverage funding outlook",
	"wacc": "WACC discount rate beta capital structure outlook",
	"cost_of_equity": "cost of equity beta equity risk premium outlook",
	"terminal_growth": "long-term growth mature growth terminal growth outlook",
	"dividend": "dividend payout capital return outlook",
	"dividend_growth": "dividend growth payout outlook trend",
	"payout_ratio": "payout ratio capital return dividend policy outlook",
	"earnings_per_share": "EPS earnings per share profit outlook",
	"required_return": "required return discount rate cost of equity outlook",
	"book_value_per_share": "book value tangible book capital levels trend",
	"return_on_equity": "ROE return on equity profitability outlook",
	"shares_outstanding": "share count dilution buybacks repurchases outlook",
	"total_debt": "total debt leverage balance sheet outlook",
	"cash": "cash liquidity balance sheet outlook",
}


_PARAMETER_NAME_SPLIT_PATTERN = r"[,;\n|]+"


class SearchProvider(Protocol):
	provider_name: str

	def search_text(self, query: str, *, max_results: int) -> list[dict[str, Any]]:
		...


@dataclass(frozen=True)
class SearchProviderLoadResult:
	provider: SearchProvider | None
	provider_name: str | None
	error: str | None = None


@dataclass(frozen=True)
class DuckDuckGoSearchProvider:
	ddgs_class: Any
	provider_name: str

	def search_text(self, query: str, *, max_results: int) -> list[dict[str, Any]]:
		with self.ddgs_class() as search_client:
			return list(search_client.text(query, max_results=max_results))


def _collapse_text(value: Any, *, max_length: int) -> str:
	text = " ".join(str(value or "").split())
	if len(text) <= max_length:
		return text
	return f"{text[: max_length - 3].rstrip()}..."


def _clean_company_identifier(company_or_ticker: str) -> str:
	return _collapse_text(company_or_ticker, max_length=80)


def _normalize_parameter_name(parameter_name: str) -> str:
	return str(parameter_name or "").strip().lower().replace("-", "_").replace(" ", "_")


def _parameter_search_topic(parameter_name: str) -> str:
	normalized = _normalize_parameter_name(parameter_name)
	return _PARAMETER_SEARCH_TOPICS.get(normalized, normalized.replace("_", " "))


def _safe_max_results(max_results: int) -> int:
	try:
		return max(1, int(max_results))
	except (TypeError, ValueError):
		return 5


def _company_market_context_queries(company_or_ticker: str, focus: str | None = None) -> list[str]:
	company = _clean_company_identifier(company_or_ticker)
	queries = [
		f"{company} business update strategy risks competition industry outlook",
		f"{company} earnings demand pricing guidance recent news",
	]
	if focus:
		queries.append(f"{company} {_collapse_text(focus, max_length=80)}")
	return queries


def _parameter_research_queries(company_or_ticker: str, parameter_name: str) -> list[str]:
	company = _clean_company_identifier(company_or_ticker)
	normalized_parameter = _normalize_parameter_name(parameter_name)
	parameter_label = normalized_parameter.replace("_", " ")
	topic = _parameter_search_topic(parameter_name)
	return [
		f"{company} {topic} analyst consensus next 12 months next 2 years",
		f"{company} {topic} guidance outlook management commentary trend",
		f"{company} {topic} estimate forecast expectations revisions",
		f"{company} {parameter_label} long-term trend drivers risks assumptions",
	]


def _parse_parameter_names(parameter_names: Any) -> list[str]:
	raw_parts = re.split(_PARAMETER_NAME_SPLIT_PATTERN, str(parameter_names or ""))
	normalized: list[str] = []
	seen: set[str] = set()
	for raw_part in raw_parts:
		name = _normalize_parameter_name(raw_part)
		if not name or name in seen:
			continue
		seen.add(name)
		normalized.append(name)
	return normalized


def _parameter_research_batch_queries(company_or_ticker: str, parameter_names: list[str]) -> list[str]:
	company = _clean_company_identifier(company_or_ticker)
	if not parameter_names:
		return []

	topics = [_parameter_search_topic(name) for name in parameter_names[:6]]
	labels = [name.replace("_", " ") for name in parameter_names[:6]]
	topics_text = _collapse_text(" ; ".join(topics), max_length=140)
	labels_text = _collapse_text(", ".join(labels), max_length=140)
	return [
		f"{company} {topics_text} analyst consensus guidance outlook",
		f"{company} {topics_text} management commentary trend drivers risks",
		f"{company} {labels_text} long-term forecast assumptions capital intensity profitability leverage",
	]


def _normalize_url(value: Any) -> tuple[str, str]:
	url = str(value or "").strip()
	if not url:
		return "", ""

	parsed = urlsplit(url)
	scheme = parsed.scheme.lower()
	if scheme not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
		return "", ""

	netloc = parsed.netloc.lower()
	path = parsed.path or ""
	normalized = urlunsplit((scheme, netloc, path, parsed.query, ""))
	if normalized.endswith("/") and path == "/" and not parsed.query:
		normalized = normalized[:-1]
	return normalized, netloc


def _normalize_search_result(item: dict[str, Any], *, rank: int, query: str, provider_name: str) -> dict[str, str] | None:
	title = _collapse_text(item.get("title") or item.get("heading"), max_length=_MAX_TITLE_LENGTH)
	snippet = _collapse_text(
		item.get("body") or item.get("snippet") or item.get("description"),
		max_length=_MAX_SNIPPET_LENGTH,
	)
	raw_url = item.get("href") or item.get("url") or item.get("link")
	url, source_domain = _normalize_url(raw_url)
	published = _collapse_text(item.get("published") or item.get("date"), max_length=40)

	if not any([title, snippet, url]):
		return None
	if raw_url and not url:
		return None
	if not url and not title:
		return None

	return {
		"title": title or source_domain or "Untitled result",
		"url": url,
		"snippet": snippet,
		"source_domain": source_domain,
		"published": published,
		"provider": provider_name,
		"query": query,
		"rank": str(rank),
	}


def _normalize_search_results(raw_results: list[dict[str, Any]], *, query: str, provider_name: str) -> list[dict[str, str]]:
	results: list[dict[str, str]] = []
	seen: set[str] = set()
	for raw_item in raw_results:
		normalized = _normalize_search_result(
			raw_item,
			rank=len(results) + 1,
			query=query,
			provider_name=provider_name,
		)
		if normalized is None:
			continue

		dedup_key = normalized["url"] or f"{normalized['title']}|{normalized['snippet']}"
		if dedup_key in seen:
			continue
		seen.add(dedup_key)
		results.append(normalized)
	return results


def _merge_results(result_groups: list[list[dict[str, str]]], *, max_results: int) -> list[dict[str, str]]:
	merged: list[dict[str, str]] = []
	seen: set[str] = set()
	for group in result_groups:
		for item in group:
			dedup_key = item.get("url") or f"{item.get('title')}|{item.get('snippet')}"
			if dedup_key in seen:
				continue
			seen.add(dedup_key)
			merged.append(item)
			if len(merged) >= max_results:
				return merged
	return merged


def _search_across_queries_payload(
	queries: list[str],
	*,
	max_results: int,
	query_type: str,
	context: dict[str, Any] | None = None,
) -> dict[str, Any]:
	clean_queries = [_collapse_text(query, max_length=_MAX_QUERY_LENGTH) for query in queries if _collapse_text(query, max_length=_MAX_QUERY_LENGTH)]
	safe_max_results = _safe_max_results(max_results)
	if not clean_queries:
		return {
			"status": "error",
			"provider": None,
			"query": "",
			"queries": [],
			"query_type": query_type,
			"results": [],
			"error": "Query must not be empty.",
			**dict(context or {}),
		}

	per_query = max(2, math.ceil(safe_max_results / len(clean_queries)))
	payloads = [search_web_payload(query, max_results=per_query) for query in clean_queries]
	result_groups = [list(payload.get("results") or []) for payload in payloads]
	results = _merge_results(result_groups, max_results=safe_max_results)
	statuses = [str(payload.get("status") or "") for payload in payloads]
	provider = next((payload.get("provider") for payload in payloads if payload.get("provider")), None)

	if results:
		status = "ok"
		error = None
	elif any(status == "empty" for status in statuses):
		status = "empty"
		error = None
	elif any(status == "unavailable" for status in statuses):
		status = "unavailable"
		error = next((payload.get("error") for payload in payloads if payload.get("status") == "unavailable"), None)
	else:
		status = "error"
		error = "; ".join(str(payload.get("error") or "").strip() for payload in payloads if payload.get("error")) or "Search failed."

	return {
		"status": status,
		"provider": provider,
		"query": clean_queries[0],
		"queries": clean_queries,
		"query_type": query_type,
		"results": results,
		"error": error,
		**dict(context or {}),
	}


def _build_search_provider() -> SearchProviderLoadResult:
	try:
		from ddgs import DDGS

		return SearchProviderLoadResult(
			provider=DuckDuckGoSearchProvider(ddgs_class=DDGS, provider_name="ddgs"),
			provider_name="ddgs",
		)
	except ImportError:
		pass

	try:
		with warnings.catch_warnings():
			warnings.simplefilter("ignore", RuntimeWarning)
			from duckduckgo_search import DDGS

		return SearchProviderLoadResult(
			provider=DuckDuckGoSearchProvider(ddgs_class=DDGS, provider_name="duckduckgo_search"),
			provider_name="duckduckgo_search",
		)
	except ImportError:
		return SearchProviderLoadResult(
			provider=None,
			provider_name=None,
			error="Install the `ddgs` package to enable market web search.",
		)


def search_web_payload(query: str, max_results: int = 5) -> dict[str, Any]:
	"""Return normalized web-search results plus provider status metadata."""

	clean_query = _collapse_text(query, max_length=_MAX_QUERY_LENGTH)
	if not clean_query:
		return {
			"status": "error",
			"provider": None,
			"query": "",
			"results": [],
			"error": "Query must not be empty.",
		}

	load_result = _build_search_provider()
	if load_result.provider is None:
		return {
			"status": "unavailable",
			"provider": load_result.provider_name,
			"query": clean_query,
			"results": [],
			"error": load_result.error or "Search provider unavailable.",
		}

	safe_max_results = _safe_max_results(max_results)

	try:
		raw_results = load_result.provider.search_text(clean_query, max_results=safe_max_results)
	except Exception as exc:
		logger.warning(
			"Market context search failed for query %r using provider %s.",
			clean_query,
			load_result.provider_name,
			exc_info=exc,
		)
		return {
			"status": "error",
			"provider": load_result.provider_name,
			"query": clean_query,
			"results": [],
			"error": f"{type(exc).__name__}: {exc}",
		}

	results = _normalize_search_results(raw_results, query=clean_query, provider_name=load_result.provider_name or "unknown")
	return {
		"status": "ok" if results else "empty",
		"provider": load_result.provider_name,
		"query": clean_query,
		"results": results,
		"error": None,
	}


def search_web_results(query: str, max_results: int = 5) -> list[dict[str, str]]:
	"""Return lightweight structured web-search results when a provider is available."""

	return search_web_payload(query, max_results=max_results)["results"]


def search_company_market_context_payload(
	company_or_ticker: str,
	max_results: int = 6,
	focus: str | None = None,
) -> dict[str, Any]:
	"""Search broad company and market context using company-focused query templates."""

	company = _clean_company_identifier(company_or_ticker)
	return _search_across_queries_payload(
		_company_market_context_queries(company, focus=focus),
		max_results=max_results,
		query_type="company_market_context",
		context={"company": company, "focus": _collapse_text(focus, max_length=80) if focus else None},
	)


def search_company_market_context_results(
	company_or_ticker: str,
	max_results: int = 6,
	focus: str | None = None,
) -> list[dict[str, str]]:
	"""Return structured company-market-context search results."""

	return search_company_market_context_payload(company_or_ticker, max_results=max_results, focus=focus)["results"]


def search_parameter_research_payload(
	company_or_ticker: str,
	parameter_name: str,
	max_results: int = 6,
) -> dict[str, Any]:
	"""Search analyst consensus, guidance, and parameter-specific evidence for a company."""

	company = _clean_company_identifier(company_or_ticker)
	parameter = _normalize_parameter_name(parameter_name)
	return _search_across_queries_payload(
		_parameter_research_queries(company, parameter),
		max_results=max_results,
		query_type="parameter_research",
		context={
			"company": company,
			"parameter_name": parameter,
			"parameter_topic": _parameter_search_topic(parameter),
		},
	)


def search_parameter_research_results(
	company_or_ticker: str,
	parameter_name: str,
	max_results: int = 6,
) -> list[dict[str, str]]:
	"""Return structured company-parameter research results."""

	return search_parameter_research_payload(company_or_ticker, parameter_name, max_results=max_results)["results"]


def search_parameter_research_batch_payload(
	company_or_ticker: str,
	parameter_names: str,
	max_results: int = 8,
) -> dict[str, Any]:
	"""Search evidence for a related batch of valuation parameters with fewer tool calls."""

	company = _clean_company_identifier(company_or_ticker)
	normalized_parameters = _parse_parameter_names(parameter_names)
	if not normalized_parameters:
		return {
			"status": "error",
			"provider": None,
			"company": company,
			"parameter_names": [],
			"query_type": "parameter_research_batch",
			"queries": [],
			"results": [],
			"error": "At least one parameter name is required.",
		}
	return _search_across_queries_payload(
		_parameter_research_batch_queries(company, normalized_parameters),
		max_results=max_results,
		query_type="parameter_research_batch",
		context={
			"company": company,
			"parameter_names": normalized_parameters,
		},
	)


def search_parameter_research_batch_results(
	company_or_ticker: str,
	parameter_names: str,
	max_results: int = 8,
) -> list[dict[str, str]]:
	"""Return grouped parameter-research results for a company."""

	return search_parameter_research_batch_payload(company_or_ticker, parameter_names, max_results=max_results)["results"]


def _format_search_result(item: dict[str, str]) -> str:
	title = item.get("title") or "Untitled result"
	url = item.get("url") or "No URL"
	snippet = item.get("snippet") or "No snippet available."
	source_domain = item.get("source_domain") or "unknown source"
	published = item.get("published") or ""
	context_bits = ", ".join(bit for bit in [source_domain, published] if bit)
	return f"- {title} ({context_bits}): {url} | {snippet}"


@tool
def search_web(query: str) -> str:
	"""Search the web with a free-form query and return formatted results."""

	payload = search_web_payload(query, max_results=5)
	if payload["status"] == "ok":
		return "\n".join(_format_search_result(item) for item in payload["results"])
	if payload["status"] == "empty":
		return f"No web results were found for query: {payload['query']}"
	if payload["status"] == "unavailable":
		return f"Search unavailable. {payload['error']}"
	return f"Search failed via {payload.get('provider') or 'configured provider'}. {payload['error']}"


@tool
def search_company_market_context(company_or_ticker: str) -> str:
	"""Search broad company market context such as strategy, risks, demand, and recent updates."""

	payload = search_company_market_context_payload(company_or_ticker, max_results=6)
	if payload["status"] == "ok":
		return "\n".join(_format_search_result(item) for item in payload["results"])
	if payload["status"] == "empty":
		return f"No company market context was found for {payload['company']}."
	if payload["status"] == "unavailable":
		return f"Search unavailable. {payload['error']}"
	return f"Search failed for {payload['company']}. {payload['error']}"


@tool
def search_parameter_research(company_or_ticker: str, parameter_name: str) -> str:
	"""Search company-specific evidence for a valuation parameter such as analyst consensus or guidance."""

	payload = search_parameter_research_payload(company_or_ticker, parameter_name, max_results=6)
	if payload["status"] == "ok":
		return "\n".join(_format_search_result(item) for item in payload["results"])
	if payload["status"] == "empty":
		return f"No useful parameter research was found for {payload['company']} and {payload['parameter_name']}."
	if payload["status"] == "unavailable":
		return f"Search unavailable. {payload['error']}"
	return f"Search failed for {payload['company']} and {payload['parameter_name']}. {payload['error']}"


@tool
def search_parameter_research_batch(company_or_ticker: str, parameter_names: str) -> str:
	"""Search company-specific evidence for a related batch of valuation parameters using fewer tool calls."""

	payload = search_parameter_research_batch_payload(company_or_ticker, parameter_names, max_results=8)
	if payload["status"] == "ok":
		return "\n".join(_format_search_result(item) for item in payload["results"])
	if payload["status"] == "empty":
		return f"No useful grouped parameter research was found for {payload['company']} and {', '.join(payload['parameter_names'])}."
	if payload["status"] == "unavailable":
		return f"Search unavailable. {payload['error']}"
	return f"Search failed for {payload['company']} and {', '.join(payload.get('parameter_names') or [])}. {payload['error']}"
