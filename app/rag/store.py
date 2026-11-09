"""PostgreSQL and pgvector storage implementation for BoardBridge chunks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

import psycopg
from pgvector.psycopg import register_vector

if TYPE_CHECKING:
    from app.rag.chunking import Chunk


def schema_sql(dim: int = 384) -> str:
    """Generate SQL DDL for pgvector extension, chunks table, and indexes."""
    return f"""
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS chunks (
        id BIGSERIAL PRIMARY KEY,
        doc_id TEXT NOT NULL,
        source_file TEXT NOT NULL,
        page INTEGER NOT NULL,
        section TEXT NOT NULL DEFAULT '',
        chunk_index INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'text',
        text TEXT NOT NULL,
        content_hash TEXT NOT NULL UNIQUE,
        model TEXT NOT NULL,
        embedding VECTOR({dim}) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);

    CREATE INDEX IF NOT EXISTS chunks_doc_page
    ON chunks (doc_id, page);
    """


def connect(url: str, dim: int = 384) -> psycopg.Connection[Any]:
    """Connect to PostgreSQL, initialize schema, and register pgvector types."""
    conn = psycopg.connect(url, autocommit=True)
    # Execute schema initialization first
    with conn.cursor() as cur:
        cur.execute(schema_sql(dim))
    # Register vector type strictly after the vector extension is active
    register_vector(conn)
    return conn


def existing_hashes(conn: psycopg.Connection[Any], hashes: Iterable[str]) -> set[str]:
    """Query database for content hashes that already exist in the chunks table."""
    hash_list = list(hashes)
    if not hash_list:
        return set()

    with conn.cursor() as cur:
        # Use ANY array parameter to query in one efficient round-trip
        cur.execute(
            "SELECT content_hash FROM chunks WHERE content_hash = ANY(%s);",
            (hash_list,),
        )
        rows = cur.fetchall()
        return {r[0] for r in rows}


def count_chunks(conn: psycopg.Connection[Any]) -> int:
    """Return the total number of records currently stored in the chunks table."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM chunks;")
        row = cur.fetchone()
        return int(row[0]) if row else 0


def insert_chunks(
    conn: psycopg.Connection[Any],
    chunks: list[Chunk],
    vectors: list[list[float]],
    model: str,
) -> int:
    """Insert chunks and embeddings into pgvector, ignoring duplicate content hashes.

    Returns the number of newly inserted rows.
    """
    if len(chunks) != len(vectors):
        raise ValueError(f"Chunks count ({len(chunks)}) and vectors count ({len(vectors)}) must match.")

    if not chunks:
        return 0

    initial_count = count_chunks(conn)

    params = [
        (
            c.doc_id,
            c.source_file,
            c.page,
            c.section,
            c.chunk_index,
            c.kind,
            c.text,
            c.content_hash,
            model,
            v,
        )
        for c, v in zip(chunks, vectors, strict=True)
    ]

    insert_query = """
    INSERT INTO chunks (
        doc_id, source_file, page, section, chunk_index, kind, text, content_hash, model, embedding
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
    )
    ON CONFLICT (content_hash) DO NOTHING;
    """

    with conn.cursor() as cur:
        cur.executemany(insert_query, params)

    final_count = count_chunks(conn)
    return final_count - initial_count
