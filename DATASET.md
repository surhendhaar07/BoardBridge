# BoardBridge Dataset

## Source

- **Project:** Zephyr RTOS
- **Repository:** https://github.com/zephyrproject-rtos/zephyr
- **Raw-file source:** https://raw.githubusercontent.com/zephyrproject-rtos/zephyr/main/
- **Collection script:** `scripts/collect_zephyr_files.py`
- **Target:** At least 50 source/documentation files under `data/raw/`

## Why this dataset?

BoardBridge helps firmware engineers locate Zephyr drivers, devicetree bindings, Kconfig options, board definitions, samples, and documentation. The collected subset focuses on examples related to sensors, PWM, CAN, GPIO, UART, SPI, Blinky, and board porting.

## File types

The collector selects relevant repository files such as:

- C source and header files: `.c`, `.h`
- Devicetree and overlays: `.dts`, `.dtsi`, `.overlay`
- Bindings and configuration: `.yaml`, `.yml`, `.conf`, `Kconfig`
- Documentation: `.rst`, `.txt`, `.md`

Text/code files are counted as **files**, not pages. `count_pages.py` counts source files and, if PDF files are added later, counts their physical pages when the optional `pypdf` package is installed.

## Collect the dataset

From the repository root, run:

```bash
python scripts/collect_zephyr_files.py --target 60
python scripts/count_pages.py data/raw
```

The collector uses GitHub's public repository tree API to discover relevant files and downloads them from the official Zephyr repository. An internet connection is required. If GitHub's API rate limit is reached, wait and run the collector again.

## Reproducibility and licence

The default source URL tracks the `main` branch, so the exact content can change over time. For reproducible experiments, record the commit SHA used for collection and pin the collector to that revision.

Zephyr is generally distributed under Apache-2.0, but individual files and third-party components may carry different notices or licences. Preserve source headers and verify the licence of files before redistributing them. This dataset is intended for research and development; consult the upstream repository's licence files and individual file headers.

## Dataset inventory

- Collection date: 2026-10-23
- Zephyr revision/commit: 2a9e8ac155a3f2fd85d4559753be86a47b44ccf0
- Files collected: 60
- PDF pages, if any: nil

## Parsing

### 1. Parser Architecture
The BoardBridge document ingestion parser (`app/ingest/parse.py` and `app/ingest/clean.py`) processes raw documents into normalized, structured 7-field page records. It dispatches files based on their suffix and filename into specialized parsing strategies:
- **PDF Parser (`parse_pdf`)**: Iterates through pages with `pdfplumber`, extracts tables and bounding boxes, extracts outside text, removes repeated headers/footers, and inherits headings across pages.
- **HTML Parser (`parse_html`)**: Uses `BeautifulSoup` to strip scripts, styles, navigation, headers, footers, and sidebars, extracting headings (`h1`-`h3`) and structured tables.
- **Text & Markdown Parser (`parse_text`)**: Handles Markdown (`.md`), reStructuredText (`.rst`), and plain text (`.txt`), detecting headings and cleaning prose text.
- **Source Code and Configuration Parser (`parse_code`)**: Dedicated handler for Zephyr RTOS C/C++ source (`.c`, `.h`), devicetree bindings and overlays (`.yaml`, `.dts`, `.overlay`), Kconfig files, CMake build scripts, and configuration files (`.conf`). Strictly preserves indentation, spaces, and line structure.

### 2. Supported File Types
- C / C++ Source & Headers: `.c`, `.h`, `.cpp`, `.hpp`
- Devicetree & Bindings: `.dts`, `.dtsi`, `.overlay`, `.yaml`, `.yml`
- Configuration & Build: `.conf`, `Kconfig`, `CMakeLists.txt`
- Documentation: `.md`, `.rst`, `.txt`, `.html`, `.htm`, `.pdf`

### 3. Libraries Used
- `pdfplumber>=0.11`: PDF page iteration, table extraction, and bounding-box geometry filtering.
- `beautifulsoup4>=4.12`: HTML document sanitization, tag decomposition, and structured content extraction.
- `pytesseract>=0.3.10`: OCR text recognition for scanned pages (optional dependency with fallback to `needs_ocr`).
- `reportlab>=4.0`: Automated generation of reproducible multi-page test PDFs with tables and images.

