"""Comprehensive unit and integration tests for document ingestion and parsing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock

from app.ingest.clean import clean_text
from app.ingest.parse import (
    generate_doc_id,
    parse_code,
    parse_html,
    parse_pdf,
    parse_text,
    run_parsing,
)
from tests.sample_docs import generate_test_html, generate_test_pdf


# 1. One record per PDF page
def test_pdf_one_record_per_page(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)
    assert len(records) == 3


# 2. Page numbering starts at 1
def test_pdf_page_numbering_starts_at_one(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)
    assert [r["page"] for r in records] == [1, 2, 3]


# 3. Correct doc_id
def test_correct_doc_id():
    # Simple top-level file
    assert generate_doc_id(Path("data/raw/example.pdf")) == "example"

    # Nested path inside root avoids collisions
    root = Path("data/raw")
    nested_1 = Path("data/raw/samples/sensor/bme280/CMakeLists.txt")
    nested_2 = Path("data/raw/drivers/sensor/bosch/bme280/CMakeLists.txt")

    id_1 = generate_doc_id(nested_1, root=root)
    id_2 = generate_doc_id(nested_2, root=root)

    assert id_1 == "samples-sensor-bme280-cmakelists-txt"
    assert id_2 == "drivers-sensor-bosch-bme280-cmakelists-txt"
    assert id_1 != id_2


# 4. Correct source_file
def test_correct_source_file(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)
    expected_source = str(pdf_path).replace("\\", "/")
    for r in records:
        assert r["source_file"] == expected_source


# 5. Headings detected by font size
def test_headings_detected_by_font_size(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)
    page_1_headings = records[0]["headings"]
    assert any("System Architecture Guide" in h for h in page_1_headings)


# 6. Headings inherited when a page has no new heading
def test_headings_inherited_when_no_new_heading(tmp_path: Path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pdf_p = tmp_path / "no_heading.pdf"
    c = canvas.Canvas(str(pdf_p), pagesize=letter)

    # Page 1 has a large heading
    c.setFont("Helvetica-Bold", 18)
    c.drawString(100, 700, "Initial Section Title")
    c.setFont("Helvetica", 10)
    c.drawString(100, 650, "Some normal body text on page 1.")
    c.showPage()

    # Page 2 has only body text, no headings
    c.setFont("Helvetica", 10)
    c.drawString(100, 700, "Continuing text on page 2 without any headings.")
    c.showPage()
    c.save()

    records = parse_pdf(pdf_p)
    assert len(records) == 2
    assert "Initial Section Title" in records[0]["headings"]
    # Page 2 must inherit page 1's heading
    assert records[1]["headings"] == records[0]["headings"]


# 7. Repeated headers removed
def test_repeated_headers_removed(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)

    for r in records:
        text = r["text"]
        assert "BoardBridge System Documentation" not in text
        assert "Confidential - Internal Use Only" not in text


# 8. Page numbers removed from normal text
def test_page_numbers_removed_from_normal_text():
    sample = "Page 7 of 40\nActual paragraph content.\n- 7 -\n7\n[ 7 ]\nAnother paragraph."
    cleaned = clean_text(sample, page_numbers=True)
    assert "Page 7 of 40" not in cleaned
    assert "- 7 -" not in cleaned
    assert "\n7\n" not in cleaned
    assert "Actual paragraph content." in cleaned
    assert "Another paragraph." in cleaned


# 9. Broken words joined correctly
def test_broken_words_joined_correctly():
    # Lowercase hyphen-newline-lowercase should join
    sample = "regu-\nlation"
    assert clean_text(sample) == "regulation"

    # Unrelated patterns like COVID-\n19 or Capitalized should NOT join
    unrelated = "COVID-\n19"
    assert clean_text(unrelated) == "COVID-\n19"


# 10. Unicode normalization
def test_unicode_normalization():
    # NFKC normalizes ligatures like fi -> f + i
    ligature_text = "ﬁle and ﬂow"
    assert clean_text(ligature_text) == "file and flow"


# 11. Indic joiners preserved
def test_indic_joiners_preserved():
    # Zero-width joiner \u200d and non-joiner \u200c must be preserved
    indic_sample = "Tamil: க்\u200dஷ and \u200c"
    cleaned = clean_text(indic_sample)
    assert "\u200d" in cleaned
    assert "\u200c" in cleaned

    # Invisible soft hyphen \u00ad, zero-width space \u200b, BOM \ufeff must be removed
    dirty = "word\u00adwith\u200bhidden\ufeffchars"
    cleaned_dirty = clean_text(dirty)
    assert "\u00ad" not in cleaned_dirty
    assert "\u200b" not in cleaned_dirty
    assert "\ufeff" not in cleaned_dirty
    assert cleaned_dirty == "wordwithhiddenchars"


# 12. Tables extracted as rows and cells
def test_tables_extracted_as_rows_and_cells(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)

    p2 = records[1]
    assert len(p2["tables"]) >= 1
    table = p2["tables"][0]
    assert len(table) >= 2
    assert table[0] == ["Service", "Fee (Rs)"]


# 13. Numeric table values retained
def test_numeric_table_values_retained(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)

    p2 = records[1]
    flat_cells = [cell for row in p2["tables"][0] for cell in row]
    assert "150" in flat_cells
    assert "100" in flat_cells


# 14. Table text added only once
def test_table_text_added_only_once(tmp_path: Path):
    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)

    p2_text = records[1]["text"]
    assert p2_text.count("Cheque book | 150") == 1
    assert p2_text.count("Duplicate statement | 100") == 1


# 15. Scanned page OCR when Tesseract is available
def test_scanned_page_ocr_when_tesseract_available(tmp_path: Path, monkeypatch):
    import app.ingest.parse as parse_mod

    # Mock OCR availability and pytesseract
    monkeypatch.setattr(parse_mod, "is_tesseract_available", lambda cmd=None: True)

    mock_pytesseract = MagicMock()
    mock_pytesseract.image_to_string.return_value = (
        "Scanned Invoice Text\n2.1 Fees and Operations\nDetails of fees."
    )
    monkeypatch.setattr("pytesseract.image_to_string", mock_pytesseract.image_to_string)

    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path, tesseract_cmd="dummy_tesseract")

    page_3 = records[2]
    assert page_3["method"] == "ocr"
    assert "2.1 Fees and Operations" in page_3["headings"]
    assert "Scanned Invoice Text" in page_3["text"]


# 16. Scanned page marked needs_ocr when Tesseract is unavailable
def test_scanned_page_marked_needs_ocr_when_tesseract_unavailable(tmp_path: Path, monkeypatch):
    import app.ingest.parse as parse_mod

    # Force Tesseract unavailable
    monkeypatch.setattr(parse_mod, "is_tesseract_available", lambda cmd=None: False)

    pdf_path = generate_test_pdf(tmp_path / "sample.pdf")
    records = parse_pdf(pdf_path)

    page_3 = records[2]
    assert page_3["method"] == "needs_ocr"
    assert page_3["text"] == ""


# 17. HTML navigation and scripts removed
def test_html_navigation_and_scripts_removed(tmp_path: Path):
    html_p = generate_test_html(tmp_path / "sample.html")
    records = parse_html(html_p)
    assert len(records) == 1

    text = records[0]["text"]
    assert "maliciousTracker" not in text
    assert "bad_code" not in text
    assert "Top Notification Banner" not in text
    assert "Related Links" not in text
    assert "All rights reserved" not in text


# 18. HTML headings and tables extracted
def test_html_headings_and_tables_extracted(tmp_path: Path):
    html_p = generate_test_html(tmp_path / "sample.html")
    records = parse_html(html_p)

    rec = records[0]
    assert rec["method"] == "html"
    assert rec["headings"] == [
        "Zephyr RTOS Sensor Architecture",
        "BME280 Driver Implementation",
        "I2C Bus Configuration",
    ]
    assert len(rec["tables"]) == 1
    assert rec["tables"][0][1] == ["CHIP_ID", "0xD0", "0x60"]
    assert "CHIP_ID | 0xD0 | 0x60" in rec["text"]
    assert "வணக்கம் Zephyr RTOS" in rec["text"]


# 19. Source-code indentation preserved
def test_source_code_indentation_preserved(tmp_path: Path):
    code_file = tmp_path / "sensor_driver.c"
    c_source = """#include <zephyr/drivers/sensor.h>

