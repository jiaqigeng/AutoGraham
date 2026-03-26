from __future__ import annotations

from contextlib import closing
import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
	import chromadb
except ImportError:  # pragma: no cover - optional dependency
	chromadb = None  # type: ignore[assignment]

try:
	from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover - optional dependency
	RecursiveCharacterTextSplitter = None  # type: ignore[assignment]


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SQLITE_DB_PATH = _REPO_ROOT / "data" / "warehouse" / "autograham.db"
_DEFAULT_CHROMA_PATH = _REPO_ROOT / "data" / "chroma"


def _ensure_directory(path: Path) -> None:
	path.mkdir(parents=True, exist_ok=True)


def _json_default(value: Any) -> Any:
	return str(value)


def _json_dumps(payload: Any) -> str:
	return json.dumps(payload, default=_json_default, sort_keys=True)


def _record_value(record: Any, field_name: str, default: Any = None) -> Any:
	if isinstance(record, Mapping):
		return record.get(field_name, default)
	return getattr(record, field_name, default)


def _record_dict(record: Any) -> dict[str, Any]:
	if hasattr(record, "to_dict"):
		return dict(record.to_dict())
	if isinstance(record, Mapping):
		return dict(record)
	raise TypeError(f"Unsupported record type: {type(record)!r}")


def _normalize_chroma_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
	normalized: dict[str, Any] = {}
	for key, value in payload.items():
		if value is None:
			continue
		if isinstance(value, (str, int, float, bool)):
			normalized[str(key)] = value
		else:
			normalized[str(key)] = _json_dumps(value)
	return normalized


def _coerce_int(value: Any, default: int = 0) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default


def default_sqlite_db_path() -> Path:
	return _DEFAULT_SQLITE_DB_PATH


def default_chroma_path() -> Path:
	return _DEFAULT_CHROMA_PATH


