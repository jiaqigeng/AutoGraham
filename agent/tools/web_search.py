from __future__ import annotations

import logging
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


def search_market_context_payload(query: str, max_results: int = 5) -> dict[str, Any]:
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

	try:
		safe_max_results = max(1, int(max_results))
	except (TypeError, ValueError):
		safe_max_results = 5

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


def search_market_context_results(query: str, max_results: int = 5) -> list[dict[str, str]]:
	"""Return lightweight structured search results when a provider is available."""

	return search_market_context_payload(query, max_results=max_results)["results"]


def _format_search_result(item: dict[str, str]) -> str:
	title = item.get("title") or "Untitled result"
	url = item.get("url") or "No URL"
	snippet = item.get("snippet") or "No snippet available."
	source_domain = item.get("source_domain") or "unknown source"
	published = item.get("published") or ""
	context_bits = ", ".join(bit for bit in [source_domain, published] if bit)
	return f"- {title} ({context_bits}): {url} | {snippet}"


@tool
def search_market_context(query: str) -> str:
	"""Search recent market context, news, or competitor information."""

	payload = search_market_context_payload(query, max_results=5)
	if payload["status"] == "ok":
		return "\n".join(_format_search_result(item) for item in payload["results"])
	if payload["status"] == "empty":
		return f"No recent market context was found for query: {payload['query']}"
	if payload["status"] == "unavailable":
		return f"Search unavailable. {payload['error']}"
	return f"Search failed via {payload.get('provider') or 'configured provider'}. {payload['error']}"
