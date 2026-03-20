from __future__ import annotations

from typing import Any, Mapping

from data.market_data import fetch_stock_data

try:
	from langchain_core.tools import tool
except ImportError:
	def tool(*decorator_args, **decorator_kwargs):
		def decorator(func):
			return func

		if decorator_args and callable(decorator_args[0]) and len(decorator_args) == 1 and not decorator_kwargs:
			return decorator(decorator_args[0])
		return decorator


def build_sec_company_url(ticker: str) -> str:
	"""Build an SEC company-filings landing page URL."""

	return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker.strip().upper()}&owner=exclude&count=40"


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


@tool
def get_filing_source_hints(ticker: str) -> str:
	"""Return likely SEC / investor-relations source links for a ticker."""

	try:
		info = fetch_stock_data(ticker.strip().upper()).info
	except Exception:
		info = {}
	hints = build_source_hints(ticker, info)
	return "\n".join(f"- {item['title']}: {item['url']}" for item in hints)


def sec_research_note() -> str:
	"""Placeholder note for future deeper filing retrieval."""

	return "TODO: add SEC 10-K / 10-Q content retrieval and section-level parsing when the MVP needs deeper filing support."
