from __future__ import annotations

import gzip
import os
import re
import zlib
from html import unescape
from json import loads
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen

try:
	from langchain_core.tools import tool
except ImportError:
	def tool(*decorator_args, **decorator_kwargs):
		def decorator(func):
			return func

		if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
			return decorator(decorator_args[0])
		return decorator


_SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
_REQUEST_TIMEOUT_SECONDS = 15
_DEFAULT_USER_AGENT = "AutoGraham research app (contact not configured)"
_MAX_SECTION_SNIPPET_CHARS = 1800

_SECTION_SPECS: dict[str, tuple[dict[str, str], ...]] = {
	"10-K": (
		{
			"key": "business",
			"title": "Business",
			"start": r"\bitem\s+1\b.{0,120}?business\b",
			"stop": r"\bitem\s+1a\b|\bitem\s+2\b",
		},
		{
			"key": "risk_factors",
			"title": "Risk Factors",
			"start": r"\bitem\s+1a\b.{0,120}?risk factors\b",
			"stop": r"\bitem\s+1b\b|\bitem\s+2\b",
		},
		{
			"key": "mda",
			"title": "Management Discussion and Analysis",
			"start": r"\bitem\s+7\b.{0,180}?management['’`s ]+discussion.{0,80}?analysis\b",
			"stop": r"\bitem\s+7a\b|\bitem\s+8\b",
		},
	),
	"10-Q": (
		{
			"key": "mda",
			"title": "Management Discussion and Analysis",
			"start": r"\bitem\s+2\b.{0,180}?management['’`s ]+discussion.{0,80}?analysis\b",
			"stop": r"\bitem\s+3\b|\bitem\s+4\b",
		},
		{
			"key": "risk_factors",
			"title": "Risk Factors",
			"start": r"\bitem\s+1a\b.{0,120}?risk factors\b",
			"stop": r"\bitem\s+2\b|\bitem\s+3\b",
		},
	),
}


def _sec_headers() -> dict[str, str]:
	"""Return SEC-friendly request headers."""

	return {
		"User-Agent": os.getenv("AUTOGRAHAM_SEC_USER_AGENT", _DEFAULT_USER_AGENT),
		"Accept-Encoding": "gzip, deflate",
	}


def _request_json(url: str) -> dict[str, Any]:
	"""Fetch JSON from the SEC endpoints with a compliant user agent."""

	request = Request(url, headers=_sec_headers())
	with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
		payload = loads(_read_response_text(response))
	return payload if isinstance(payload, dict) else {}


def _request_text(url: str) -> str:
	"""Fetch raw text/HTML from an SEC document URL."""

	request = Request(url, headers=_sec_headers())
	with urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
		return _read_response_text(response, errors="ignore")


def _decode_response_bytes(raw_bytes: bytes, content_encoding: str = "") -> bytes:
	"""Decode SEC payload bytes, including gzip/deflate responses."""

	encoding = str(content_encoding or "").strip().lower()
	if "gzip" in encoding:
		return gzip.decompress(raw_bytes)
	if "deflate" in encoding:
		try:
			return zlib.decompress(raw_bytes)
		except zlib.error:
			return zlib.decompress(raw_bytes, -zlib.MAX_WBITS)
	if raw_bytes[:2] == b"\x1f\x8b":
		return gzip.decompress(raw_bytes)
	return raw_bytes


def _read_response_text(response: Any, errors: str = "strict") -> str:
	"""Read and decode HTTP response text while handling compression."""

	raw_bytes = response.read()
	content_encoding = ""
	headers = getattr(response, "headers", None)
	if headers is not None:
		try:
			content_encoding = str(headers.get("Content-Encoding") or "")
		except Exception:
			content_encoding = ""
	decoded = _decode_response_bytes(raw_bytes, content_encoding)
	return decoded.decode("utf-8-sig", errors=errors)


