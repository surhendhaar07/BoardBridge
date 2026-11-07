"""Document chunking module for BoardBridge RAG ingestion.

Implements heading-first splitting, paragraph packing with word-bounded overlap,
table isolation, content hashing, and metadata preservation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# ============================================================================
# CHUNKING CONSTANTS
# ============================================================================

# MAX_CHARS: Maximum number of characters allowed in a single chunk.
# Set to 1,000 characters because target embedding models (e.g. all-MiniLM-L6-v2)
# enforce a 256 word-piece input limit (~1,000 characters corresponds to ~250 tokens).
MAX_CHARS = 1000

# OVERLAP: Number of characters repeated between consecutive chunks (150 chars).
# Preserves semantic context across chunk boundaries, preventing split statements
# or severed definitions from degrading retrieval relevance.
OVERLAP = 150

# MIN_CHARS: Minimum character threshold for a valid chunk.
# Chunks with fewer than 25 characters are discarded to eliminate trivial fragments,
# empty lines, or isolated formatting artifacts.
MIN_CHARS = 25

# Regex patterns for standalone page footer removal
FOOTER_PATTERNS = [
    re.compile(r"^\s*page\s+\d+(?:\s+(?:of|/)\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),
    re.compile(r"^\s*\[\s*\d+\s*\]\s*$"),
    re.compile(r"^\s*\d+\s+(?:of|/)\s+\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),
]


@dataclass
class Chunk:
    """Standardized RAG document chunk with full provenance metadata."""

    doc_id: str
    source_file: str
    page: int
    section: str
    chunk_index: int
    kind: str  # "text" | "table"
    text: str
    content_hash: str


def normalise(text: str) -> str:
    """Collapse multiple whitespace characters into one space and strip leading/trailing whitespace.

    Preserves actual words, symbols, and punctuation.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def content_hash(text: str) -> str:
    """Compute SHA-256 hexadecimal digest of normalized text.

    Ensures identical text with varying whitespace produces the exact same hash.
    """
    normalized = normalise(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def strip_table_text(text: str, tables: list[Any]) -> str:
    """Remove formatted table representations from page body when tables are available separately."""
    if not tables or not text:
        return text

    # Remove formatted table blocks: e.g. "Table 1:\nCol | Val\n..."
    # Matches "Table \d+:" followed by pipe-delimited lines
    pattern = r"(?:\n\s*)*\bTable\s+\d+:\s*(?:\n\s*(?:[^\n]*\|[^\n]*|[^\n]+))+"
    stripped = re.sub(pattern, "", text).strip()
    return stripped


def is_footer_line(line: str) -> bool:
    """Check if a line matches standalone page footer patterns."""
    trimmed = line.strip()
    return any(p.match(trimmed) for p in FOOTER_PATTERNS)


def split_by_heading(
    text: str,
    headings: list[str],
    section: str,
) -> list[tuple[str, str]]:
    """Split text into (section, body) pairs based on exact heading matches.

    - Matches lines exactly against headings.
    - Each matching heading starts a new section.
    - If a page has no headings, continues using the existing section context.
    - Strips standalone page-footer lines (e.g. 'Page 3', 'Page 3 of 40').
    """
    if not text or not text.strip():
        return [(section, "")]

    clean_headings = {h.strip() for h in headings if h and h.strip()}
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()

    pairs: list[tuple[str, str]] = []
    current_section = section
    accumulated_lines: list[str] = []

    for line in lines:
        trimmed = line.strip()

        # Remove standalone footers
        if is_footer_line(trimmed):
            continue

        # Check for heading match
        if trimmed in clean_headings:
            body_content = "\n".join(accumulated_lines).strip()
            if body_content:
                pairs.append((current_section, body_content))
            current_section = trimmed
            accumulated_lines = []
        else:
            accumulated_lines.append(line)

    final_body = "\n".join(accumulated_lines).strip()
    if final_body or not pairs:
        pairs.append((current_section, final_body))

    return pairs


def _cut(para: str, limit: int) -> list[str]:
    """Split a paragraph exceeding limit characters.

    Prefers splitting at the last sentence boundary before limit.
    Falls back to the last available space.
    If no space exists, splits at the exact limit boundary.
    Never splits in the middle of a word when a space is available.
    """
    para = para.strip()
    if not para:
        return []
    if len(para) <= limit:
        return [para]

    pieces: list[str] = []
    remaining = para

    while len(remaining) > limit:
        window = remaining[:limit]

        # 1. Look for sentence boundary inside window: . ! ? followed by space or end
        sentence_matches = list(re.finditer(r"[.!?](?=\s|$)", window))
        split_pos = -1
        if sentence_matches:
            split_pos = sentence_matches[-1].end()

        # 2. If no sentence boundary found, find last available space
        if split_pos <= 0:
            space_pos = window.rfind(" ")
            if space_pos > 0:
                split_pos = space_pos

        # 3. If no space found (continuous unbroken string), hard cut at limit
        if split_pos <= 0:
            split_pos = limit

        piece = remaining[:split_pos].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[split_pos:].strip()

    if remaining:
        pieces.append(remaining)

    return pieces


def _get_word_bounded_tail(text: str, overlap: int) -> str:
    """Extract up to overlap characters from the end of text, ensuring it starts on a whole word."""
    if not text or overlap <= 0:
        return ""
    if len(text) <= overlap:
        return text

    raw_tail = text[-overlap:]
    # Find first space in tail so overlap does not start mid-word
    first_space = raw_tail.find(" ")
    if first_space != -1 and first_space < len(raw_tail) - 1:
        return raw_tail[first_space + 1 :].strip()
    return raw_tail.strip()


def pack(
    body: str,
    max_chars: int = MAX_CHARS,
    overlap: int = OVERLAP,
) -> list[str]:
    """Pack body text into chunks up to max_chars with word-bounded overlap."""
    if not body or not body.strip():
        return []

    normalized = body.replace("\r\n", "\n").replace("\r", "\n").strip()

    # Split into paragraphs by double newline
    raw_paras = [p.strip() for p in normalized.split("\n\n") if p.strip()]
    if not raw_paras:
        raw_paras = [normalized]

    paras: list[str] = []
    for p in raw_paras:
        if len(p) > max_chars:
            paras.extend(_cut(p, max_chars))
        else:
            paras.append(p)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for p in paras:
        added_len = len(p) if current_len == 0 else current_len + 2 + len(p)

        if added_len <= max_chars:
            current_parts.append(p)
            current_len = sum(len(x) for x in current_parts) + 2 * (len(current_parts) - 1)
        else:
            if current_parts:
                chunk_text = "\n\n".join(current_parts).strip()
                chunks.append(chunk_text)

                # Build overlap from the end of the previous chunk
                tail = _get_word_bounded_tail(chunk_text, overlap)
                current_parts = []
                current_len = 0
                if tail:
                    # If tail + p fits in max_chars, use it
                    if len(tail) + 2 + len(p) <= max_chars:
                        current_parts.append(tail)
                        current_len = len(tail)
                    else:
                        # Trim tail to remaining space
                        available = max_chars - 2 - len(p)
                        if available > 0:
                            trimmed_tail = _get_word_bounded_tail(tail, available)
                            if trimmed_tail:
                                current_parts.append(trimmed_tail)
                                current_len = len(trimmed_tail)

            current_parts.append(p)
            current_len = sum(len(x) for x in current_parts) + 2 * (len(current_parts) - 1)

    if current_parts:
        chunk_text = "\n\n".join(current_parts).strip()
        if not (chunks and chunk_text == chunks[-1]):
            chunks.append(chunk_text)

    return [c for c in chunks if c.strip()]


def table_texts(table: Any, max_chars: int = MAX_CHARS) -> list[str]:
    """Convert a table into row-formatted chunks, repeating the header in subsequent chunks if split."""
    if not table:
        return []

    # Support string-form tables
    if isinstance(table, str):
        table_str = table.strip()
        if not table_str:
            return []
        lines = [
            line.strip() for line in table_str.splitlines() if line.strip() and not line.startswith("Table ")
        ]
        if not lines:
            return []
        rows = [[c.strip() for c in line.split("|")] for line in lines]
    elif isinstance(table, list):
        rows = table
    else:
        return []

    if not rows:
        return []

    # Format rows as " | " separated strings
    formatted_rows: list[str] = []
    for r in rows:
        if isinstance(r, list):
            row_str = " | ".join(str(c).strip() for c in r)
        else:
            row_str = str(r).strip()
        if row_str:
            formatted_rows.append(row_str)

    if not formatted_rows:
        return []

    header = formatted_rows[0]
    data_rows = formatted_rows[1:]

    if not data_rows:
        return [header] if len(header) <= max_chars else _cut(header, max_chars)

    chunks: list[str] = []
    current_chunk_rows = [header]
    current_len = len(header)

    for row in data_rows:
        added_len = current_len + 1 + len(row)
        if added_len <= max_chars:
            current_chunk_rows.append(row)
            current_len = added_len
        else:
            if len(current_chunk_rows) > 1:
                chunks.append("\n".join(current_chunk_rows))
                # Repeat header in subsequent chunk
                current_chunk_rows = [header]
                current_len = len(header)

            if current_len + 1 + len(row) > max_chars:
                for sub_row in _cut(row, max_chars - len(header) - 1):
                    chunks.append(f"{header}\n{sub_row}")
                current_chunk_rows = [header]
                current_len = len(header)
            else:
                current_chunk_rows.append(row)
                current_len = current_len + 1 + len(row)

    if len(current_chunk_rows) > 1 or (len(current_chunk_rows) == 1 and not chunks):
        chunks.append("\n".join(current_chunk_rows))

    return [c for c in chunks if c.strip()]


def chunk_pages(
    pages: list[dict[str, Any]],
    max_chars: int = MAX_CHARS,
    overlap: int = OVERLAP,
) -> list[Chunk]:
    """Convert parsed page records into normalized Chunk objects.

    - Sorts pages by doc_id and page.
    - Resets section context when a new document starts.
    - Preserves section continuation across pages of the same document.
    - Skips 'needs_ocr' and 'empty' pages.
    - Strips duplicated table text from page body.
    - Splits text by headings.
    - Packs text into chunks and separates tables into table chunks.
    - Assigns chunk_index starting from zero per page.
    - Discards chunks shorter than MIN_CHARS.
    """
    sorted_pages = sorted(pages, key=lambda p: (str(p.get("doc_id", "")), int(p.get("page", 1))))

    all_chunks: list[Chunk] = []
    current_doc_id: str | None = None
    current_section = ""

    for page_rec in sorted_pages:
        doc_id = str(page_rec.get("doc_id", ""))
        source_file = str(page_rec.get("source_file", ""))
        page_num = int(page_rec.get("page", 1))
        method = str(page_rec.get("method", "text"))

        # Skip pages with needs_ocr or empty
        if method in {"needs_ocr", "empty"}:
            continue

        # Reset section context when a new document starts
        if doc_id != current_doc_id:
            current_doc_id = doc_id
            current_section = ""

        page_chunk_index = 0

        raw_text = page_rec.get("text", "")
        tables = page_rec.get("tables", [])
        clean_body = strip_table_text(raw_text, tables)

        headings = page_rec.get("headings", [])
        section_pairs = split_by_heading(clean_body, headings, current_section)

        for sec, sec_text in section_pairs:
            if sec:
                current_section = sec

            if not sec_text.strip():
                continue

            text_chunks = pack(sec_text, max_chars=max_chars, overlap=overlap)
            for tc in text_chunks:
                if len(tc) >= MIN_CHARS:
                    all_chunks.append(
                        Chunk(
                            doc_id=doc_id,
                            source_file=source_file,
                            page=page_num,
                            section=current_section,
                            chunk_index=page_chunk_index,
                            kind="text",
                            text=tc,
                            content_hash=content_hash(tc),
                        )
                    )
                    page_chunk_index += 1

        # Tables become separate chunks
        for tbl in tables:
            tbl_chunk_texts = table_texts(tbl, max_chars=max_chars)
            for tt in tbl_chunk_texts:
                if len(tt) >= MIN_CHARS:
                    all_chunks.append(
                        Chunk(
                            doc_id=doc_id,
                            source_file=source_file,
                            page=page_num,
                            section=current_section,
                            chunk_index=page_chunk_index,
                            kind="table",
                            text=tt,
                            content_hash=content_hash(tt),
                        )
                    )
                    page_chunk_index += 1

    return all_chunks
