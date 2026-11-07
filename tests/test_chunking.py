"""Unit and integration tests for document chunking and chunk preview."""

from __future__ import annotations

import json
from pathlib import Path

from app.rag.chunking import (
    MAX_CHARS,
    OVERLAP,
    _cut,
    _get_word_bounded_tail,
    chunk_pages,
    content_hash,
    normalise,
    pack,
    split_by_heading,
    strip_table_text,
    table_texts,
)
from tools.preview_chunks import load_parsed_pages, preview


# 1. Text normalization
def test_text_normalization():
    dirty = "   Zephyr   RTOS  \n\t  driver \r\n configuration   "
    assert normalise(dirty) == "Zephyr RTOS driver configuration"
    assert normalise("") == ""


# 2. SHA-256 content hash
def test_sha256_content_hash():
    h = content_hash("Zephyr RTOS GPIO driver")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# 3. Identical normalized text produces identical hashes
def test_identical_normalized_text_produces_identical_hashes():
    h1 = content_hash("GPIO pin\nconfiguration")
    h2 = content_hash("GPIO pin configuration")
    h3 = content_hash("  GPIO   pin   \t  configuration  ")
    assert h1 == h2 == h3


# 4. Heading-based splitting
def test_heading_based_splitting():
    text = (
        "General introduction to drivers.\n\n"
        "GPIO Configuration\n"
        "Configure pins as inputs or outputs using the devicetree.\n\n"
        "SPI Driver API\n"
        "Transmit SPI frames synchronously."
    )
    headings = ["GPIO Configuration", "SPI Driver API"]
    pairs = split_by_heading(text, headings, section="Intro")

    assert len(pairs) == 3
    assert pairs[0][0] == "Intro"
    assert "General introduction" in pairs[0][1]

    assert pairs[1][0] == "GPIO Configuration"
    assert "Configure pins" in pairs[1][1]

    assert pairs[2][0] == "SPI Driver API"
    assert "Transmit SPI frames" in pairs[2][1]


# 5. Section continuation across pages
def test_section_continuation_across_pages():
    pages = [
        {
            "doc_id": "zephyr_doc",
            "source_file": "doc.rst",
            "page": 1,
            "headings": ["Sensor Subsystem"],
            "text": "Sensor Subsystem\nPage 1 overview of sensors.",
            "tables": [],
            "method": "text",
        },
        {
            "doc_id": "zephyr_doc",
            "source_file": "doc.rst",
            "page": 2,
            "headings": [],  # No new heading on page 2
            "text": "Page 2 continuing description of sensor channels.",
            "tables": [],
            "method": "text",
        },
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) >= 2
    assert chunks[0].section == "Sensor Subsystem"
    # Page 2 must inherit page 1's section
    assert chunks[1].section == "Sensor Subsystem"


# 6. Section reset between documents
def test_section_reset_between_documents():
    pages = [
        {
            "doc_id": "doc_1",
            "source_file": "doc1.c",
            "page": 1,
            "headings": ["SPI Driver API"],
            "text": "SPI Driver API\nSPI configuration code for bus initialization and transfer.",
            "tables": [],
            "method": "code",
        },
        {
            "doc_id": "doc_2",
            "source_file": "doc2.c",
            "page": 1,
            "headings": [],  # No headings in doc 2
            "text": "Blinky sample application main routine without heading.",
            "tables": [],
            "method": "code",
        },
    ]
    chunks = chunk_pages(pages)
    doc1_chunks = [c for c in chunks if c.doc_id == "doc_1"]
    doc2_chunks = [c for c in chunks if c.doc_id == "doc_2"]

    assert doc1_chunks[0].section == "SPI Driver API"
    # Doc 2 must NOT inherit Doc 1's section
    assert doc2_chunks[0].section == ""


# 7. Footer removal
def test_footer_removal():
    text = "Page 3\nActual driver setup content.\nPage 3 of 40\n- 3 -\n3\nMore driver implementation details."
    pairs = split_by_heading(text, [], section="")
    body = pairs[0][1]

    assert "Page 3 of 40" not in body
    assert "- 3 -" not in body
    assert "Actual driver setup content." in body
    assert "More driver implementation details." in body


# 8. Long paragraph splitting
def test_long_paragraph_splitting():
    sentence_1 = "This is the first sentence about Zephyr RTOS drivers. "
    sentence_2 = "This second sentence discusses devicetree overlays and pin control. "
    sentence_3 = "The third sentence covers Kconfig configuration options in depth."
    long_para = sentence_1 + sentence_2 + sentence_3

    # Limit smaller than total length, cut prefers sentence boundaries
    pieces = _cut(long_para, limit=80)
    assert len(pieces) >= 2
    for p in pieces:
        assert len(p) <= 80

    # Test unbreakable string without spaces
    unbreakable = "A" * 150
    cut_unbreakable = _cut(unbreakable, limit=50)
    assert len(cut_unbreakable) == 3
    assert all(len(p) <= 50 for p in cut_unbreakable)


