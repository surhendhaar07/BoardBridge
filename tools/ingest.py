"""Idempotent document ingestion pipeline for BoardBridge pgvector storage.

Loads parsed JSONL records, chunks text and tables, prevents duplicates at three
levels (in-batch, pre-embedding database check, and ON CONFLICT insert), embeds
only new chunks, and records run metrics.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path
from typing import Any

from app.rag.chunking import Chunk, chunk_pages
from app.rag.embeddings import Embedder, get_embedder
from app.rag.store import connect, count_chunks, existing_hashes, insert_chunks


def load_pages(folder: Path | str) -> list[dict[str, Any]]:
    """Load parsed records strictly from *.jsonl files in folder, ignoring sample_pages.json."""
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return []

    jsonl_files = sorted(folder_path.glob("*.jsonl"))
    pages: list[dict[str, Any]] = []

    for fpath in jsonl_files:
        with open(fpath, encoding="utf-8") as f:
            for line_no, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    pages.append(record)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Malformed JSON in {fpath.name} at line {line_no}: {exc}") from exc

    return pages


def append_report_row(report_file: Path, stats: dict[str, Any]) -> None:
    """Append a structured run row to INGESTION.md, initializing headers if needed."""
    date_str = datetime.date.today().isoformat()
    skipped_total = stats["duplicates"] + stats["already_stored"]
    skipped_str = f"{skipped_total} ({stats['duplicates']} batch, {stats['already_stored']} db)"

    row = (
        f"| {date_str} | {stats['pages']} | {stats['pages_no_text']} | {stats['chunks']} | "
        f"{skipped_str} | {stats['stored']} | {stats['rows_in_table']} | "
        f"{stats['seconds']}s | {stats['model']} ({stats['dim']}) | 1000/150 |\n"
    )

    cols_header = (
        "| Date | Pages | No-text pages | Chunks made | Skipped (duplicate) | "
        "New stored | Rows in table | Seconds | Model (dim) | Chunk/overlap |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )

    if not report_file.exists():
        header = "# BoardBridge Ingestion Run Log\n\n" + cols_header
        report_file.write_text(header + row, encoding="utf-8")
    else:
        content = report_file.read_text(encoding="utf-8")
        if "| Date | Pages |" not in content:
            content = content.rstrip() + "\n\n" + cols_header
        # Append row after table header
        report_file.write_text(content.rstrip() + "\n" + row, encoding="utf-8")


def ingest(
    folder: Path | str,
    db_url: str = "postgresql://app:app@localhost:5432/rag",
    max_pages: int | None = None,
    batch: int = 64,
    embedder: Embedder | None = None,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Execute end-to-end idempotent ingestion into PostgreSQL/pgvector."""
    start_time = time.perf_counter()

    if embedder is None:
        embedder = get_embedder()

    # 1. Load parsed pages
    all_pages = load_pages(folder)
    selected_pages = all_pages[:max_pages] if max_pages is not None else all_pages

    # 2. Identify no-text / skipped pages
    usable_pages: list[dict[str, Any]] = []
    no_text_count = 0

    for p in selected_pages:
        method = p.get("method", "text")
        text = p.get("text", "").strip()
        tables = p.get("tables", [])
        if method in {"needs_ocr", "empty"} or (not text and not tables):
            no_text_count += 1
        else:
            usable_pages.append(p)

    # 3. Chunk usable documents
    generated_chunks: list[Chunk] = chunk_pages(usable_pages)

    # 4. Level 1 Deduplication: within the batch using content_hash
    unique_chunks: list[Chunk] = []
    seen_hashes_batch: set[str] = set()
    batch_duplicates = 0

    for c in generated_chunks:
        if c.content_hash in seen_hashes_batch:
            batch_duplicates += 1
        else:
            seen_hashes_batch.add(c.content_hash)
            unique_chunks.append(c)

    # 5. Connect to PostgreSQL and pgvector
    conn = connect(db_url, dim=embedder.dim)
    new_chunks_stored = 0
    already_stored_count = 0

    try:
        # 6. Level 2 Deduplication: check existing database hashes before embedding
        all_unique_hashes = [c.content_hash for c in unique_chunks]
        known_hashes = existing_hashes(conn, all_unique_hashes)
        already_stored_count = len(known_hashes)

        # 7. Identify only new chunks needing embedding
        new_chunks = [c for c in unique_chunks if c.content_hash not in known_hashes]

        # 8. Embed and insert in batches of `batch` (default 64)
        for i in range(0, len(new_chunks), batch):
            chunk_slice = new_chunks[i : i + batch]
            # Embed with section context added to prompt input
            embed_inputs = [f"{c.section}\n{c.text}".strip() if c.section else c.text for c in chunk_slice]
            vectors = embedder.embed(embed_inputs)
            # Insert original text without modification
            inserted = insert_chunks(conn, chunk_slice, vectors, model=embedder.model)
            new_chunks_stored += inserted

        total_rows = count_chunks(conn)

    finally:
        conn.close()

    elapsed = round(time.perf_counter() - start_time, 2)

    stats: dict[str, Any] = {
        "pages": len(selected_pages),
        "pages_no_text": no_text_count,
        "chunks": len(generated_chunks),
        "duplicates": batch_duplicates,
        "already_stored": already_stored_count,
        "stored": new_chunks_stored,
        "rows_in_table": total_rows,
        "seconds": elapsed,
        "model": embedder.model,
        "dim": embedder.dim,
    }

    if report_path:
        append_report_row(Path(report_path), stats)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="BoardBridge Ingestion Pipeline")
    parser.add_argument(
        "folder",
        nargs="?",
        default="data/parsed",
        help="Path to folder containing parsed JSONL files (default: data/parsed)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Maximum pages to process (default: None = all)",
    )
    parser.add_argument(
        "--report",
        default="INGESTION.md",
        help="Path to markdown ingestion report (default: INGESTION.md)",
    )
    parser.add_argument(
        "--db",
        default="postgresql://app:app@localhost:5432/rag",
        help="PostgreSQL connection URL (default: postgresql://app:app@localhost:5432/rag)",
    )
    parser.add_argument(
        "--provider",
        choices=["fake", "local"],
        default=None,
        help="Embedding provider override (fake or local)",
    )

    args = parser.parse_args()

    # Determine embedding provider
    if args.provider:
        from app.config import Settings

        settings = Settings(embedding_provider=args.provider)
        embedder = get_embedder(settings)
    else:
        embedder = get_embedder()

    try:
        stats = ingest(
            folder=Path(args.folder),
            db_url=args.db,
            max_pages=args.max_pages,
            embedder=embedder,
            report_path=Path(args.report) if args.report else None,
        )
        print(json.dumps(stats, indent=2))
    except Exception as exc:
        print(f"Ingestion error: {type(exc).__name__} - {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
