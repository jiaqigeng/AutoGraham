from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent.ingestion import FetchArtifact, SourceNote
from agent.subagents.research.macro_agent import run_macro_analysis


class MacroAgentTests(unittest.TestCase):
	def test_run_macro_analysis_accepts_source_note_dataclasses(self) -> None:
		stock = SimpleNamespace(
			info={
				"longName": "Microsoft Corporation",
				"sector": "Technology",
				"industry": "Software - Infrastructure",
				"website": "https://www.microsoft.com",
			}
		)
		artifacts = {
			"company_news": FetchArtifact(
				source="company_news",
				status="success",
				source_notes=[
					SourceNote(
						title="Microsoft AI momentum continues",
						snippet="MSFT continues investing in cloud and AI while competing with AMZN.",
						source_type="company_news",
					)
				],
			),
			"market_news": FetchArtifact(
				source="market_news",
				status="success",
				source_notes=[
					SourceNote(
						title="Enterprise software demand remains resilient",
						snippet="Large platform vendors continue spending on AI infrastructure.",
						source_type="market_news",
					)
				],
			),
			"company_profile": FetchArtifact(
				source="company_profile",
				status="success",
				payload={
					"profile": {
						"companyName": "Microsoft Corporation",
						"sector": "Technology",
						"industry": "Software - Infrastructure",
					}
				},
			),
			"macro": FetchArtifact(
				source="macro",
				status="success",
				payload={"sector": "Technology", "industry": "Software - Infrastructure", "fred_series": []},
				source_notes=[
					SourceNote(
						title="Cloud platform competition stays intense",
						snippet="MSFT, AMZN, and GOOGL remain the core hyperscale competitors.",
						source_type="macro_search",
					)
				],
			),
		}

		with patch(
			"agent.subagents.research.macro_agent.build_company_snapshot",
			return_value={
				"company_name": "Microsoft Corporation",
				"sector": "Technology",
				"industry": "Software - Infrastructure",
				"current_price": 100.0,
				"market_cap": 1_000.0,
			},
		), patch(
			"agent.subagents.research.macro_agent.load_ingested_artifact",
			side_effect=lambda ticker, source: artifacts[source],
		), patch("agent.subagents.research.macro_agent.build_source_links", return_value=[]), patch(
			"agent.subagents.research.macro_agent.build_source_hints",
			return_value=[],
		), patch("agent.subagents.research.macro_agent.invoke_text_prompt", return_value=None):
			artifact = run_macro_analysis("MSFT", stock)

		self.assertEqual(artifact["analysis_agent"], "macro")
		self.assertEqual(artifact["error"], "")
		self.assertIn("Competitor Read", artifact["report_markdown"])
		self.assertTrue(any(fact.get("key") == "competitors" for fact in artifact["candidate_facts"]))


if __name__ == "__main__":
	unittest.main()
