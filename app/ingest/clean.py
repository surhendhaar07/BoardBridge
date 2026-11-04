"""Text cleaning and normalization rules for document ingestion."""

from __future__ import annotations

import math
import re
import unicodedata

# Invisible characters to remove
# Soft hyphen (U+00AD), Zero-width space (U+200B), BOM (U+FEFF)
# Note: Zero-width joiner (U+200D) and Zero-width non-joiner (U+200C) are preserved for Indic languages
INVISIBLE_CHARS_TO_REMOVE = {"\u00ad", "\u200b", "\ufeff"}

# Regex for lowercase broken hyphenated words across lines: e.g. "regu-\nlation" -> "regulation"
BROKEN_WORD_REGEX = re.compile(r"([a-z]+)-\n([a-z]+)")

# Regex patterns for standalone page numbers
PAGE_NUMBER_PATTERNS = [
    re.compile(r"^\s*\d+\s*$"),  # e.g. "7"
    re.compile(r"^\s*-\s*\d+\s*-\s*$"),  # e.g. "- 7 -"
    re.compile(r"^\s*page\s+\d+(?:\s+(?:of|/)\s+\d+)?\s*$", re.IGNORECASE),  # e.g. "Page 7 of 40"
    re.compile(r"^\s*\[\s*\d+\s*\]\s*$"),  # e.g. "[ 7 ]"
    re.compile(r"^\s*\d+\s+(?:of|/)\s+\d+\s*$", re.IGNORECASE),  # e.g. "7 of 40"
]


def shape(line: str) -> str:
    """Normalize line for header/footer comparison by replacing digit sequences with '#' and stripping."""
    s = line.strip()
    return re.sub(r"\d+", "#", s)


def repeated_lines(pages: list[str], share: float = 0.5) -> set[str]:
    """Identify lines appearing in first 2 or last 2 lines of at least `share` of pages.

    Only applies when document has at least 3 pages.
    Ignores changing page numbers by utilizing `shape()`.
    Returns a set containing both exact lines and shaped patterns to remove.
    """
    if len(pages) < 3:
        return set()

    threshold = math.ceil(len(pages) * share)
    shape_counts: dict[str, int] = {}
    shape_to_raw: dict[str, set[str]] = {}

    for page_text in pages:
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        if not lines:
            continue

        candidate_lines: set[str] = set()
        # First two lines
        for line in lines[:2]:
            candidate_lines.add(line)
        # Last two lines
        for line in lines[-2:]:
            candidate_lines.add(line)

        # Record unique shapes observed on this page
        seen_shapes_on_page: set[str] = set()
        for line in candidate_lines:
            s_shape = shape(line)
            if s_shape:
                seen_shapes_on_page.add(s_shape)
                shape_to_raw.setdefault(s_shape, set()).add(line)

        for s_shape in seen_shapes_on_page:
            shape_counts[s_shape] = shape_counts.get(s_shape, 0) + 1

    unwanted: set[str] = set()
    for s_shape, count in shape_counts.items():
        if count >= threshold:
            unwanted.add(s_shape)
            unwanted.update(shape_to_raw.get(s_shape, set()))

    return unwanted


def drop_lines(text: str, unwanted: set[str]) -> str:
    """Drop lines whose text or shape matches unwanted headers or footers."""
    if not unwanted:
        return text

    kept_lines: list[str] = []
    for line in text.splitlines():
        trimmed = line.strip()
        if trimmed in unwanted or shape(line) in unwanted:
            continue
        kept_lines.append(line)

    return "\n".join(kept_lines)


def is_standalone_page_number(line: str) -> bool:
    """Check if a line is a standalone page number."""
    return any(pattern.match(line) for pattern in PAGE_NUMBER_PATTERNS)


def clean_text(text: str, page_numbers: bool = True) -> str:
    """Clean and normalize extracted prose text.

    Applies in order:
    1. Newline normalization
    2. Rule 1: Unicode NFKC normalization
    3. Rule 2: Remove invisible characters (soft hyphens, zero-width space, BOM); preserve Indic joiners
    4. Rule 3: Join broken words across lines (lowercase hyphen-newline-lowercase)
    5. Rule 4: Remove standalone page numbers (if page_numbers=True)
    6. Rule 6: Collapse whitespace and preserve paragraph boundaries

    Note: Do not apply to source code or configuration files.
    """
    if not text:
        return ""

    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Rule 1: Unicode NFKC normalization
    text = unicodedata.normalize("NFKC", text)

    # Rule 2: Remove invisible characters (preserve \u200d and \u200c)
    for char in INVISIBLE_CHARS_TO_REMOVE:
        text = text.replace(char, "")

    # Rule 3: Join broken words (lowercase-hyphen-newline-lowercase)
    text = BROKEN_WORD_REGEX.sub(r"\1\2", text)

    # Process line-by-line for page numbers and horizontal whitespace
    cleaned_lines: list[str] = []
    lines = text.splitlines()
    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        prev_line = lines[idx - 1].strip() if idx > 0 else ""

        # Standalone page number check: do not drop if previous line ended with a word-hyphen (e.g. COVID-)
        is_after_word_hyphen = bool(re.search(r"[a-zA-Z]-$", prev_line))
        if page_numbers and is_standalone_page_number(line) and not is_after_word_hyphen:
            continue

        # Rule 6: Collapse consecutive horizontal spaces and trim line
        collapsed = re.sub(r"[ \t]+", " ", raw_line).strip()
        cleaned_lines.append(collapsed)

    text = "\n".join(cleaned_lines)

    # Rule 6: Collapse excessive blank lines (more than 2 consecutive newlines) to 2 newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