def initialize_sqlite(db_path: str | Path | None = None) -> Path:
	target = Path(db_path) if db_path is not None else _DEFAULT_SQLITE_DB_PATH
	_ensure_directory(target.parent)
	with closing(sqlite3.connect(target)) as connection:
		connection.execute("PRAGMA journal_mode=DELETE")
		connection.execute("PRAGMA foreign_keys=ON")
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS ingestion_runs (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				ticker TEXT NOT NULL,
				created_at TEXT NOT NULL,
				sources_json TEXT NOT NULL,
				document_count INTEGER NOT NULL DEFAULT 0,
				financial_fact_count INTEGER NOT NULL DEFAULT 0
			)
			"""
		)
		connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ingestion_runs_ticker ON ingestion_runs(ticker)")
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS documents (
				document_id TEXT PRIMARY KEY,
				ticker TEXT NOT NULL,
				source TEXT NOT NULL,
				document_type TEXT NOT NULL,
				title TEXT NOT NULL,
				published_at TEXT,
				url TEXT,
				content_hash TEXT NOT NULL,
				text TEXT NOT NULL,
				metadata_json TEXT NOT NULL DEFAULT '{}'
			)
			"""
		)
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS financial_facts (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				ticker TEXT NOT NULL,
				source TEXT NOT NULL,
				metric_name TEXT NOT NULL,
				period TEXT NOT NULL DEFAULT '',
				as_of_date TEXT,
				statement_type TEXT NOT NULL DEFAULT '',
				value REAL NOT NULL,
				unit TEXT,
				currency TEXT,
				metadata_json TEXT NOT NULL DEFAULT '{}',
				UNIQUE (ticker, source, metric_name, period, as_of_date, statement_type)
			)
			"""
		)
		connection.execute(
			"""
			CREATE TABLE IF NOT EXISTS document_chunks (
				chunk_id TEXT PRIMARY KEY,
				document_id TEXT NOT NULL,
				ticker TEXT NOT NULL,
				source TEXT NOT NULL,
				chunk_index INTEGER NOT NULL,
				text TEXT NOT NULL,
				metadata_json TEXT NOT NULL DEFAULT '{}',
				FOREIGN KEY (document_id) REFERENCES documents(document_id)
			)
			"""
		)
	return target


def record_ingestion_run(
	ticker: str,
	*,
	sources_json: Mapping[str, Any],
	document_count: int,
	financial_fact_count: int,
	db_path: str | Path | None = None,
	created_at: str,
) -> int:
	target = initialize_sqlite(db_path)
	clean_ticker = ticker.strip().upper()
	with closing(sqlite3.connect(target)) as connection:
		connection.execute(
			"""
			INSERT INTO ingestion_runs (ticker, created_at, sources_json, document_count, financial_fact_count)
			VALUES (?, ?, ?, ?, ?)
			ON CONFLICT(ticker) DO UPDATE SET
				created_at = excluded.created_at,
				sources_json = excluded.sources_json,
				document_count = excluded.document_count,
				financial_fact_count = excluded.financial_fact_count
			""",
			(
				clean_ticker,
				created_at,
				_json_dumps(dict(sources_json)),
				int(document_count),
				int(financial_fact_count),
			),
		)
		connection.commit()
		row = connection.execute("SELECT id FROM ingestion_runs WHERE ticker = ?", (clean_ticker,)).fetchone()
		return int(row[0]) if row else 0


def replace_ticker_data(ticker: str, *, db_path: str | Path | None = None) -> None:
	target = initialize_sqlite(db_path)
	clean_ticker = ticker.strip().upper()
	with closing(sqlite3.connect(target)) as connection:
		document_rows = connection.execute(
			"SELECT document_id FROM documents WHERE ticker = ?",
			(clean_ticker,),
		).fetchall()
		document_ids = [str(row[0]) for row in document_rows if row and row[0]]
		if document_ids:
			placeholders = ",".join("?" for _ in document_ids)
			connection.execute(
				f"DELETE FROM document_chunks WHERE document_id IN ({placeholders})",
				document_ids,
			)
		connection.execute("DELETE FROM documents WHERE ticker = ?", (clean_ticker,))
		connection.execute("DELETE FROM financial_facts WHERE ticker = ?", (clean_ticker,))
		connection.commit()


def upsert_documents(documents: Sequence[Any], *, db_path: str | Path | None = None) -> int:
	if not documents:
		initialize_sqlite(db_path)
		return 0
	target = initialize_sqlite(db_path)
	rows = []
	for record in documents:
		payload = _record_dict(record)
		rows.append(
			(
				str(payload.get("document_id") or ""),
				str(payload.get("ticker") or "").strip().upper(),
				str(payload.get("source") or ""),
				str(payload.get("document_type") or ""),
				str(payload.get("title") or ""),
				str(payload.get("published_at")) if payload.get("published_at") else None,
				str(payload.get("url")) if payload.get("url") else None,
				str(payload.get("content_hash") or ""),
				str(payload.get("text") or ""),
				_json_dumps(dict(payload.get("metadata") or {})),
			)
		)
	with closing(sqlite3.connect(target)) as connection:
		connection.executemany(
			"""
			INSERT INTO documents (
				document_id, ticker, source, document_type, title,
				published_at, url, content_hash, text, metadata_json
			)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(document_id) DO UPDATE SET
				ticker = excluded.ticker,
				source = excluded.source,
				document_type = excluded.document_type,
				title = excluded.title,
				published_at = excluded.published_at,
				url = excluded.url,
				content_hash = excluded.content_hash,
				text = excluded.text,
				metadata_json = excluded.metadata_json
			""",
			rows,
		)
		connection.commit()
	return len(rows)


def upsert_financial_facts(financial_facts: Sequence[Any], *, db_path: str | Path | None = None) -> int:
	if not financial_facts:
		initialize_sqlite(db_path)
		return 0
	target = initialize_sqlite(db_path)
	rows = []
	for record in financial_facts:
		payload = _record_dict(record)
		try:
			numeric_value = float(payload.get("value"))
		except (TypeError, ValueError):
			continue
		if not math.isfinite(numeric_value):
			continue
		rows.append(
			(
				str(payload.get("ticker") or "").strip().upper(),
				str(payload.get("source") or ""),
				str(payload.get("metric_name") or ""),
				str(payload.get("period") or ""),
				str(payload.get("as_of_date")) if payload.get("as_of_date") else None,
				str(payload.get("statement_type") or ""),
				numeric_value,
				str(payload.get("unit")) if payload.get("unit") else None,
				str(payload.get("currency")) if payload.get("currency") else None,
				_json_dumps(dict(payload.get("metadata") or {})),
			)
		)
	with closing(sqlite3.connect(target)) as connection:
		connection.executemany(
			"""
			INSERT INTO financial_facts (
				ticker, source, metric_name, period, as_of_date,
				statement_type, value, unit, currency, metadata_json
			)
			VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(ticker, source, metric_name, period, as_of_date, statement_type) DO UPDATE SET
				value = excluded.value,
				unit = excluded.unit,
				currency = excluded.currency,
				metadata_json = excluded.metadata_json
			""",
			rows,
		)
		connection.commit()
	return len(rows)


def _fallback_split_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
	if not text:
		return []
	if chunk_size <= 0:
		return [text]
	overlap = max(0, min(chunk_overlap, chunk_size - 1))
	step = max(1, chunk_size - overlap)
	chunks: list[str] = []
	for start in range(0, len(text), step):
		chunk = text[start : start + chunk_size].strip()
		if chunk:
			chunks.append(chunk)
		if start + chunk_size >= len(text):
			break
	return chunks


def chunk_text_documents(
	documents: Sequence[Any],
	*,
	chunk_size: int = 1000,
	chunk_overlap: int = 150,
) -> list[dict[str, Any]]:
	if not documents:
		return []
	if RecursiveCharacterTextSplitter is not None:
		splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
		split = splitter.split_text
	else:
		split = lambda text: _fallback_split_text(text, chunk_size, chunk_overlap)

	chunks: list[dict[str, Any]] = []
	for document in documents:
		payload = _record_dict(document)
		text_chunks = split(str(payload.get("text") or ""))
		for index, chunk in enumerate(text_chunks):
			chunks.append(
				{
					"chunk_id": f"{payload.get('document_id')}::chunk::{index}",
					"document_id": str(payload.get("document_id") or ""),
					"ticker": str(payload.get("ticker") or "").strip().upper(),
					"source": str(payload.get("source") or ""),
					"chunk_index": index,
					"text": chunk,
					"metadata": {
						**dict(payload.get("metadata") or {}),
						"document_id": payload.get("document_id"),
						"ticker": str(payload.get("ticker") or "").strip().upper(),
						"source": payload.get("source"),
						"chunk_index": index,
						"document_type": payload.get("document_type"),
						"title": payload.get("title"),
						"url": payload.get("url"),
					},
				}
			)
	return chunks


def upsert_document_chunks(chunks: Sequence[Mapping[str, Any]], *, db_path: str | Path | None = None) -> int:
	if not chunks:
		initialize_sqlite(db_path)
		return 0
	target = initialize_sqlite(db_path)
	rows = [
		(
			str(item.get("chunk_id") or ""),
			str(item.get("document_id") or ""),
			str(item.get("ticker") or "").strip().upper(),
			str(item.get("source") or ""),
			int(item.get("chunk_index") or 0),
			str(item.get("text") or ""),
			_json_dumps(dict(item.get("metadata") or {})),
		)
		for item in chunks
	]
	with closing(sqlite3.connect(target)) as connection:
		connection.executemany(
			"""
			INSERT INTO document_chunks (
				chunk_id, document_id, ticker, source, chunk_index, text, metadata_json
			)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(chunk_id) DO UPDATE SET
				document_id = excluded.document_id,
				ticker = excluded.ticker,
				source = excluded.source,
				chunk_index = excluded.chunk_index,
				text = excluded.text,
				metadata_json = excluded.metadata_json
			""",
			rows,
		)
		connection.commit()
	return len(rows)


def upsert_chroma_documents(
	documents: Sequence[Any],
	*,
	chroma_path: str | Path | None = None,
	collection_name: str = "autograham_docs",
	chunk_size: int = 1000,
	chunk_overlap: int = 150,
) -> dict[str, Any]:
	target = Path(chroma_path) if chroma_path is not None else _DEFAULT_CHROMA_PATH
	_ensure_directory(target)
	if chromadb is None:
		return {"status": "skipped", "reason": "chromadb is not installed", "upserted_count": 0, "collection_name": collection_name}
	chunks = chunk_text_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
	if not chunks:
		return {"status": "empty", "upserted_count": 0, "collection_name": collection_name}
	client = chromadb.PersistentClient(path=str(target))
	collection = client.get_or_create_collection(collection_name)
	collection.upsert(
		ids=[str(item["chunk_id"]) for item in chunks],
		documents=[str(item["text"]) for item in chunks],
		metadatas=[_normalize_chroma_metadata(dict(item.get("metadata") or {})) for item in chunks],
		embeddings=[[0.0, 0.0, 0.0] for _ in chunks],
	)
	return {"status": "success", "upserted_count": len(chunks), "collection_name": collection_name}


def get_chroma_chunks(
	ticker: str,
	*,
	source: str | None = None,
	chroma_path: str | Path | None = None,
	collection_name: str = "autograham_docs",
	limit: int | None = None,
) -> list[dict[str, Any]]:
	target = Path(chroma_path) if chroma_path is not None else _DEFAULT_CHROMA_PATH
	if chromadb is None or not target.exists():
		return []
	client = chromadb.PersistentClient(path=str(target))
	collection = client.get_or_create_collection(collection_name)
	where: dict[str, Any]
	if source:
		where = {"$and": [{"ticker": ticker.strip().upper()}, {"source": source}]}
	else:
		where = {"ticker": ticker.strip().upper()}
	result = collection.get(where=where, include=["documents", "metadatas"])
	documents = list(result.get("documents") or [])
	metadatas = list(result.get("metadatas") or [])
	ids = list(result.get("ids") or [])
	items = [
		{
			"id": str(chunk_id),
			"text": str(document or ""),
			"metadata": dict(metadata or {}),
		}
		for chunk_id, document, metadata in zip(ids, documents, metadatas)
	]
	items.sort(
		key=lambda item: (
			str(dict(item.get("metadata") or {}).get("document_id") or ""),
			_coerce_int(dict(item.get("metadata") or {}).get("chunk_index")),
			str(item.get("id") or ""),
		)
	)
	if limit is not None:
		return items[:limit]
	return items


def get_sqlite_financial_facts(
	ticker: str,
	*,
	metric_names: Sequence[str] | None = None,
	db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
	target = initialize_sqlite(db_path)
	clean_ticker = ticker.strip().upper()
	query = """
		SELECT ticker, source, metric_name, period, as_of_date, statement_type, value, unit, currency, metadata_json
		FROM financial_facts
		WHERE ticker = ?
	"""
	parameters: list[Any] = [clean_ticker]
	if metric_names:
		placeholders = ",".join("?" for _ in metric_names)
		query += f" AND metric_name IN ({placeholders})"
		parameters.extend(metric_names)
	query += " ORDER BY COALESCE(as_of_date, period) DESC, metric_name ASC"
	with closing(sqlite3.connect(target)) as connection:
		rows = connection.execute(query, parameters).fetchall()
	return [
		{
			"ticker": str(row[0]),
			"source": str(row[1]),
			"metric_name": str(row[2]),
			"period": str(row[3]),
			"as_of_date": str(row[4]) if row[4] is not None else None,
			"statement_type": str(row[5]),
			"value": float(row[6]),
			"unit": str(row[7]) if row[7] is not None else None,
			"currency": str(row[8]) if row[8] is not None else None,
			"metadata": json.loads(str(row[9] or "{}")),
		}
		for row in rows
	]


def _artifact_records(packet: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
	artifacts = [
		_record_value(packet, "sec_data"),
		_record_value(packet, "financials_data"),
		_record_value(packet, "company_news_data"),
		_record_value(packet, "market_news_data"),
		_record_value(packet, "company_profile_data"),
		_record_value(packet, "macro_data"),
	]
	documents = [
		_record_dict(item)
		for artifact in artifacts
		for item in list(_record_value(artifact, "documents", []) or [])
	]
	financial_facts = [
		_record_dict(item)
		for artifact in artifacts
		for item in list(_record_value(artifact, "financial_facts", []) or [])
	]
	source_status = dict(_record_value(packet, "raw_research_packet", {}).get("source_status") or {})
	return documents, financial_facts, source_status


def persist_data_ingestion_packet(
	packet: Any,
	*,
	sqlite_db_path: str | Path | None = None,
	chroma_path: str | Path | None = None,
	include_chroma: bool = True,
	collection_name: str = "autograham_docs",
) -> dict[str, Any]:
	target_db = initialize_sqlite(sqlite_db_path)
	clean_ticker = str(_record_value(packet, "ticker", "")).strip().upper()
	replace_ticker_data(clean_ticker, db_path=target_db)
	documents, financial_facts, source_status = _artifact_records(packet)
	document_count = upsert_documents(documents, db_path=target_db)
	financial_fact_count = upsert_financial_facts(financial_facts, db_path=target_db)
	chunks = chunk_text_documents(documents)
	chunk_count = upsert_document_chunks(chunks, db_path=target_db)
	chroma_result = {"status": "skipped", "upserted_count": 0, "collection_name": collection_name}
	if include_chroma:
		chroma_result = upsert_chroma_documents(documents, chroma_path=chroma_path, collection_name=collection_name)
	run_id = record_ingestion_run(
		clean_ticker,
		sources_json=source_status,
		document_count=document_count,
		financial_fact_count=financial_fact_count,
		db_path=target_db,
		created_at=str(_record_value(packet, "created_at", "")),
	)
	return {
		"run_id": run_id,
		"sqlite_db_path": str(target_db),
		"document_count": document_count,
		"financial_fact_count": financial_fact_count,
		"chunk_count": chunk_count,
		"chroma": chroma_result,
	}


__all__ = [
	"chunk_text_documents",
	"default_chroma_path",
	"default_sqlite_db_path",
	"get_chroma_chunks",
	"get_sqlite_financial_facts",
	"initialize_sqlite",
	"persist_data_ingestion_packet",
	"record_ingestion_run",
	"replace_ticker_data",
	"upsert_chroma_documents",
	"upsert_document_chunks",
	"upsert_documents",
	"upsert_financial_facts",
]
