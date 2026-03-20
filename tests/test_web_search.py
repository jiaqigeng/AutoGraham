from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from agent.tools.web_search import SearchProviderLoadResult, search_market_context, search_market_context_payload, search_market_context_results


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
			payload = search_market_context_payload("AAPL risks")

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
			payload = search_market_context_payload("  AAPL   valuation   ", max_results=3)

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
			payload = search_market_context_payload("MSFT competitors")

		self.assertEqual(payload["status"], "error")
		self.assertEqual(payload["results"], [])
		self.assertIn("RuntimeError: boom", payload["error"])

	def test_results_helper_returns_plain_results_list(self) -> None:
		provider = StubSearchProvider(results=[{"title": "One", "url": "https://example.com/1", "body": "Snippet"}])
		with patch(
			"agent.tools.web_search._build_search_provider",
			return_value=SearchProviderLoadResult(provider=provider, provider_name="stub"),
		):
			results = search_market_context_results("TSLA risks")

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["provider"], "stub")

	def test_tool_formats_successful_results_for_agents(self) -> None:
		with patch(
			"agent.tools.web_search.search_market_context_payload",
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
			formatted = search_market_context("nvda")

		self.assertIn("NVIDIA demand remains strong", formatted)
		self.assertIn("example.com, 2026-03-18", formatted)
		self.assertIn("https://example.com/nvda", formatted)


if __name__ == "__main__":
	unittest.main()
