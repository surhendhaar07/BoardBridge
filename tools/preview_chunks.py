"""Command-line chunk preview tool for BoardBridge.

Loads parsed records from JSONL files, chunks documents, prints statistics,
and displays sample chunks with metadata. Operates completely offline without
requiring a database or embedding model.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

from app.rag.chunking import Chunk, chunk_pages


def load_parsed_pages(folder: Path) -> tuple[list[dict[str, Any]], int, int]:
    """Load parsed records from *.jsonl files in folder, strictly ignoring sample_pages.json.

    Returns:
        (usable_pages, total_raw_records, skipped_records)
    """
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return [], 0, 0

    usable_pages: list[dict[str, Any]] = []
    total_raw = 0
    skipped = 0

    # Search strictly for *.jsonl files; explicitly ignore sample_pages.json
    jsonl_files = sorted(folder.glob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line_s = line.strip()
                    if not line_s:
                        continue
                    total_raw += 1
                    try:
                        record = json.loads(line_s)
                        method = record.get("method", "text")
                        text = record.get("text", "")
                        tables = record.get("tables", [])

                        # Skip needs_ocr and empty records
                        if method in {"needs_ocr", "empty"}:
                            skipped += 1
                            continue
                        if not text.strip() and not tables:
                            skipped += 1
                            continue

                        usable_pages.append(record)
                    except json.JSONDecodeError:
                        skipped += 1
        except Exception as exc:
            print(f"Warning: error reading {jsonl_file}: {exc}", file=sys.stderr)

    return usable_pages, total_raw, skipped


def preview(folder: Path, n: int = 5, seed: int = 9) -> list[Chunk]:
    """Execute chunking preview and print distribution metrics and sample chunks."""
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        print(f"Error: Parsed data folder '{folder}' does not exist.")
        return []

    usable_pages, total_raw, _ = load_parsed_pages(folder)
    if not usable_pages:
        print(f"No usable parsed records found in '{folder}'.")
        return []

    chunks = chunk_pages(usable_pages)

    print(f"Usable pages: {len(usable_pages)} (out of {total_raw} parsed records)")
    print(f"Total chunks: {len(chunks)}")

    if not chunks:
        print("Zero chunks generated.")
        return []

    lengths = [len(c.text) for c in chunks]
    min_len = min(lengths)
    max_len = max(lengths)
    med_len = statistics.median(lengths)

    print(f"Chunk lengths: min = {min_len}, median = {med_len:.1f}, max = {max_len}")
    print()

    # Reproducible sampling using fixed random seed
    rng = random.Random(seed)
    sample_size = min(n, len(chunks))
    sample_chunks = rng.sample(chunks, sample_size)

    for c in sample_chunks:
        section_display = c.section if c.section else "General"
        print(f"--- {c.doc_id} | page {c.page} | {section_display} | #{c.chunk_index} | {c.kind}")
        print()
        print(c.text)
        print()

    return sample_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="BoardBridge Chunk Preview Tool")
    parser.add_argument(
        "folder",
        nargs="?",
        default="data/parsed",
        help="Path to folder containing parsed JSONL files (default: data/parsed)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of random chunks to preview (default: 5)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=9,
        help="Random seed for deterministic chunk selection (default: 9)",
    )

    args = parser.parse_args()
    preview(folder=Path(args.folder), n=args.n, seed=args.seed)


if __name__ == "__main__":
    main()