static int bme280_sample_fetch(const struct device *dev)
{
    struct bme280_data *data = dev->data;
    if (!data) {
        return -EINVAL;
    }
    return 0;
}
"""
    code_file.write_text(c_source, encoding="utf-8")
    records = parse_code(code_file)

    assert len(records) == 1
    rec = records[0]
    assert rec["method"] == "code"
    # Indentation of 4 and 8 spaces must remain intact
    assert "    struct bme280_data *data = dev->data;" in rec["text"]
    assert "        return -EINVAL;" in rec["text"]
    assert any("bme280_sample_fetch" in h for h in rec["headings"])


# 20. Markdown headings extracted
def test_markdown_headings_extracted(tmp_path: Path):
    md_file = tmp_path / "sample.md"
    md_content = """# Sensor Overview

This is general documentation.

## Calibration Procedures
Step 1: Read calibration coefficients.

### Compensation Formula
Formula for temperature compensation.
"""
    md_file.write_text(md_content, encoding="utf-8")
    records = parse_text(md_file)

    assert len(records) == 1
    rec = records[0]
    assert rec["method"] == "text"
    assert rec["headings"] == [
        "Sensor Overview",
        "Calibration Procedures",
        "Compensation Formula",
    ]


# 21. CLI writes JSONL and sample JSON
def test_cli_writes_jsonl_and_sample_json(tmp_path: Path):
    in_dir = tmp_path / "input"
    in_dir.mkdir()
    generate_test_pdf(in_dir / "doc1.pdf")
    generate_test_html(in_dir / "doc2.html")

    out_jsonl = tmp_path / "output" / "pages.jsonl"
    sample_json = tmp_path / "output" / "sample_pages.json"

    stats = run_parsing(
        input_path=in_dir,
        output_path=out_jsonl,
        limit=10,
        sample_size=2,
    )

    assert stats["pages"] >= 4
    assert out_jsonl.is_file()
    assert sample_json.is_file()

    # Verify JSONL lines
    lines = out_jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == stats["pages"]

    required_keys = {"doc_id", "source_file", "page", "headings", "text", "tables", "method"}
    for line in lines:
        obj = json.loads(line)
        assert set(obj.keys()) == required_keys

    # Verify sample_pages.json
    samples = json.loads(sample_json.read_text(encoding="utf-8"))
    assert len(samples) == 2
    assert set(samples[0].keys()) == required_keys


# 22. Duplicate document IDs are reported
def test_duplicate_document_ids_are_reported(tmp_path: Path, caplog):
    in_dir = tmp_path / "dup_test"
    in_dir.mkdir()

    # Create two files in different directories that might share a stem if root not passed
    f1 = in_dir / "dir_a" / "kconfig"
    f2 = in_dir / "dir_b" / "kconfig"
    f1.parent.mkdir()
    f2.parent.mkdir()
    f1.write_text("config A\n  bool", encoding="utf-8")
    f2.write_text("config B\n  bool", encoding="utf-8")

    out_jsonl = tmp_path / "dup_out" / "pages.jsonl"

    import app.ingest.parse as parse_mod

    # Temporarily force generate_doc_id to produce duplicate for test verification
    original_gen = parse_mod.generate_doc_id
    try:
        parse_mod.generate_doc_id = lambda p, root=None: "kconfig-dup"
        with caplog.at_level(logging.WARNING, logger="boardbridge.ingest"):
            run_parsing(input_path=in_dir, output_path=out_jsonl)

        assert any("Duplicate doc_id 'kconfig-dup'" in record.message for record in caplog.records)
    finally:
        parse_mod.generate_doc_id = original_gen


# 23. One broken file does not stop the whole run
def test_one_broken_file_does_not_stop_the_whole_run(tmp_path: Path):
    in_dir = tmp_path / "resilient_test"
    in_dir.mkdir()

    # Valid file
    good_file = in_dir / "valid.txt"
    good_file.write_text("Valid text content for resilient test.", encoding="utf-8")

    # Corrupted PDF file
    broken_pdf = in_dir / "corrupted.pdf"
    broken_pdf.write_bytes(b"%PDF-1.4 Corrupted header and invalid trailer")

    out_jsonl = tmp_path / "resilient_out" / "pages.jsonl"
    stats = run_parsing(input_path=in_dir, output_path=out_jsonl)

    assert stats["broken"] >= 1
    assert stats["pages"] >= 1
    assert out_jsonl.is_file()
