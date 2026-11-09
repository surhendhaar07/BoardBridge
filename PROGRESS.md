# Progress

Commit after every class. Tag every Friday: `git tag week-N && git push origin week-N`.

## Week 1 Tasks & Verification

### Day 1 – Project Setup & Problem Definition
- [x] Repo created from the Examate template and registered on the form
- [x] README top section filled from my project card

### Day 2 – Zephyr Questions & Dataset Planning
- [x] docs/QUESTIONS.md: 10 real embedded questions covering sensors, PWM, CAN, UART, GPIO

### Day 3 – Dataset Collection
- [x] 60 Zephyr source/documentation files collected into data/raw/
- [x] DATASET.md inventory filled and verified with scripts/count_pages.py
- [x] Sample files stored in data/sample/

### Day 5 – Production LLM Integration
- [x] LLM provider abstraction (Protocol, FakeLLMProvider, OpenAICompatProvider)
- [x] POST /chat with Server-Sent Events (SSE) streaming
- [x] Exponential backoff with full jitter and non-retry after stream start
- [x] Failover to fallback model
- [x] Cost logging to logs/cost.jsonl and GET /usage daily aggregation

### Day 6 – Deploy on Day One (Docker Compose, CI, Pre-commit & Deployment)
- [x] Day 6 – Docker Compose (db service with pgvector, api service with health dependency)
- [x] Day 6 – PostgreSQL/pgvector configured and verified via init_db.sql
- [x] Day 6 – Readiness endpoint (GET /ready checks database with safe error handling)
- [x] Day 6 – GitHub Actions CI workflow (lint, format check, automated tests)
- [x] Day 6 – Docker smoke test job in CI
- [x] Day 6 – Pre-commit hooks configured with Ruff (ruff + ruff-format) and verified
- [x] Day 6 – CI status badge in README linked to workflow
- [x] Day 6 – Week 1 Git tag (week-1 tag created)

## Week 2 Tasks & Verification