### 4. Cleaning Rules (`app/ingest/clean.py`)
1. **Unicode NFKC Normalization**: `unicodedata.normalize("NFKC", text)` converts ligatures (e.g. `ﬁ` -> `fi`).
2. **Invisible Character Removal**: Strips soft hyphens (`\u00ad`), zero-width spaces (`\u200b`), and byte order marks (`\ufeff`). Preserves Indic script joiners (`\u200d`, `\u200c`).
3. **Broken Word Rejoining**: Automatically joins lowercase hyphen-newline-lowercase word wraps (`regu-\nlation` -> `regulation`). Does not join alphanumeric compounds like `COVID-\n19`.
4. **Standalone Page Number Removal**: Removes page-number lines (e.g. `Page 7 of 40`, `- 7 -`, `7`) while preserving numeric values inside table cells and code.
5. **Repeated Header/Footer Removal**: Detects lines repeated across >= 50% of pages in the top 2 or bottom 2 lines of documents with >= 3 pages using digit normalization (`shape()`).
6. **Whitespace Normalization**: Collapses horizontal spacing and excessive blank lines to 2 newlines while preserving paragraph structure. (Bypassed for source code to maintain indentation).

### 5. Heading Detection
- **PDF**: Dynamically calculates document body font size. Lines with font size >= 115% of body size or bold font are classified as headings. Child pages without new headings inherit the previous heading.
- **HTML**: Traverses semantic heading tags (`h1`, `h2`, `h3`).
- **Markdown / RST**: Extracts `#` header lines and underline markers (`===`, `---`, `~~~`).
- **Source Code**: Extracts function prototypes, struct definitions, devicetree compatible strings (`compatible = "..."`), Kconfig symbols (`config SYMBOL`), and YAML top-level keys.

### 6. Table Extraction
Tables are extracted as structured arrays of rows and cells. Cell text is normalized without stripping numbers. In the body text, tables are formatted as cell-separated rows (`Table 1:`, `Service | Fee (Rs)`). Table bounding boxes are excluded from normal text extraction so table text is never duplicated.

### 7. OCR Handling
Pages containing image objects and fewer than 25 characters of extractable text are identified as scanned pages. If Tesseract is available (via PATH or `TESSERACT_CMD`), the page is rendered at 300 DPI and parsed using `pytesseract` (`method="ocr"`). If Tesseract is unavailable, the page is marked with `method="needs_ocr"` and empty text without failing the parsing pipeline.

### 8. JSONL Record Schema
Every parsed record contains exactly 7 mandatory fields:
```json
{
  "doc_id": "drivers-sensor-bosch-bme280-bme280-c",
  "source_file": "data/raw/drivers/sensor/bosch/bme280/bme280.c",
  "page": 1,
  "headings": ["struct bme280_config", "static inline int bme280_bus_check(const struct device *dev)"],
  "text": "/* bme280.c - Driver for Bosch BME280 temperature and pressure sensor */ ...",
  "tables": [],
  "method": "code"
}
```

### 9. Parsing Command
```bash
python -m app.ingest.parse data/raw --limit 50
```

### 10. Actual Parsing Run Statistics
- **Documents processed:** 50 (or 60 across entire dataset)
- **Page records generated:** 50 (or 60 across entire dataset)
- **code records:** 50 (59 across entire dataset)
- **text records:** 0 (1 across entire dataset: `samples/sensor/bme280/README.rst`)
- **html records:** 0
- **ocr records:** 0
- **needs_ocr records:** 0
- **empty records:** 0
- **tables extracted:** 0
- **unsupported files:** 0
- **broken files:** 0

### Real Issues Identified and Resolved During Ingestion
1. **Duplicate `doc_id` Collision Across Directories**: Zephyr uses recurring filenames such as `CMakeLists.txt` and `Kconfig` across multiple sensor driver and sample directories (`samples/sensor/bme280/CMakeLists.txt` and `drivers/sensor/bosch/bme280/CMakeLists.txt`). Deriving `doc_id` strictly from the file stem resulted in identical document IDs. This was resolved by incorporating relative directory paths into the slug (e.g. `samples-sensor-bme280-cmakelists-txt` vs `drivers-sensor-bosch-bme280-cmakelists-txt`), preventing collisions.
2. **Page Number Removal Stripping Hyphenated Compound Numbers**: Standalone numeric regex (`^\s*\d+\s*$`) inadvertently removed the trailing number from hyphenated compounds on line breaks (such as `COVID-\n19` or `Boeing-\n737`). This was resolved by verifying that the preceding line did not terminate with an alphabetic word hyphen (`[a-zA-Z]-$`).
3. **Scanned Page Detection with Stamp Headers**: A scanned page containing repeated header and footer text produced 64 characters of extractable text, causing the parser to miss the `< 25` character threshold. This was resolved by stripping repeated header/footer lines before evaluating extractable content length.
