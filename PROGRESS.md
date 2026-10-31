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
- [ ] Day 6 – Render live URL verified (ready for deployment connect)
- [x] Day 6 – Week 1 Git tag (week-1 tag created)
- [x] Tag week-2 created and pushed

## Daily log
| Date | What I did today | Commit |
|---|---|---|
| 2026-10-21 | Day 1: Project setup, problem definition, and initial README | Initial commit |
| 2026-10-22 | Day 2: Added 10 technical embedded firmware questions to QUESTIONS.md | Day - 1 |
| 2026-10-23 | Day 3: Collected 60 Zephyr files, updated DATASET.md, added samples | week-1 |
| 2026-10-31 | Day 5: Production LLM integration with SSE streaming, retries, fallback model, cost tracking, and /usage | Day 5 |
| 2026-10-31 | Day 6: Docker Compose with pgvector, GET /ready check, CI with smoke test, pre-commit hooks, and deployment guide | week-2 |
