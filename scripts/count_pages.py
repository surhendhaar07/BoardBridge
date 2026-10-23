#!/usr/bin/env python3
"""Count files and optional PDF pages under a directory.

Text/code source files count as files (not physical pages).
PDF pages are counted when pypdf is installed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

TEXT_SUFFIXES = {
    ".c", ".h", ".yaml", ".yml", ".dts", ".dtsi", ".overlay",
    ".rst", ".md", ".txt", ".conf", ".py", ".json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default="data/raw", help="directory to count (default: data/raw)")
    args = parser.parse_args()

    root = Path(args.directory)
    if not root.exists():
        print(f"Directory not found: {root}")
        return 1

    files = [p for p in root.rglob("*") if p.is_file()]
    pdfs = [p for p in files if p.suffix.lower() == ".pdf"]
    source_files = [p for p in files if p.suffix.lower() in TEXT_SUFFIXES or p.name == "Kconfig"]

    pdf_page_count = None
    if pdfs:
        try:
            from pypdf import PdfReader
            pdf_page_count = sum(len(PdfReader(str(path)).pages) for path in pdfs)
        except ImportError:
            print("Note: install pypdf to count PDF pages: python -m pip install pypdf")

    print(f"Directory: {root.resolve()}")
    print(f"Total files: {len(files)}")
    print(f"Recognized source/documentation files: {len(source_files)}")
    print(f"PDF files: {len(pdfs)}")
    if pdf_page_count is not None:
        print(f"PDF pages: {pdf_page_count}")
    print(f"50+ files target: {'MET' if len(files) >= 50 else 'NOT MET'}")
    return 0 if len(files) >= 50 else 2


if __name__ == "__main__":
    raise SystemExit(main())
