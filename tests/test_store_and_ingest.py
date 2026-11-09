"""Unit tests for PostgreSQL/pgvector storage and the ingestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.rag.chunking import Chunk
from app.rag.embeddings import FakeEmbedder
from app.rag.store import (
    count_chunks,
    existing_hashes,
    insert_chunks,
    schema_sql,
)
from tools.ingest import ingest, load_pages

# ============================================================================
# STORAGE TESTS
# ============================================================================


def test_schema_sql_contains_correct_dimension_and_indexes():
    sql = schema_sql(dim=384)
    assert "CREATE EXTENSION IF NOT EXISTS vector;" in sql
    assert "embedding VECTOR(384) NOT NULL" in sql
    assert "content_hash TEXT NOT NULL UNIQUE" in sql
    assert "USING hnsw (embedding vector_cosine_ops)" in sql
    assert "CREATE INDEX IF NOT EXISTS chunks_doc_page" in sql

    # Test with custom dimension
    sql_128 = schema_sql(dim=128)
    assert "embedding VECTOR(128) NOT NULL" in sql_128


def test_insert_chunks_validates_matching_lengths():
    mock_conn = MagicMock()
    chunk = Chunk(
        doc_id="test_doc",
        source_file="test.c",
        page=1,
        section="test",
        chunk_index=0,
        kind="text",
        text="Sample text",
        content_hash="hash1",
    )

    # 1 chunk but 2 vectors -> ValueError
    with pytest.raises(ValueError, match="must match"):
        insert_chunks(
            conn=mock_conn,
            chunks=[chunk],
            vectors=[[0.1] * 384, [0.2] * 384],
            model="fake",
        )


def test_existing_hashes_queries_properly():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = [("hash_abc",), ("hash_def",)]

    known = existing_hashes(mock_conn, ["hash_abc", "hash_def", "hash_xyz"])
    assert known == {"hash_abc", "hash_def"}

    # Empty list must return empty set without querying
    assert existing_hashes(mock_conn, []) == set()


def test_count_chunks_queries_table():
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchone.return_value = (42,)

    total = count_chunks(mock_conn)
    assert total == 42


# ============================================================================
# INGESTION TESTS
# ============================================================================


def test_load_pages_loads_only_jsonl_and_ignores_sample_json(tmp_path: Path):
    folder = tmp_path / "data"
    folder.mkdir()

    # Valid JSONL file
    jsonl_file = folder / "records.jsonl"
    r1 = {
        "doc_id": "doc1",
        "source_file": "file1.c",
        "page": 1,
        "text": "Valid text",
        "headings": [],
        "tables": [],
        "method": "code",
    }
    r2 = {
        "doc_id": "doc2",
        "source_file": "file2.c",
        "page": 1,
        "text": "Valid text 2",
        "headings": [],
        "tables": [],
        "method": "code",
    }
    jsonl_file.write_text(f"{json.dumps(r1)}\n\n{json.dumps(r2)}\n", encoding="utf-8")

    # Ignored sample_pages.json file
    sample_file = folder / "sample_pages.json"
    sample_file.write_text(json.dumps([{"doc_id": "ignored"}]), encoding="utf-8")

    pages = load_pages(folder)
    assert len(pages) == 2
    assert pages[0]["doc_id"] == "doc1"
    assert pages[1]["doc_id"] == "doc2"


def test_load_pages_reports_malformed_json_with_filename_and_line(
    tmp_path: Path,
):
    folder = tmp_path / "bad_data"
    folder.mkdir()

    bad_file = folder / "corrupt.jsonl"
    bad_file.write_text('{"doc_id": "valid"}\n{invalid_json_here}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Malformed JSON in corrupt.jsonl at line 2"):
        load_pages(folder)


def test_ingest_pipeline_with_mock_db(tmp_path: Path):
    folder = tmp_path / "parsed"
    folder.mkdir()

    # Create 3 records:
    # 1. Normal record
    # 2. Duplicate record (same content as 1)
    # 3. needs_ocr record (must be skipped)
    rec1 = {
        "doc_id": "doc1",
        "source_file": "test1.c",
        "page": 1,
        "text": "Zephyr RTOS GPIO driver initialization and configuration routines.",
        "headings": ["GPIO Setup"],
        "tables": [],
        "method": "code",
    }
    rec2 = {
        "doc_id": "doc2",
        "source_file": "test2.c",
        "page": 1,
        "text": "Zephyr RTOS GPIO driver initialization and configuration routines.",  # duplicate
        "headings": ["GPIO Setup"],
        "tables": [],
        "method": "code",
    }
    rec3 = {
        "doc_id": "doc3",
        "source_file": "test3.pdf",
        "page": 1,
        "text": "",
        "headings": [],
        "tables": [],
        "method": "needs_ocr",
    }

    jsonl_file = folder / "pages.jsonl"
    lines = [json.dumps(r) for r in [rec1, rec2, rec3]]
    jsonl_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    fake_embedder = FakeEmbedder(dim=384)
    report_md = tmp_path / "INGESTION.md"

    # Mock database connection and operations
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Simulate fresh database: existing_hashes returns empty
    with (
        patch("tools.ingest.connect", return_value=mock_conn),
        patch("tools.ingest.existing_hashes", return_value=set()) as mock_exist,
        patch("tools.ingest.insert_chunks", return_value=1) as mock_ins,
        patch("tools.ingest.count_chunks", return_value=1),
    ):
        stats = ingest(
            folder=folder,
            db_url="postgresql://mock/rag",
            embedder=fake_embedder,
            report_path=report_md,
        )

        assert stats["pages"] == 3
        assert stats["pages_no_text"] == 1  # rec3 was needs_ocr
        assert stats["duplicates"] == 1  # rec2 was duplicate of rec1 in-batch
        assert stats["stored"] == 1
        assert stats["rows_in_table"] == 1
        assert stats["dim"] == 384
        assert stats["model"] == "fake"

        # Verify insert_chunks was called once with 1 chunk
        assert mock_ins.call_count == 1
        assert mock_exist.call_count == 1

        # Check report file was generated
        assert report_md.exists()
        content = report_md.read_text(encoding="utf-8")
        assert "| Pages |" in content
        assert "fake (384)" in content


def test_ingest_idempotency_second_run_stores_zero_new_chunks(tmp_path: Path):
    folder = tmp_path / "parsed"
    folder.mkdir()

    rec = {
        "doc_id": "sensor_doc",
        "source_file": "sensor.c",
        "page": 1,
        "text": "BME280 sensor data reading and temperature compensation algorithm.",
        "headings": ["Compensation"],
        "tables": [],
        "method": "code",
    }
    jsonl_file = folder / "pages.jsonl"
    jsonl_file.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    fake_embedder = FakeEmbedder(dim=384)
    mock_conn = MagicMock()

    # On second run, mock existing_hashes returning the chunk hash (already stored)
    with (
        patch("tools.ingest.connect", return_value=mock_conn),
        patch(
            "tools.ingest.existing_hashes",
            return_value={"mocked_hash_already_in_db"},
        ),
        patch("tools.ingest.insert_chunks") as mock_insert,
        patch("tools.ingest.count_chunks", return_value=5),
    ):
        # We patch chunk.content_hash to match the known hash
        with patch(
            "app.rag.chunking.content_hash",
            return_value="mocked_hash_already_in_db",
        ):
            stats = ingest(
                folder=folder,
                db_url="postgresql://mock/rag",
                embedder=fake_embedder,
            )

            # Pre-embedding check identified hash as already stored
            assert stats["already_stored"] == 1
            assert stats["stored"] == 0
            # Embedding and insert were completely skipped
            assert mock_insert.call_count == 0
