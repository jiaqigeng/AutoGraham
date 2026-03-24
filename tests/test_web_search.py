from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from agent.tools.web_search import (
	SearchProviderLoadResult,
	search_company_market_context,
	search_company_market_context_payload,
	search_parameter_research_batch,
	search_parameter_research_batch_payload,
	search_parameter_research,
	search_parameter_research_payload,
	search_web,
	search_web_payload,
	search_web_results,
)


@dataclass
class StubSearchProvider:
	results: list[dict[str, Any]] | None = None
	error: Exception | None = None
	provider_name: str = "stub"

	def search_text(self, query: str, *, max_results: int) -> list[dict[str, Any]]:
		if self.error is not None:
			raise self.error
		return list(self.results or [])


class WebSearchTests(unittest.TestCase):
	def test_payload_reports_unavailable_provider(self) -> None:
		with patch(
			"agent.tools.web_search._build_search_provider",
			return_value=SearchProviderLoadResult(provider=None, provider_name=None, error="Install `ddgs`."),
		):
			payload = search_web_payload("AAPL risks")

		self.assertEqual(payload["status"], "unavailable")
		self.assertEqual(payload["results"], [])
		self.assertIn("Install `ddgs`", payload["error"])

	def test_payload_normalizes_filters_and_deduplicates_results(self) -> None:
		provider = StubSearchProvider(
			results=[
				{
					"title": "  Example headline  ",
					"href": "HTTPS://Example.com/news?id=1#section",
					"body": "Line one\nLine two",
					"date": "2026-03-18",
				},
				{
					"title": "Duplicate URL should be dropped",
					"url": "https://example.com/news?id=1",
					"body": "Second copy",
				},
				{
					"title": "Ignored bad scheme",
					"url": "javascript:alert(1)",
					"body": "Should not survive normalization",
				},
				{
					"body": "Still useful without a title",
					"url": "https://example.org/article",
				},
			]
		)
		with patch(
			"agent.tools.web_search._build_search_provider",
			return_value=SearchProviderLoadResult(provider=provider, provider_name="stub"),
		):
			payload = search_web_payload("  AAPL   valuation   ", max_results=3)

		self.assertEqual(payload["status"], "ok")
		self.assertEqual(len(payload["results"]), 2)
		first, second = payload["results"]
		self.assertEqual(first["title"], "Example headline")
		self.assertEqual(first["url"], "https://example.com/news?id=1")
		self.assertEqual(first["snippet"], "Line one Line two")
		self.assertEqual(first["source_domain"], "example.com")
		self.assertEqual(first["published"], "2026-03-18")
		self.assertEqual(first["rank"], "1")
		self.assertEqual(second["title"], "example.org")
		self.assertEqual(second["url"], "https://example.org/article")
		self.assertEqual(second["rank"], "2")

	def test_payload_reports_provider_errors(self) -> None:
		provider = StubSearchProvider(error=RuntimeError("boom"))
		with patch(
			"agent.tools.web_search._build_search_provider",
			return_value=SearchProviderLoadResult(provider=provider, provider_name="stub"),
		):
			payload = search_web_payload("MSFT competitors")

		self.assertEqual(payload["status"], "error")
		self.assertEqual(payload["results"], [])
		self.assertIn("RuntimeError: boom", payload["error"])

	def test_results_helper_returns_plain_results_list(self) -> None:
		provider = StubSearchProvider(results=[{"title": "One", "url": "https://example.com/1", "body": "Snippet"}])
		with patch(
			"agent.tools.web_search._build_search_provider",
			return_value=SearchProviderLoadResult(provider=provider, provider_name="stub"),
		):
			results = search_web_results("TSLA risks")

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["provider"], "stub")

	def test_tool_formats_successful_results_for_agents(self) -> None:
		with patch(
			"agent.tools.web_search.search_web_payload",
			return_value={
				"status": "ok",
				"provider": "stub",
				"query": "nvda",
				"results": [
					{
						"title": "NVIDIA demand remains strong",
						"url": "https://example.com/nvda",
						"snippet": "GPU demand stayed elevated.",
						"source_domain": "example.com",
						"published": "2026-03-18",
					}
				],
				"error": None,
			},
		):
			formatted = search_web("nvda")

		self.assertIn("NVIDIA demand remains strong", formatted)
		self.assertIn("example.com, 2026-03-18", formatted)
		self.assertIn("https://example.com/nvda", formatted)

	def test_company_market_context_payload_builds_company_focused_queries_and_merges_results(self) -> None:
		def fake_payload(query: str, max_results: int = 5) -> dict[str, Any]:
			return {
				"status": "ok",
				"provider": "stub",
				"query": query,
				"results": [
					{
						"title": f"Result for {query}",
						"url": f"https://example.com/{len(query)}",
						"snippet": "Snippet",
						"source_domain": "example.com",
						"published": "2026-03-18",
						"provider": "stub",
						"query": query,
						"rank": "1",
					}
				],
				"error": None,
			}

		with patch("agent.tools.web_search.search_web_payload", side_effect=fake_payload):
			payload = search_company_market_context_payload("MSFT", max_results=4, focus="cloud demand")

		self.assertEqual(payload["status"], "ok")
		self.assertEqual(payload["company"], "MSFT")
		self.assertEqual(payload["query_type"], "company_market_context")
		self.assertEqual(len(payload["queries"]), 3)
		self.assertIn("MSFT business update strategy risks competition industry outlook", payload["queries"])
		self.assertIn("MSFT cloud demand", payload["queries"])
		self.assertTrue(payload["results"])

	def test_parameter_research_payload_builds_consensus_and_guidance_queries(self) -> None:
		def fake_payload(query: str, max_results: int = 5) -> dict[str, Any]:
			return {
				"status": "ok",
				"provider": "stub",
				"query": query,
				"results": [
					{
						"title": f"Result for {query}",
						"url": f"https://example.com/{abs(hash(query))}",
						"snippet": "Snippet",
						"source_domain": "example.com",
						"published": "",
						"provider": "stub",
						"query": query,
						"rank": "1",
					}
				],
				"error": None,
			}

		with patch("agent.tools.web_search.search_web_payload", side_effect=fake_payload):
			payload = search_parameter_research_payload("AAPL", "revenue growth", max_results=5)

		self.assertEqual(payload["status"], "ok")
		self.assertEqual(payload["company"], "AAPL")
		self.assertEqual(payload["parameter_name"], "revenue_growth")
		self.assertEqual(payload["query_type"], "parameter_research")
		self.assertIn("AAPL revenue growth sales growth demand outlook analyst consensus next 12 months next 2 years", payload["queries"])
		self.assertIn("AAPL revenue growth sales growth demand outlook guidance outlook management commentary trend", payload["queries"])
		self.assertIn("AAPL revenue growth long-term trend drivers risks assumptions", payload["queries"])
		self.assertTrue(payload["results"])

	def test_parameter_research_tool_formats_results(self) -> None:
		with patch(
			"agent.tools.web_search.search_parameter_research_payload",
			return_value={
				"status": "ok",
				"provider": "stub",
				"company": "JPM",
				"parameter_name": "return_on_equity",
				"query_type": "parameter_research",
				"queries": ["JPM ROE analyst consensus"],
				"results": [
					{
						"title": "Analysts expect ROE normalization",
						"url": "https://example.com/jpm-roe",
						"snippet": "Consensus expects ROE to settle near 15%.",
						"source_domain": "example.com",
						"published": "2026-03-18",
					}
				],
				"error": None,
			},
		):
			formatted = search_parameter_research("JPM", "return_on_equity")

		self.assertIn("Analysts expect ROE normalization", formatted)
		self.assertIn("https://example.com/jpm-roe", formatted)

	def test_parameter_research_batch_payload_builds_grouped_queries(self) -> None:
		def fake_payload(query: str, max_results: int = 5) -> dict[str, Any]:
			return {
				"status": "ok",
				"provider": "stub",
				"query": query,
				"results": [
					{
						"title": f"Result for {query}",
						"url": f"https://example.com/{abs(hash(query))}",
						"snippet": "Snippet",
						"source_domain": "example.com",
						"published": "",
						"provider": "stub",
						"query": query,
						"rank": "1",
					}
				],
				"error": None,
			}

		with patch("agent.tools.web_search.search_web_payload", side_effect=fake_payload):
			payload = search_parameter_research_batch_payload("AAPL", "revenue, ebit_margin, tax_rate", max_results=6)

		self.assertEqual(payload["status"], "ok")
		self.assertEqual(payload["company"], "AAPL")
		self.assertEqual(payload["parameter_names"], ["revenue", "ebit_margin", "tax_rate"])
		self.assertEqual(payload["query_type"], "parameter_research_batch")
		self.assertEqual(len(payload["queries"]), 3)
		self.assertIn("AAPL", payload["queries"][0])
		self.assertIn("analyst consensus guidance outlook", payload["queries"][0])
		self.assertTrue(payload["results"])

	def test_parameter_research_batch_tool_formats_results(self) -> None:
		with patch(
			"agent.tools.web_search.search_parameter_research_batch_payload",
			return_value={
				"status": "ok",
				"provider": "stub",
				"company": "META",
				"parameter_names": ["revenue", "ebit_margin", "tax_rate"],
				"query_type": "parameter_research_batch",
				"queries": ["META revenue ebit margin tax rate analyst consensus guidance outlook"],
				"results": [
					{
						"title": "Consensus expects margin normalization",
						"url": "https://example.com/meta-margin",
						"snippet": "Analysts expect revenue growth to moderate while margins improve modestly.",
						"source_domain": "example.com",
						"published": "2026-03-20",
					}
				],
				"error": None,
			},
		):
			formatted = search_parameter_research_batch("META", "revenue, ebit_margin, tax_rate")

		self.assertIn("Consensus expects margin normalization", formatted)
		self.assertIn("https://example.com/meta-margin", formatted)

	def test_company_market_context_tool_reports_empty_search_cleanly(self) -> None:
		with patch(
			"agent.tools.web_search.search_company_market_context_payload",
			return_value={
				"status": "empty",
				"provider": "stub",
				"company": "TSLA",
				"focus": None,
				"query_type": "company_market_context",
				"queries": ["TSLA business update strategy risks competition industry outlook"],
				"results": [],
				"error": None,
			},
		):
			formatted = search_company_market_context("TSLA")

		self.assertIn("No company market context was found for TSLA", formatted)


if __name__ == "__main__":
	unittest.main()