def _normalize_text(value: str) -> str:
	"""Collapse extracted filing text into a search-friendly plain-text body."""

	text = value.replace("\xa0", " ")
	text = re.sub(r"[ \t]+", " ", text)
	text = re.sub(r"\n\s*\n+", "\n\n", text)
	return text.strip()


def _html_to_text(html: str) -> str:
	"""Convert filing HTML into plain text for lightweight section extraction."""

	text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
	text = re.sub(r"(?i)<br\s*/?>", "\n", text)
	text = re.sub(r"(?i)</p\s*>", "\n", text)
	text = re.sub(r"(?i)</div\s*>", "\n", text)
	text = re.sub(r"(?i)</tr\s*>", "\n", text)
	text = re.sub(r"(?s)<[^>]+>", " ", text)
	return _normalize_text(unescape(text))


def _format_cik(value: Any) -> str | None:
	text = str(value or "").strip()
	if not text:
		return None
	digits = "".join(character for character in text if character.isdigit())
	return digits.zfill(10) if digits else None


def build_sec_company_url(ticker: str) -> str:
	"""Build an SEC company-filings landing page URL."""

	return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker.strip().upper()}&owner=exclude&count=40"


def resolve_company_cik(ticker: str) -> str | None:
	"""Resolve a stock ticker into a zero-padded SEC CIK string."""

	payload = _request_json(_SEC_COMPANY_TICKERS_URL)
	target = ticker.strip().upper()
	for item in payload.values():
		if not isinstance(item, Mapping):
			continue
		if str(item.get("ticker") or "").strip().upper() != target:
			continue
		return _format_cik(item.get("cik_str"))
	return None


def _iter_recent_filing_rows(submissions: Mapping[str, Any]) -> Iterable[dict[str, str]]:
	recent = submissions.get("filings", {}).get("recent", {})
	if not isinstance(recent, Mapping):
		return []

	forms = list(recent.get("form") or [])
	accessions = list(recent.get("accessionNumber") or [])
	primary_documents = list(recent.get("primaryDocument") or [])
	filing_dates = list(recent.get("filingDate") or [])
	descriptions = list(recent.get("primaryDocDescription") or [])
	row_count = min(len(forms), len(accessions), len(primary_documents), len(filing_dates))
	rows: list[dict[str, str]] = []
	for index in range(row_count):
		rows.append(
			{
				"form": str(forms[index] or "").strip().upper(),
				"accession_number": str(accessions[index] or "").strip(),
				"primary_document": str(primary_documents[index] or "").strip(),
				"filing_date": str(filing_dates[index] or "").strip(),
				"description": str(descriptions[index] or "").strip() if index < len(descriptions) else "",
			}
		)
	return rows


def _filing_document_url(cik: str, accession_number: str, primary_document: str) -> str:
	cik_no_padding = str(int(cik))
	accession_no_dashes = accession_number.replace("-", "")
	return f"{_SEC_ARCHIVES_BASE_URL}/{cik_no_padding}/{accession_no_dashes}/{primary_document}"


def get_recent_filing_metadata(ticker: str, form_types: tuple[str, ...] = ("10-K", "10-Q")) -> list[dict[str, str]]:
	"""Return the latest filing metadata for the requested SEC form types."""

	cik = resolve_company_cik(ticker)
	if cik is None:
		return []

	submissions = _request_json(_SEC_SUBMISSIONS_URL.format(cik=cik))
	wanted_forms = {form.strip().upper() for form in form_types if form.strip()}
	selected: list[dict[str, str]] = []
	seen_forms: set[str] = set()
	for row in _iter_recent_filing_rows(submissions):
		form = row.get("form", "")
		if form not in wanted_forms or form in seen_forms:
			continue
		primary_document = row.get("primary_document", "")
		accession_number = row.get("accession_number", "")
		if not primary_document or not accession_number:
			continue
		row["cik"] = cik
		row["document_url"] = _filing_document_url(cik, accession_number, primary_document)
		selected.append(row)
		seen_forms.add(form)
		if seen_forms == wanted_forms:
			break
	return selected


