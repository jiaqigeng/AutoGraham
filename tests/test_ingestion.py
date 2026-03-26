from __future__ import annotations

from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.ingestion import (
	DocumentRecord,
	FetchArtifact,
	FinancialFact,
	SourceNote,
	build_data_ingestion_packet,
	read_cached_artifact,
	write_cached_artifact,
)
from agent.storage import chunk_text_documents, get_chroma_chunks, persist_data_ingestion_packet


class IngestionFoundationTests(unittest.TestCase):
	def test_build_data_ingestion_packet_dedupes_links_and_notes(self) -> None:
		shared_note = SourceNote(title="Shared", url="https://example.com/shared", snippet="shared", source_type="reference")
		sec_data = FetchArtifact(
			source="sec",
			status="success",
			source_links=["https://example.com/shared", "https://example.com/sec"],
			source_notes=[shared_note],
			documents=[
				DocumentRecord(
					document_id="AAPL::sec::1",
					ticker="AAPL",
					source="sec",
					document_type="mda",
					title="MD&A",
					text="Management discussion and analysis",
				)
			],
		)
		financials_data = FetchArtifact(
			source="financials",
			status="success",
			source_links=["https://example.com/finance"],
			source_notes=[
				SourceNote(title="Finance", url="https://example.com/finance", snippet="facts", source_type="financials")
			],
			financial_facts=[
				FinancialFact(ticker="AAPL", source="financials", metric_name="current_price", value=100.0, period="latest")
			],
		)
		company_news_data = FetchArtifact(
			source="company_news",
			status="success",
			documents=[
				DocumentRecord(
					document_id="AAPL::company_news::1",
					ticker="AAPL",
					source="company_news",
					document_type="news_article",
					title="Apple launches new product",
					text="Apple launches a new product line.",
				)
			],
		)
		market_news_data = FetchArtifact(
			source="market_news",
			status="success",
			documents=[
				DocumentRecord(
					document_id="AAPL::market_news::1",
					ticker="AAPL",
					source="market_news",
					document_type="news_article",
					title="Markets rally",
					text="Broad equities moved higher today.",
				)
			],
		)
		company_profile_data = FetchArtifact(
			source="company_profile",
			status="success",
			payload={"profile": {"companyName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics"}},
		)
		macro_data = FetchArtifact(
			source="macro",
			status="success",
			documents=[
				DocumentRecord(
					document_id="AAPL::macro::1",
					ticker="AAPL",
					source="macro",
					document_type="macro_context",
					title="Consumer electronics TAM outlook",
					text="The sector outlook remains supported by replacement cycles and services growth.",
				)
			],
		)

		packet = build_data_ingestion_packet(
			"aapl",
			sec_data,
			financials_data,
			company_news_data,
			market_news_data,
			company_profile_data,
			macro_data,
		)

		self.assertEqual(packet.ticker, "AAPL")
		self.assertEqual(packet.source_links.count("https://example.com/shared"), 1)
		self.assertEqual(len(packet.source_notes), 2)
		self.assertEqual(packet.raw_research_packet["source_status"]["sec"], "success")
		self.assertEqual(packet.raw_research_packet["financial_fact_counts"]["financials"], 1)
		self.assertEqual(packet.raw_research_packet["source_status"]["company_news"], "success")
		self.assertEqual(packet.raw_research_packet["source_status"]["macro"], "success")
		self.assertEqual(packet.raw_research_packet["macro_context"]["sector"], "Technology")
		self.assertEqual(packet.raw_research_packet["macro_context"]["industry"], "Consumer Electronics")

	def test_artifact_cache_round_trip(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			cache_path = Path(temp_dir) / "artifact.json"
			artifact = FetchArtifact(
				source="financials",
				status="success",
				financial_facts=[
					FinancialFact(ticker="MSFT", source="financials", metric_name="current_price", value=123.45, period="latest")
				],
				source_notes=[SourceNote(title="Snapshot", snippet="latest data", source_type="financials")],
			)

			write_cached_artifact(cache_path, artifact)
			cached = read_cached_artifact(cache_path, ttl_seconds=60)

			self.assertIsNotNone(cached)
			assert cached is not None
			self.assertEqual(cached.source, "financials")
			self.assertEqual(cached.financial_facts[0].metric_name, "current_price")
			self.assertTrue(cached.metadata.get("cache_hit"))

	def test_persist_data_ingestion_packet_writes_sqlite_rows(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			db_path = Path(temp_dir) / "data_ingestion.db"
			packet = build_data_ingestion_packet(
				"AAPL",
				FetchArtifact(
					source="sec",
					status="success",
					documents=[
						DocumentRecord(
							document_id="AAPL::sec::1",
							ticker="AAPL",
							source="sec",
							document_type="risk_factors",
							title="Risk Factors",
							text="Competition and regulation remain important risks.",
						)
					],
				),
				FetchArtifact(
					source="financials",
					status="success",
					financial_facts=[
						FinancialFact(ticker="AAPL", source="financials", metric_name="current_price", value=189.0, period="latest"),
						FinancialFact(ticker="AAPL", source="financials", metric_name="operating_margin", value=0.31, period="2025-09-30"),
					],
				),
				FetchArtifact(
					source="company_news",
					status="success",
					documents=[
						DocumentRecord(
							document_id="AAPL::company_news::1",
							ticker="AAPL",
							source="company_news",
							document_type="news_article",
							title="Apple supplier update",
							text="Supply chain news item.",
						)
					],
				),
				FetchArtifact(
					source="market_news",
					status="success",
					documents=[
						DocumentRecord(
							document_id="AAPL::market_news::1",
							ticker="AAPL",
							source="market_news",
							document_type="news_article",
							title="Macro update",
							text="Rates remain in focus.",
						)
					],
				),
				FetchArtifact(
					source="company_profile",
					status="success",
					documents=[
						DocumentRecord(
							document_id="AAPL::company_profile::1",
							ticker="AAPL",
							source="company_profile",
							document_type="company_profile",
							title="Apple profile",
							text="Apple operates in technology.",
						)
					],
					payload={"profile": {"sector": "Technology", "industry": "Consumer Electronics"}},
				),
				sqlite_db_path=db_path,
				chroma_path=Path(temp_dir) / "chroma",
			)

			result = persist_data_ingestion_packet(packet, sqlite_db_path=db_path, include_chroma=False)

			self.assertEqual(result["document_count"], 4)
			self.assertEqual(result["financial_fact_count"], 2)
			with closing(sqlite3.connect(db_path)) as connection:
				document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
				fact_count = connection.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0]
				run_count = connection.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0]
			self.assertEqual(document_count, 4)
			self.assertEqual(fact_count, 2)
			self.assertEqual(run_count, 1)

	def test_persist_data_ingestion_packet_replaces_existing_ticker_rows(self) -> None:
		with tempfile.TemporaryDirectory() as temp_dir:
			db_path = Path(temp_dir) / "data_ingestion.db"
			first_packet = build_data_ingestion_packet(
				"AAPL",
				FetchArtifact(
					source="sec",
					status="success",
					documents=[
						DocumentRecord(
							document_id="AAPL::sec::1",
							ticker="AAPL",
							source="sec",
							document_type="mda",
							title="MD&A",
							text="Original text",
						)
					],
				),
				FetchArtifact(
					source="financials",
					status="success",
					financial_facts=[
						FinancialFact(ticker="AAPL", source="financials", metric_name="current_price", value=100.0, period="latest"),
					],
				),
				sqlite_db_path=db_path,
				chroma_path=Path(temp_dir) / "chroma",
			)
			second_packet = build_data_ingestion_packet(
				"AAPL",
				FetchArtifact(
					source="sec",
					status="success",
					documents=[
						DocumentRecord(
							document_id="AAPL::sec::1",
							ticker="AAPL",
							source="sec",
							document_type="mda",
							title="MD&A",
							text="Updated text",
						)
					],
				),
				FetchArtifact(
					source="financials",
					status="success",
					financial_facts=[
						FinancialFact(ticker="AAPL", source="financials", metric_name="current_price", value=200.0, period="latest"),
					],
				),
				sqlite_db_path=db_path,
				chroma_path=Path(temp_dir) / "chroma",
			)

			persist_data_ingestion_packet(first_packet, sqlite_db_path=db_path, include_chroma=False)
			persist_data_ingestion_packet(second_packet, sqlite_db_path=db_path, include_chroma=False)

			with closing(sqlite3.connect(db_path)) as connection:
				run_count = connection.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0]
				document_count = connection.execute("SELECT COUNT(*) FROM documents WHERE ticker = 'AAPL'").fetchone()[0]
				fact_count = connection.execute("SELECT COUNT(*) FROM financial_facts WHERE ticker = 'AAPL'").fetchone()[0]
				document_text = connection.execute("SELECT text FROM documents WHERE document_id = 'AAPL::sec::1'").fetchone()[0]
				current_price = connection.execute(
					"SELECT value FROM financial_facts WHERE ticker = 'AAPL' AND metric_name = 'current_price' AND period = 'latest'"
				).fetchone()[0]
			self.assertEqual(run_count, 1)
			self.assertEqual(document_count, 1)
			self.assertEqual(fact_count, 1)
			self.assertEqual(document_text, "Updated text")
			self.assertEqual(current_price, 200.0)

	def test_chunk_text_documents_keeps_filter_and_order_metadata(self) -> None:
		chunks = chunk_text_documents(
			[
				DocumentRecord(
					document_id="AAPL::sec::1",
					ticker="aapl",
					source="sec",
					document_type="mda",
					title="MD&A",
					text="A" * 1200,
				)
			],
			chunk_size=500,
			chunk_overlap=0,
		)

		self.assertGreaterEqual(len(chunks), 2)
		self.assertEqual(chunks[0]["metadata"]["document_id"], "AAPL::sec::1")
		self.assertEqual(chunks[0]["metadata"]["ticker"], "AAPL")
		self.assertEqual(chunks[0]["metadata"]["source"], "sec")
		self.assertEqual(chunks[0]["metadata"]["chunk_index"], 0)

	def test_get_chroma_chunks_sorts_results_into_stable_document_order(self) -> None:
		class FakeCollection:
			def get(self, **kwargs):
				self.kwargs = kwargs
				return {
					"ids": [
						"AAPL::sec::2::chunk::1",
						"AAPL::sec::1::chunk::2",
						"AAPL::sec::1::chunk::0",
					],
					"documents": [
						"Second document later chunk",
						"First document later chunk",
						"First document first chunk",
					],
					"metadatas": [
						{"document_id": "AAPL::sec::2", "chunk_index": 1, "ticker": "AAPL", "source": "sec"},
						{"document_id": "AAPL::sec::1", "chunk_index": 2, "ticker": "AAPL", "source": "sec"},
						{"document_id": "AAPL::sec::1", "chunk_index": 0, "ticker": "AAPL", "source": "sec"},
					],
				}

		class FakeClient:
			def __init__(self, collection):
				self.collection = collection

			def get_or_create_collection(self, name):
				self.name = name
				return self.collection

		with tempfile.TemporaryDirectory() as temp_dir:
			collection = FakeCollection()
			fake_client = FakeClient(collection)
			with patch("agent.storage.chromadb") as mocked_chromadb:
				mocked_chromadb.PersistentClient.return_value = fake_client
				chunks = get_chroma_chunks("aapl", source="sec", chroma_path=Path(temp_dir))

		self.assertEqual(
			[item["id"] for item in chunks],
			[
				"AAPL::sec::1::chunk::0",
				"AAPL::sec::1::chunk::2",
				"AAPL::sec::2::chunk::1",
			],
		)
		self.assertEqual(
			collection.kwargs["where"],
			{"$and": [{"ticker": "AAPL"}, {"source": "sec"}]},
		)


if __name__ == "__main__":
	unittest.main()