# 9. Maximum chunk length
def test_maximum_chunk_length():
    large_text = "Zephyr RTOS firmware driver paragraph. " * 50
    chunks = pack(large_text, max_chars=MAX_CHARS, overlap=OVERLAP)

    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= MAX_CHARS


# 10. Overlap between consecutive chunks
def test_overlap_between_consecutive_chunks():
    p1 = "Zephyr GPIO drivers support pin configuration and interrupt handling."
    p2 = "The application can configure GPIO pins as inputs or outputs with pull-up resistors."
    p3 = "Interrupts can be triggered on rising edges, falling edges, or both."
    combined = f"{p1}\n\n{p2}\n\n{p3}"

    chunks = pack(combined, max_chars=120, overlap=35)
    assert len(chunks) >= 2

    # Chunk 2 should contain tail content from Chunk 1
    overlap_tail = _get_word_bounded_tail(chunks[0], 35)
    assert overlap_tail in chunks[1]


# 11. Overlap starts on a whole word
def test_overlap_starts_on_a_whole_word():
    text = "The quick brown fox jumps over the lazy dog."
    tail = _get_word_bounded_tail(text, overlap=18)
    # 18 chars back would be "r the lazy dog." -> word bounded should start with "the"
    assert not tail.startswith("r ")
    assert tail.split()[0] in {"the", "lazy", "dog."}


# 12. Minimum chunk length filtering
def test_minimum_chunk_length_filtering():
    short_page = [
        {
            "doc_id": "short_doc",
            "source_file": "short.txt",
            "page": 1,
            "headings": [],
            "text": "Tiny.",  # Less than MIN_CHARS (25)
            "tables": [],
            "method": "text",
        }
    ]
    chunks = chunk_pages(short_page)
    assert len(chunks) == 0


# 13. Table extraction
def test_table_extraction():
    table = [
        ["Register", "Address", "Default"],
        ["CHIP_ID", "0xD0", "0x60"],
        ["RESET", "0xE0", "0x00"],
    ]
    chunks = table_texts(table, max_chars=1000)

    assert len(chunks) == 1
    assert "Register | Address | Default" in chunks[0]
    assert "CHIP_ID | 0xD0 | 0x60" in chunks[0]


# 14. Table header repetition
def test_table_header_repetition():
    table = [["HeaderA", "HeaderB"]] + [[f"Row_{i}", f"Val_{i}"] for i in range(20)]
    # Use a small max_chars to force table splitting
    chunks = table_texts(table, max_chars=100)

    assert len(chunks) >= 2
    for c in chunks:
        # Every split chunk must repeat the header
        assert c.startswith("HeaderA | HeaderB")


# 15. Table text is not duplicated
def test_table_text_is_not_duplicated():
    raw_text = (
        "Prose content discussing the register map.\n\n"
        "Table 1:\n"
        "Register | Address\n"
        "CHIP_ID | 0xD0\n"
        "RESET | 0xE0"
    )
    tables = [[["Register", "Address"], ["CHIP_ID", "0xD0"], ["RESET", "0xE0"]]]

    stripped = strip_table_text(raw_text, tables)
    assert "Prose content discussing the register map." in stripped
    assert "Table 1:" not in stripped
    assert "CHIP_ID | 0xD0" not in stripped

    pages = [
        {
            "doc_id": "sensor_reg",
            "source_file": "sensor.c",
            "page": 1,
            "headings": [],
            "text": raw_text,
            "tables": tables,
            "method": "code",
        }
    ]
    chunks = chunk_pages(pages)
    text_chunks = [c for c in chunks if c.kind == "text"]
    table_chunks = [c for c in chunks if c.kind == "table"]

    assert len(text_chunks) == 1
    assert "CHIP_ID | 0xD0" not in text_chunks[0].text
    assert len(table_chunks) == 1
    assert "CHIP_ID | 0xD0" in table_chunks[0].text


# 16. Metadata preservation
def test_metadata_preservation():
    page = {
        "doc_id": "bme280_driver",
        "source_file": "drivers/sensor/bme280.c",
        "page": 2,
        "headings": ["bme280_sample_fetch"],
        "text": "bme280_sample_fetch\nint bme280_sample_fetch(const struct device *dev) { return 0; }",
        "tables": [],
        "method": "code",
    }
    chunks = chunk_pages([page])
    assert len(chunks) == 1
    c = chunks[0]

    assert c.doc_id == "bme280_driver"
    assert c.source_file == "drivers/sensor/bme280.c"
    assert c.page == 2
    assert c.section == "bme280_sample_fetch"
    assert c.chunk_index == 0
    assert c.kind == "text"
    assert len(c.content_hash) == 64


