"""BoardBridge RAG module: chunking, document retrieval, and prompt context building."""

from app.rag.chunking import (
    MAX_CHARS,
    MIN_CHARS,
    OVERLAP,
    Chunk,
    chunk_pages,
    content_hash,
    normalise,
    pack,
    split_by_heading,
    strip_table_text,
    table_texts,
)
from app.rag.retrieval import build_rag_messages, retrieve_zephyr_context

__all__ = [
    "MAX_CHARS",
    "MIN_CHARS",
    "OVERLAP",
    "Chunk",
    "chunk_pages",
    "content_hash",
    "normalise",
    "pack",
    "split_by_heading",
    "strip_table_text",
    "table_texts",
    "build_rag_messages",
    "retrieve_zephyr_context",
]