def _extract_section_excerpt(text: str, start_pattern: str, stop_pattern: str | None) -> str:
	"""Extract a filing section using SEC item markers."""

	start_matches = list(re.finditer(start_pattern, text, flags=re.IGNORECASE | re.DOTALL))
	if not start_matches:
		return ""

	start_index = start_matches[-1].start()
	search_window = text[start_index:]
	end_index = len(search_window)
	if stop_pattern:
		stop_match = re.search(stop_pattern, search_window[1:], flags=re.IGNORECASE | re.DOTALL)
		if stop_match:
			end_index = stop_match.start() + 1
	excerpt = _normalize_text(search_window[:end_index])
	return excerpt[:_MAX_SECTION_SNIPPET_CHARS].rstrip()


def _extract_relevant_sections(form_type: str, filing_html: str) -> list[dict[str, str]]:
	"""Extract high-value qualitative SEC sections that Yahoo Finance does not provide."""

	specs = _SECTION_SPECS.get(form_type.upper(), ())
	if not specs:
		return []

	text = _html_to_text(filing_html)
	sections: list[dict[str, str]] = []
	for spec in specs:
		snippet = _extract_section_excerpt(text, spec["start"], spec["stop"])
		if not snippet:
			continue
		sections.append(
			{
				"section_key": spec["key"],
				"section_title": spec["title"],
				"snippet": snippet,
			}
		)
	return sections


def build_source_hints(ticker: str, info: Mapping[str, Any]) -> list[dict[str, str]]:
	"""Create source-link hints without requiring live filing downloads."""

	hints = [
		{
			"title": f"{ticker.upper()} SEC filings",
			"url": build_sec_company_url(ticker),
			"source_type": "sec",
			"snippet": "SEC company filings search page.",
		}
	]
	website = str(info.get("website") or "").strip()
	if website:
		hints.append(
			{
				"title": f"{ticker.upper()} company website",
				"url": website,
				"source_type": "company",
				"snippet": "Company website or investor-relations starting point.",
			}
		)
	return hints


def get_relevant_filing_section_notes(ticker: str, max_sections: int = 3) -> list[dict[str, Any]]:
	"""Return recent SEC section excerpts that add qualitative detail beyond Yahoo Finance."""

	notes: list[dict[str, Any]] = []
	try:
		filings = get_recent_filing_metadata(ticker, form_types=("10-K", "10-Q"))
	except Exception:
		return notes

	for filing in filings:
		document_url = filing.get("document_url")
		if not document_url:
			continue
		try:
			filing_html = _request_text(document_url)
		except Exception:
			continue

		for section in _extract_relevant_sections(filing.get("form", ""), filing_html):
			notes.append(
				{
					"title": f"{ticker.strip().upper()} {filing.get('form', '')} {section['section_title']}",
					"url": document_url,
					"source_type": "sec_section",
					"snippet": section["snippet"],
					"section_key": section["section_key"],
					"form_type": filing.get("form", ""),
					"filing_date": filing.get("filing_date", ""),
					"confidence": 0.85,
				}
			)
			if len(notes) >= max_sections:
				return notes
	return notes


@tool
def get_filing_source_hints(ticker: str) -> str:
	"""Return likely SEC / investor-relations source links for a ticker."""

	try:
		from data.cache import get_cached_stock_data

		info = get_cached_stock_data(ticker).info
	except Exception:
		info = {}
	hints = build_source_hints(ticker, info)
	return "\n".join(f"- {item['title']}: {item['url']}" for item in hints)


@tool
def get_relevant_filing_sections(ticker: str) -> str:
	"""Return recent SEC sections with forward-looking and qualitative evidence not found in Yahoo Finance."""

	notes = get_relevant_filing_section_notes(ticker, max_sections=3)
	if not notes:
		return f"No relevant SEC filing sections were retrieved for {ticker.strip().upper()}."
	return "\n\n".join(
		f"{note['title']} ({note.get('filing_date') or 'filing date unavailable'}): {note['url']}\n{note['snippet']}"
		for note in notes
	)