### Session 7 – CI and Going Live
- [x] Session 7 – CI workflow (.github/workflows/ci.yml with test and docker-smoke jobs)
- [x] Ruff lint check (ruff check .)
- [x] Ruff format check (ruff format --check .)
- [x] Automated tests in CI (pytest -q with Fake LLM)
- [x] Docker smoke test (boardbridge image, /health and /ready verification)
- [x] Pre-commit configuration (.pre-commit-config.yaml with pre-commit-hooks v6.0.0 & ruff v0.17.3)
- [x] Pre-commit hooks passing (check-yaml, end-of-file-fixer, trailing-whitespace, detect-private-key, ruff-check, ruff-format)
- [x] Render deployment configuration (Primary platform: Render; Docker runtime, free-tier setup, environment variables)
- [ ] Live /health endpoint verified on Render (pending user dashboard deploy)
- [ ] Live /ready endpoint verified on Render (pending user dashboard deploy)
- [ ] Live /chat streaming verified on Render (pending user dashboard deploy)
- [x] CI badge in README (linked to ci.yml workflow)
- [x] Live URL in README (https://boardbridge.onrender.com/health)
- [x] week-2 Git tag ready for submission

## Week 3 Tasks & Verification

### GenAI Session 8 – Parsing Documents
- [x] Dependencies installed (`pdfplumber`, `beautifulsoup4`, `pytesseract`, `reportlab`)
- [x] `app/ingest/clean.py` created with all 6 normalization and cleaning rules
- [x] `app/ingest/parse.py` created with modular dispatcher and 7-field record schema
- [x] PDF parsing implemented with page-by-page extraction, table isolation, and font-size heading detection
- [x] HTML parsing implemented with semantic root selection, tag removal, and table extraction
- [x] Markdown and text parsing implemented with heading extraction and safe UTF-8 decoding
- [x] Zephyr source-code parsing implemented with preserved indentation, spacing, and firmware symbol headings
- [x] Table extraction implemented with bounding-box text isolation and readable row/cell formatting
- [x] OCR support implemented with Tesseract detection and graceful `needs_ocr` fallback
- [x] Unit tests created (`tests/sample_docs.py` and `tests/test_parse.py`) covering all 23 requirements
- [x] pytest passes (50/50 tests passing across entire repository)
- [x] Ruff checks pass (`ruff check .` and `ruff format --check .`)
- [x] 50 records generated (`data/parsed/pages.jsonl` and `data/parsed/sample_pages.json`)
- [x] `sample_pages.json` inspected and validated with 5+ records
- [x] `DATASET.md` updated with comprehensive parsing documentation and run statistics

### GenAI Session 9 (Task 1) – Document Chunking and Preview
- [x] `app/rag/chunking.py` created with `MAX_CHARS = 1000`, `OVERLAP = 150`, `MIN_CHARS = 25`
- [x] Standard `Chunk` dataclass implemented with 8 provenance metadata fields
- [x] Whitespace normalization and SHA-256 content hashing (`normalise`, `content_hash`)
- [x] Duplicated table text stripping (`strip_table_text`)
- [x] Heading-based document splitting and section continuation (`split_by_heading`)
- [x] Long paragraph splitting with sentence boundary prioritization (`_cut`)
- [x] Paragraph packing with word-bounded overlap (`pack`)
- [x] Separate table chunking with repeated header schema preservation (`table_texts`)
- [x] Main chunking pipeline (`chunk_pages`) skipping `needs_ocr` and `empty`
- [x] Command-line chunk preview tool (`tools/preview_chunks.py`)
- [x] Unit test suite (`tests/test_chunking.py`) with 22/22 passing tests
- [x] 187 chunks generated and previewed on actual Zephyr dataset
- [x] Full test suite (72/72 tests) passing
- [x] `CHUNKING.md` created with complete documentation

### GenAI Session 9 (Task 2) – Embeddings, pgvector and Idempotent Ingestion
- [x] Embedder Protocol and providers implemented (`app/rag/embeddings.py`): FakeEmbedder and LocalEmbedder
- [x] LocalEmbedder with lazy import of `sentence-transformers/all-MiniLM-L6-v2` and CPU inference
- [x] Database schema defined in `app/rag/store.py` with `vector(384)`, HNSW cosine index, and `(doc_id, page)` index
- [x] Schema connection helper with `register_vector` and table creation
- [x] 3-level idempotent ingestion: in-batch deduplication, pre-embedding database check, and `ON CONFLICT (content_hash) DO NOTHING`
- [x] Section heading prepended to embedding input (`f"{chunk.section}\n{chunk.text}"`) while preserving original text
- [x] Command-line ingestion tool (`tools/ingest.py`) with `--max-pages`, `--report`, and `--db` flags
- [x] Unit test suite (`tests/test_embeddings.py` and `tests/test_store_and_ingest.py`) with 15/15 passing tests
- [x] Ingestion report documentation created (`INGESTION.md`)
- [x] Full test suite (87/87 tests) passing offline without requiring database or internet

## Daily log
| Date | What I did today | Commit |
|---|---|---|
| 2026-10-21 | Day 1: Project setup, problem definition, and initial README | Initial commit |
| 2026-10-22 | Day 2: Added 10 technical embedded firmware questions to QUESTIONS.md | Day - 1 |
| 2026-10-23 | Day 3: Collected 60 Zephyr files, updated DATASET.md, added samples | week-1 |
| 2026-10-31 | Day 5: Production LLM integration with SSE streaming, retries, fallback model, cost tracking, and /usage | Day 5 |
| 2026-10-31 | Day 6: Docker Compose with pgvector, GET /ready check, CI with smoke test, pre-commit hooks, and deployment guide | feat: compose with pgvector |
| 2026-11-03 | Session 7: CI on every push with docker-smoke, pre-commit v6.0.0 hooks, Render deployment guide, CI badge and live link | week-2 |
| 2026-11-04 | Session 8: Document parsing for Zephyr source, PDF, HTML, Markdown; 23 test cases; pages.jsonl & sample_pages.json | Session 8 |
| 2026-11-07 | Session 9 Task 1: Chunking module, 1000/150/25 constants, heading split, table chunks, preview CLI, 22 tests | Session 9 Task 1 |
| 2026-11-09 | Session 9 Task 2: Embedder abstraction, pgvector storage, HNSW index, 3-level idempotent ingestion CLI, 15 tests | Session 9 Task 2 |
