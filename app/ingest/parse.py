"""Modular document parser for BoardBridge RAG ingestion.

Supports PDF, HTML, Markdown/Text, and Zephyr RTOS source code/configuration files.
Outputs standardized 7-field records for chunking and embedding.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from app.ingest.clean import clean_text, drop_lines, repeated_lines

logger = logging.getLogger("boardbridge.ingest")

# Supported file extensions/names
CODE_SUFFIXES = {
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".yaml",
    ".yml",
    ".dts",
    ".dtsi",
    ".overlay",
    ".conf",
    ".py",
    ".js",
    ".ts",
    ".java",
}
CODE_FILENAMES = {"kconfig", "cmakelists.txt"}
TEXT_SUFFIXES = {".md", ".rst", ".txt"}
HTML_SUFFIXES = {".html", ".htm"}
PDF_SUFFIXES = {".pdf"}


def get_tesseract_cmd() -> str | None:
    """Detect Tesseract executable from TESSERACT_CMD env, PATH, or standard Windows locations."""
    env_cmd = os.environ.get("TESSERACT_CMD")
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd

    which_cmd = shutil.which("tesseract")
    if which_cmd:
        return which_cmd

    win_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in win_paths:
        if os.path.isfile(p):
            return p

    return None


def is_tesseract_available(tesseract_cmd: str | None = None) -> bool:
    """Check if pytesseract and the Tesseract executable are usable."""
    cmd = tesseract_cmd or get_tesseract_cmd()
    if not cmd:
        return False
    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def generate_doc_id(path: Path, root: Path | None = None) -> str:
    """Generate a clean, lowercase, hyphenated, stable doc_id.

    Avoids collisions by preserving relative directory context when nested inside root.
    """
    path_obj = Path(path)
    if root is not None:
        try:
            rel = path_obj.relative_to(root)
            if rel.parent != Path("."):
                # Use relative path to avoid collisions between identical filenames in different folders
                raw_slug = str(rel)
                return re.sub(r"[^a-z0-9]+", "-", raw_slug.lower()).strip("-")
        except ValueError:
            pass

    slug = re.sub(r"[^a-z0-9]+", "-", path_obj.stem.lower()).strip("-")
    return slug or "document"


def clean_rows(rows: list[list[Any]] | None) -> list[list[str]]:
    """Clean table cells preserving numeric values without dropping cell content."""
    if not rows:
        return []

    cleaned: list[list[str]] = []
    for row in rows:
        cleaned_row: list[str] = []
        for cell in row:
            if cell is None:
                cleaned_row.append("")
            else:
                # Collapse horizontal spaces inside cell, keep numbers intact
                cell_str = re.sub(r"[ \t]+", " ", str(cell)).strip()
                cleaned_row.append(cell_str)
        if any(cleaned_row):
            cleaned.append(cleaned_row)
    return cleaned


def with_tables(text: str, tables: list[list[list[str]]]) -> str:
    """Format tables as cell-separated lines and append once to text."""
    if not tables:
        return text

    table_blocks: list[str] = []
    for idx, table in enumerate(tables, 1):
        lines = [f"Table {idx}:"]
        for row in table:
            lines.append(" | ".join(str(c) for c in row))
        table_blocks.append("\n".join(lines))

    tables_text = "\n\n".join(table_blocks)
    if text.strip():
        return f"{text.strip()}\n\n{tables_text}"
    return tables_text


def outside(page: Any, boxes: list[tuple[float, float, float, float]]) -> str:
    """Extract page text strictly outside the given table bounding boxes."""
    if not boxes:
        return page.extract_text(use_text_flow=True) or ""

    def not_in_table(obj: dict[str, Any]) -> bool:
        ox0 = obj.get("x0", 0.0)
        otop = obj.get("top", 0.0)
        ox1 = obj.get("x1", 0.0)
        obottom = obj.get("bottom", 0.0)
        for bx0, btop, bx1, bbottom in boxes:
            # Overlap test: char falls inside table bbox
            if not (ox1 <= bx0 or ox0 >= bx1 or obottom <= btop or otop >= bbottom):
                return False
        return True

    try:
        filtered = page.filter(not_in_table)
        return filtered.extract_text(use_text_flow=True) or ""
    except Exception:
        return page.extract_text(use_text_flow=True) or ""


def _extract_pdf_headings(
    page: Any,
    body_size: float,
    unwanted: set[str],
) -> list[str]:
    """Extract headings from a PDF page using font size and bold formatting."""
    headings: list[str] = []
    try:
        lines = page.extract_text_lines(return_chars=True)
    except Exception:
        return []

    for line_info in lines:
        text = line_info.get("text", "").strip()
        if not text or len(text) > 120:
            continue
        # Headings should contain alphabetic characters and not end in standard punctuation
        if not any(c.isalpha() for c in text) or text.endswith((".", ",", ";", ":")):
            continue
        if len(text.split()) > 15:
            continue
        if text in unwanted:
            continue

        chars = line_info.get("chars", [])
        if not chars:
            continue

        avg_size = sum(c.get("size", 0.0) for c in chars) / len(chars)
        is_bold = any("bold" in str(c.get("fontname", "")).lower() for c in chars)

        if avg_size >= body_size * 1.15 or (is_bold and avg_size >= body_size * 0.95):
            headings.append(text)

    return headings


def parse_pdf(
    path: Path,
    root: Path | None = None,
    lang: str = "eng",
    tesseract_cmd: str | None = None,
) -> list[dict[str, Any]]:
    """Parse a PDF document page-by-page into 7-field JSON records using pdfplumber."""
    import pdfplumber

    records: list[dict[str, Any]] = []
    doc_id = generate_doc_id(path, root)
    source_file = str(path).replace("\\", "/")

    cmd = tesseract_cmd or get_tesseract_cmd()
    has_ocr = is_tesseract_available(cmd)
    if has_ocr and cmd:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd

    with pdfplumber.open(path) as pdf:
        num_pages = len(pdf.pages)

        # First pass: collect outside text and tables across all pages
        raw_pages_data: list[dict[str, Any]] = []
        all_char_sizes: list[float] = []

        for p_idx, page in enumerate(pdf.pages):
            tables = page.find_tables()
            boxes = [t.bbox for t in tables]
            raw_text = outside(page, boxes)
            clean_tbls = [clean_rows(t.extract()) for t in tables]

            # Collect font sizes for body size detection
            for c in page.chars:
                if c.get("text", "").strip():
                    all_char_sizes.append(round(c.get("size", 10.0), 1))

            raw_pages_data.append(
                {
                    "page_num": p_idx + 1,
                    "raw_text": raw_text,
                    "tables": [t for t in clean_tbls if t],
                    "boxes": boxes,
                    "has_images": bool(page.images),
                    "page_obj": page,
                }
            )

        # Detect body font size across document
        body_size = 10.0
        if all_char_sizes:
            counter = collections.Counter(all_char_sizes)
            body_size = counter.most_common(1)[0][0]

        # Rule 5: Detect repeated headers/footers when doc has >= 3 pages
        unwanted_lines: set[str] = set()
        if num_pages >= 3:
            unwanted_lines = repeated_lines([d["raw_text"] for d in raw_pages_data], share=0.5)

        last_heading: str | None = None

        # Second pass: generate final per-page records
        for pdata in raw_pages_data:
            page_num = pdata["page_num"]
            raw_text = pdata["raw_text"]
            tables = pdata["tables"]
            has_images = pdata["has_images"]
            page = pdata["page_obj"]

            dropped = drop_lines(raw_text, unwanted_lines)

            # Scanned page detection: has image and fewer than 25 extractable characters
            if has_images and len(dropped.strip()) < 25:
                if has_ocr:
                    try:
                        import pytesseract

                        img = page.to_image(resolution=300).original
                        ocr_text = pytesseract.image_to_string(img, lang=lang)
                        ocr_headings = re.findall(
                            r"^\s*(\d+(?:\.\d+)*\s+[A-Za-z][A-Za-z0-9 ]+)\s*$",
                            ocr_text,
                            re.MULTILINE,
                        )
                        cleaned = clean_text(ocr_text, page_numbers=True)
                        headings = [h.strip() for h in ocr_headings]
                        if not headings and last_heading:
                            headings = [last_heading]
                        elif headings:
                            last_heading = headings[-1]

                        records.append(
                            {
                                "doc_id": doc_id,
                                "source_file": source_file,
                                "page": page_num,
                                "headings": headings,
                                "text": cleaned,
                                "tables": [],
                                "method": "ocr",
                            }
                        )
                    except Exception as exc:
                        logger.warning(f"OCR failed for {path} page {page_num}: {exc}")
                        records.append(
                            {
                                "doc_id": doc_id,
                                "source_file": source_file,
                                "page": page_num,
                                "headings": [last_heading] if last_heading else [],
                                "text": "",
                                "tables": [],
                                "method": "needs_ocr",
                            }
                        )
                else:
                    # Tesseract not available: mark needs_ocr, return empty text
                    records.append(
                        {
                            "doc_id": doc_id,
                            "source_file": source_file,
                            "page": page_num,
                            "headings": [last_heading] if last_heading else [],
                            "text": "",
                            "tables": [],
                            "method": "needs_ocr",
                        }
                    )
            else:
                # Normal text-based PDF page
                page_headings = _extract_pdf_headings(page, body_size, unwanted_lines)
                if not page_headings and last_heading:
                    headings = [last_heading]
                else:
                    headings = page_headings
                    if page_headings:
                        last_heading = page_headings[-1]

                dropped = drop_lines(raw_text, unwanted_lines)
                cleaned = clean_text(dropped, page_numbers=True)
                final_text = with_tables(cleaned, tables)

                records.append(
                    {
                        "doc_id": doc_id,
                        "source_file": source_file,
                        "page": page_num,
                        "headings": headings,
                        "text": final_text,
                        "tables": tables,
                        "method": "text",
                    }
                )

            # Flush page cache to minimize memory footprint
            try:
                page.flush_cache()
            except Exception:
                pass

    return records


def parse_html(path: Path, root: Path | None = None) -> list[dict[str, Any]]:
    """Parse HTML file using BeautifulSoup, extracting h1-h3 headings, tables, and cleaned text."""
    from bs4 import BeautifulSoup

    doc_id = generate_doc_id(path, root)
    source_file = str(path).replace("\\", "/")

    raw_bytes = path.read_bytes()
    soup = BeautifulSoup(raw_bytes, "html.parser")

    # Remove unwanted tags
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "aside", "sidebar"]):
        tag.decompose()

    # Prefer main or article as content root
    root_node = soup.find("main") or soup.find("article") or soup.body or soup

    # Extract h1, h2, h3 headings in order
    headings: list[str] = []
    for h in root_node.find_all(["h1", "h2", "h3"]):
        h_text = h.get_text(strip=True)
        if h_text and h_text not in headings:
            headings.append(h_text)

    # Extract tables
    tables_data: list[list[list[str]]] = []
    for table_elem in root_node.find_all("table"):
        rows: list[list[str]] = []
        for tr in table_elem.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells)
        cleaned_tbl = clean_rows(rows)
        if cleaned_tbl:
            tables_data.append(cleaned_tbl)
        # Decompose table element so its text is not duplicated in general body text
        table_elem.decompose()

    # Extract body text with preserved paragraph breaks
    raw_text = root_node.get_text(separator="\n\n", strip=True)
    cleaned_text = clean_text(raw_text, page_numbers=False)
    final_text = with_tables(cleaned_text, tables_data)

    return [
        {
            "doc_id": doc_id,
            "source_file": source_file,
            "page": 1,
            "headings": headings,
            "text": final_text,
            "tables": tables_data,
            "method": "html",
        }
    ]


def parse_text(path: Path, root: Path | None = None) -> list[dict[str, Any]]:
    """Parse Markdown, reStructuredText, or plain text files."""
    doc_id = generate_doc_id(path, root)
    source_file = str(path).replace("\\", "/")
    content = path.read_text(encoding="utf-8", errors="replace")

    headings: list[str] = []
    lines = content.splitlines()

    for idx, line in enumerate(lines):
        trimmed = line.strip()
        if not trimmed:
            continue
        # Markdown headings (# Heading)
        if trimmed.startswith("#"):
            h = trimmed.lstrip("#").strip()
            if h and h not in headings:
                headings.append(h)
        # reStructuredText underlines (===, ---, ~~~)
        elif idx + 1 < len(lines):
            underline = lines[idx + 1].strip()
            if (
                len(underline) >= 3
                and all(c == underline[0] for c in underline)
                and underline[0] in "=-~^`\"'"
                and len(trimmed) <= len(underline) + 4
            ):
                if trimmed not in headings:
                    headings.append(trimmed)

    cleaned = clean_text(content, page_numbers=True)

    return [
        {
            "doc_id": doc_id,
            "source_file": source_file,
            "page": 1,
            "headings": headings,
            "text": cleaned,
            "tables": [],
            "method": "text",
        }
    ]


def _extract_code_headings(content: str, suffix: str, name: str) -> list[str]:
    """Extract contextual headings from code and configuration files."""
    headings: list[str] = []
    lines = content.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # C / C++ functions, structs, definitions
        if suffix in {".c", ".h", ".cpp", ".hpp"}:
            if (
                stripped.startswith(("#define ", "struct ", "enum ", "union ", "typedef struct "))
                and "{" in stripped
            ):
                h = stripped.split("{")[0].strip()
                if h and h not in headings:
                    headings.append(h)
            elif (
                re.match(
                    r"^(?:static\s+|inline\s+|const\s+|extern\s+)*[a-zA-Z_]\w*\s+(?:\*+\s*)?[a-zA-Z_]\w*\s*\([^;]*\)\s*\{?",
                    stripped,
                )
                and not stripped.startswith("if ")
                and not stripped.startswith("while ")
            ):
                h = stripped.split("{")[0].strip()
                if h and len(h) < 90 and h not in headings:
                    headings.append(h)

        # Devicetree and overlay files
        elif suffix in {".dts", ".dtsi", ".overlay"}:
            if "compatible =" in stripped:
                m = re.search(r'compatible\s*=\s*"([^"]+)"', stripped)
                if m:
                    h = f'compatible = "{m.group(1)}"'
                    if h not in headings:
                        headings.append(h)
            elif stripped.endswith("{") and not stripped.startswith("/*"):
                h = stripped.rstrip("{").strip()
                if h and len(h) < 60 and h not in headings:
                    headings.append(h)

        # Kconfig files
        elif name == "kconfig" or name.startswith("kconfig"):
            if stripped.startswith(("config ", "menuconfig ")):
                sym = stripped.split()[1]
                h = f"config {sym}"
                if h not in headings:
                    headings.append(h)
            elif stripped.startswith("menu "):
                m = re.search(r'menu\s+"([^"]+)"', stripped)
                if m:
                    h = f"menu: {m.group(1)}"
                    if h not in headings:
                        headings.append(h)

        # YAML Devicetree bindings / configs
        elif suffix in {".yaml", ".yml"}:
            if stripped.startswith("compatible:"):
                h = stripped
                if h not in headings:
                    headings.append(h)
            elif stripped.startswith("title:"):
                h = stripped
                if h not in headings:
                    headings.append(h)
            elif re.match(r"^[a-zA-Z0-9_\-]+:\s*$", line):  # top level key
                h = stripped.rstrip(":")
                if h in {"properties", "child-binding", "bus"} and h not in headings:
                    headings.append(h)

        # CMakeLists.txt
        elif name == "cmakelists.txt":
            if stripped.startswith(("cmake_minimum_required", "project(", "target_sources")):
                h = stripped.split(")")[0] + ")"
                if h not in headings:
                    headings.append(h)

        # Zephyr .conf files
        elif suffix == ".conf":
            if stripped.startswith("CONFIG_") and "=" in stripped:
                sym = stripped.split("=")[0].strip()
                if sym not in headings:
                    headings.append(sym)

        # Python files
        elif suffix == ".py":
            if stripped.startswith(("class ", "def ")):
                h = stripped.split("(")[0].split(":")[0].strip()
                if h and h not in headings:
                    headings.append(h)

    return headings[:15]  # Cap maximum headings per file to keep metadata concise


def parse_code(path: Path, root: Path | None = None) -> list[dict[str, Any]]:
    """Parse source-code or configuration file preserving all indentation and code formatting."""
    doc_id = generate_doc_id(path, root)
    source_file = str(path).replace("\\", "/")
    content = path.read_text(encoding="utf-8", errors="replace")

    # Normalize newlines
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    suffix = path.suffix.lower()
    name = path.name.lower()
    headings = _extract_code_headings(content, suffix, name)

    # Note: Indentation, whitespace, and code numbers are strictly preserved!
    return [
        {
            "doc_id": doc_id,
            "source_file": source_file,
            "page": 1,
            "headings": headings,
            "text": content.strip(),
            "tables": [],
            "method": "code",
        }
    ]


def parse_file(
    path: Path,
    root: Path | None = None,
    lang: str = "eng",
    tesseract_cmd: str | None = None,
) -> list[dict[str, Any]]:
    """Dispatch a file to the appropriate parser based on extension or filename."""
    path_obj = Path(path)
    if not path_obj.is_file():
        return []

    suffix = path_obj.suffix.lower()
    name = path_obj.name.lower()

    if suffix in PDF_SUFFIXES:
        return parse_pdf(path_obj, root=root, lang=lang, tesseract_cmd=tesseract_cmd)
    if suffix in HTML_SUFFIXES:
        return parse_html(path_obj, root=root)
    if name in CODE_FILENAMES or suffix in CODE_SUFFIXES:
        return parse_code(path_obj, root=root)
    if suffix in TEXT_SUFFIXES:
        return parse_text(path_obj, root=root)

    # Fallback to text parser if it looks like a text file
    try:
        sample = path_obj.read_bytes()[:1024]
        # Null bytes usually indicate binary files
        if b"\x00" not in sample:
            return parse_text(path_obj, root=root)
    except Exception:
        pass

    return []


def run_parsing(
    input_path: Path,
    output_path: Path,
    limit: int = 0,
    sample_size: int = 5,
    lang: str = "eng",
    tesseract_cmd: str | None = None,
) -> dict[str, int]:
    """Execute ingestion across files, writing pages.jsonl and sample_pages.json."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.is_file():
        file_list = [input_path]
        root_dir: Path | None = input_path.parent
    else:
        file_list = sorted([p for p in input_path.rglob("*") if p.is_file()])
        root_dir = input_path

    stats = {
        "docs": 0,
        "pages": 0,
        "text": 0,
        "code": 0,
        "html": 0,
        "ocr": 0,
        "needs_ocr": 0,
        "empty": 0,
        "tables": 0,
        "unsupported": 0,
        "broken": 0,
    }

    seen_doc_ids: dict[str, str] = {}
    sample_records: list[dict[str, Any]] = []

    with open(output_path, "w", encoding="utf-8") as out_f:
        for file_p in file_list:
            if limit > 0 and stats["pages"] >= limit:
                break

            try:
                records = parse_file(file_p, root=root_dir, lang=lang, tesseract_cmd=tesseract_cmd)
                if not records:
                    stats["unsupported"] += 1
                    continue

                stats["docs"] += 1

                for rec in records:
                    if limit > 0 and stats["pages"] >= limit:
                        break

                    doc_id = rec["doc_id"]
                    source_file = rec["source_file"]

                    # Duplicate doc_id detection
                    if doc_id in seen_doc_ids and seen_doc_ids[doc_id] != source_file:
                        logger.warning(
                            "Duplicate doc_id '%s' for %s (previously used for %s)",
                            doc_id,
                            source_file,
                            seen_doc_ids[doc_id],
                        )
                    seen_doc_ids[doc_id] = source_file

                    # Tally statistics
                    stats["pages"] += 1
                    method = rec.get("method", "text")
                    if method in stats:
                        stats[method] += 1

                    if not rec.get("text", "").strip():
                        stats["empty"] += 1

                    stats["tables"] += len(rec.get("tables", []))

                    # Write JSONL record
                    out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")

                    if len(sample_records) < sample_size:
                        sample_records.append(rec)

            except Exception as exc:
                stats["broken"] += 1
                print(f"Error parsing {file_p}: {type(exc).__name__} - {exc}")

    # Write sample_pages.json
    sample_path = output_path.parent / "sample_pages.json"
    with open(sample_path, "w", encoding="utf-8") as sample_f:
        json.dump(sample_records, sample_f, ensure_ascii=False, indent=2)
        sample_f.write("\n")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="BoardBridge Document Ingestion Parser")
    parser.add_argument(
        "path",
        nargs="?",
        default="data/raw",
        help="Input directory or file to parse (default: data/raw)",
    )
    parser.add_argument(
        "--out",
        default="data/parsed/pages.jsonl",
        help="Output JSONL path (default: data/parsed/pages.jsonl)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum page records to extract (default: 0 = unlimited)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=5,
        help="Number of records to save in sample_pages.json (default: 5)",
    )
    parser.add_argument(
        "--lang",
        default="eng",
        help="OCR language for Tesseract (default: eng)",
    )

    args = parser.parse_args()
    stats = run_parsing(
        input_path=Path(args.path),
        output_path=Path(args.out),
        limit=args.limit,
        sample_size=args.sample,
        lang=args.lang,
    )

    print(
        f"docs: {stats['docs']} | pages: {stats['pages']} | text: {stats['text']} | "
        f"code: {stats['code']} | html: {stats['html']} | ocr: {stats['ocr']} | "
        f"needs_ocr: {stats['needs_ocr']} | empty: {stats['empty']} | "
        f"tables: {stats['tables']} | unsupported: {stats['unsupported']} | "
        f"broken: {stats['broken']}"
    )


if __name__ == "__main__":
    main()