# 17. Chunk index starts from zero per page
def test_chunk_index_starts_from_zero_per_page():
    long_p1 = "Paragraph on page one. " * 30
    long_p2 = "Paragraph on page two. " * 30

    pages = [
        {
            "doc_id": "multi_chunk",
            "source_file": "test.txt",
            "page": 1,
            "headings": [],
            "text": long_p1,
            "tables": [],
            "method": "text",
        },
        {
            "doc_id": "multi_chunk",
            "source_file": "test.txt",
            "page": 2,
            "headings": [],
            "text": long_p2,
            "tables": [],
            "method": "text",
        },
    ]
    chunks = chunk_pages(pages, max_chars=400, overlap=50)

    p1_chunks = [c for c in chunks if c.page == 1]
    p2_chunks = [c for c in chunks if c.page == 2]

    assert len(p1_chunks) >= 2
    assert [c.chunk_index for c in p1_chunks] == list(range(len(p1_chunks)))

    assert len(p2_chunks) >= 2
    # Page 2 chunk index must restart at 0
    assert p2_chunks[0].chunk_index == 0
    assert [c.chunk_index for c in p2_chunks] == list(range(len(p2_chunks)))


# 18. needs_ocr pages are skipped
def test_needs_ocr_pages_are_skipped():
    pages = [
        {
            "doc_id": "scanned_doc",
            "source_file": "scanned.pdf",
            "page": 1,
            "headings": [],
            "text": "",
            "tables": [],
            "method": "needs_ocr",
        }
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) == 0


# 19. Empty pages are skipped
def test_empty_pages_are_skipped():
    pages = [
        {
            "doc_id": "empty_doc",
            "source_file": "empty.pdf",
            "page": 1,
            "headings": [],
            "text": "   ",
            "tables": [],
            "method": "empty",
        }
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) == 0


# 20. Source-code text and indentation are not unnecessarily modified
def test_source_code_indentation_preserved():
    c_code = (
        "static int bme280_init(const struct device *dev)\n"
        "{\n"
        "    struct bme280_data *data = dev->data;\n"
        "    if (!data) {\n"
        "        return -EINVAL;\n"
        "    }\n"
        "    return 0;\n"
        "}"
    )
    pages = [
        {
            "doc_id": "sensor_c",
            "source_file": "sensor.c",
            "page": 1,
            "headings": [],
            "text": c_code,
            "tables": [],
            "method": "code",
        }
    ]
    chunks = chunk_pages(pages)
    assert len(chunks) == 1
    # 4 and 8 space indentation must be intact
    assert "    struct bme280_data *data = dev->data;" in chunks[0].text
    assert "        return -EINVAL;" in chunks[0].text


# 21. Multiple documents do not share headings
def test_multiple_documents_do_not_share_headings():
    pages = [
        {
            "doc_id": "doc_alpha",
            "source_file": "alpha.c",
            "page": 1,
            "headings": ["Alpha Heading"],
            "text": "Alpha Heading\nAlpha document content.",
            "tables": [],
            "method": "code",
        },
        {
            "doc_id": "doc_beta",
            "source_file": "beta.c",
            "page": 1,
            "headings": [],
            "text": "Beta document content with no headings.",
            "tables": [],
            "method": "code",
        },
    ]
    chunks = chunk_pages(pages)
    beta_chunk = next(c for c in chunks if c.doc_id == "doc_beta")
    assert beta_chunk.section != "Alpha Heading"
    assert beta_chunk.section == ""


# 22. Preview loader ignores sample_pages.json
def test_preview_loader_ignores_sample_pages_json(tmp_path: Path):
    folder = tmp_path / "parsed"
    folder.mkdir()

    # Valid JSONL file
    jsonl_file = folder / "pages.jsonl"
    rec = {
        "doc_id": "valid_doc",
        "source_file": "test.c",
        "page": 1,
        "headings": ["Valid Heading"],
        "text": "Valid Heading\nValid content exceeding min chars easily.",
        "tables": [],
        "method": "code",
    }
    jsonl_file.write_text(json.dumps(rec) + "\n", encoding="utf-8")

    # Sample JSON file that must be IGNORED
    sample_json = folder / "sample_pages.json"
    sample_json.write_text(json.dumps([{"doc_id": "ignored_doc"}]), encoding="utf-8")

    usable, total, skipped = load_parsed_pages(folder)
    assert len(usable) == 1
    assert usable[0]["doc_id"] == "valid_doc"

    # Preview function must execute without errors
    chunks = preview(folder=folder, n=1, seed=42)
    assert len(chunks) == 1
    assert chunks[0].doc_id == "valid_doc"
