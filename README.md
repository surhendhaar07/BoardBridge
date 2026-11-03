# BoardBridge

[![CI](https://github.com/surhendhaar07/BoardBridge/actions/workflows/ci.yml/badge.svg)](https://github.com/surhendhaar07/BoardBridge/actions/workflows/ci.yml)

Live: https://boardbridge.onrender.com/health

> The application is hosted on a free-tier instance. It may sleep after inactivity, and the first request after sleeping can take approximately one minute.

## Problem
Firmware engineers developing embedded systems often struggle to identify the correct drivers, devicetree bindings, Kconfig options, and working samples in the large Zephyr RTOS repository. With thousands of source files and hardware configurations, manually finding compatible components can consume significant development time and lead to configuration errors. Existing documentation searches may not provide a complete, board-specific answer connecting the driver, hardware description, and build configuration. BoardBridge solves this problem by combining repository indexing, hybrid code search, and Retrieval-Augmented Generation (RAG) to provide source-cited technical answers. Its AI research agent further investigates complex hardware integration questions and flags claims that cannot be verified against the source code.

## Who it is for
- **Embedded Firmware Engineer**: An engineer at an EV charging startup in Coimbatore migrating controller firmware to a new ARM Cortex-M development board.
- **Embedded Systems Developer**: A developer working with Zephyr RTOS who needs to identify compatible sensors, peripheral drivers, devicetree properties, Kconfig options, and reference implementations quickly.

## Signature feature
**Board Bring-up Sheet**: Enter a development board and a sensor or peripheral to generate a structured integration report containing the relevant driver source, devicetree compatible string and properties, required Kconfig options, hardware configuration considerations, and related sample code. Each technical claim is linked to supporting source files and line references. Unsupported or unverified claims are explicitly flagged rather than presented as confirmed facts.

## Hardest problem (my interview story)
The hardest engineering challenge in BoardBridge is reliably ingesting and indexing more than 25,000 repository files, including C source code, headers, YAML devicetree bindings, Kconfig files, board definitions, and documentation. Processing such a large repository requires resumable background jobs, progress tracking, retry handling, and duplicate prevention. If a worker crashes halfway through ingestion, the system must resume from the last reliable checkpoint without reprocessing completed files unnecessarily or creating duplicate chunks. I plan to address this through persistent job states, content-based identifiers, idempotent indexing, and automated crash-recovery tests.

## Tech Stack
- **API Framework**: FastAPI, Uvicorn, Pydantic v2, Pydantic Settings
- **Database & Vectors**: PostgreSQL 16 with `pgvector` (`pgvector/pgvector:pg16`), `psycopg` 3
- **Containerization**: Docker, Docker Compose
- **Tooling & CI/CD**: Ruff (linter & formatter), Pytest, Pre-commit, GitHub Actions CI
- **RAG & LLM**: Provider-independent abstraction (`FakeLLMProvider`, `OpenAICompatProvider`), SSE streaming, exponential backoff with full jitter, failover fallback model, and cost tracking

## Dataset
| Source | Link | Documents | Pages | Licence / terms |
|---|---|---|---|---|
| Zephyr RTOS source repository | [GitHub](https://github.com/zephyrproject-rtos/zephyr) | 25,000+ target files across C, headers, YAML, Kconfig, devicetree, board definitions, samples, and documentation | Not applicable to source files; 60 raw files collected under `data/raw/` and samples in `data/sample/` | Apache-2.0 for files covered by that licence; verify individual file headers and third-party component licences |

## 10 real questions
See [docs/QUESTIONS.md](docs/QUESTIONS.md).

---

## Architecture Overview

BoardBridge uses a decoupled, provider-independent LLM architecture located in `app/llm/`:
- `app/llm/base.py`: Defines the `LLMProvider` Protocol and `StreamChunk` data model.
- `app/llm/fake.py`: Deterministic, offline fake provider used for local testing and CI without API keys.
- `app/llm/openai_compat.py`: Robust client for OpenAI-compatible endpoints (Ollama, Groq, Gemini OpenAI endpoint, vLLM, OpenRouter) with configurable timeout, exponential backoff with full jitter, and streaming chunk handling.
- `app/llm/factory.py`: Provider factory that instantiates the configured primary and fallback providers.
- `app/llm/manager.py`: Manages SSE response streaming, fallback model failover, and cost logging.
- `app/db.py`: Database connection and readiness verification using `psycopg`.
- `app/rag.py`: Retrieves actual Zephyr RTOS documentation and source code to inject verified context into the LLM prompt.

```
User Request (POST /chat)
         │
         ▼
[app.rag: retrieve_zephyr_context]
         │ (verified source references)
         ▼
[app.llm.manager: stream_rag_chat]
    ├── Primary Provider (OpenAICompatProvider / FakeLLMProvider)
    │      └── Failover (Timeout, 429, 5xx before output) ──► Fallback Provider
    ├── Streaming SSE chunks: data: {"delta": ...}
    └── Final completion event: event: done, data: {"usage": ..., "cost_usd": ...}
```

---

## Health vs. Readiness Endpoints

- **`GET /health` (Liveness)**:
  Verifies that the FastAPI process is up and receiving requests. Must be fast, lightweight, and **must not** touch the database or external LLM services. Returns HTTP 200:
  ```json
  {"status": "ok", "app": "BoardBridge", "environment": "local"}
  ```

- **`GET /ready` (Readiness)**:
  Checks whether the service is ready to handle queries.
  - If `DATABASE_URL` is unconfigured: returns HTTP 200:
    ```json
    {"status": "ready", "database": "not configured"}
    ```
  - If `DATABASE_URL` is configured: executes `SELECT 1;` with a 3-second timeout via `psycopg`. If successful, returns HTTP 200:
    ```json
    {"status": "ready", "database": "ok"}
    ```
  - If database connection fails: returns HTTP 503 `{"detail": "Database connection check failed"}` without leaking database credentials.

---

## Docker Compose Setup

Run the complete BoardBridge stack (PostgreSQL with pgvector + FastAPI application) with:

```bash
docker compose up --build
```

### Services
1. **`db`** (`pgvector/pgvector:pg16`):
   - Database: `rag`
   - User: `app`
   - Password: `app` (local development only)
   - Port: `5432:5432`
   - Persistent volume: `pgdata`
   - Healthcheck: `pg_isready -U app -d rag`
   - Automatically initializes pgvector extension via `./scripts/init_db.sql`.
2. **`api`** (FastAPI app):
   - Port: `8000:8000`
   - Database connection: `DATABASE_URL=postgresql://app:app@db:5432/rag`
   - Waits for `db` to pass healthcheck before starting.

Verify services:
```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

---

## PostgreSQL & pgvector Verification

The pgvector extension is automatically created via `scripts/init_db.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

Verify directly inside the running container:
```bash
docker compose exec db psql -U app -d rag -c "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
```

---

## Environment Variable Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

Configuration variables supported in `.env`:

```env
APP_NAME=BoardBridge
ENVIRONMENT=local

# Database (PostgreSQL with pgvector)
# Local: postgresql://app:app@localhost:5432/rag
# Docker Compose: postgresql://app:app@db:5432/rag
DATABASE_URL=

# Primary LLM provider: "fake" or "openai_compat"
LLM_PROVIDER=fake
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=
LLM_MODEL=llama3.1:8b

# Resilience and retry settings
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=3
LLM_BACKOFF_BASE_SECONDS=0.5

# Fallback model configuration
LLM_FALLBACK_MODEL=
LLM_FALLBACK_BASE_URL=
LLM_FALLBACK_API_KEY=

# Pricing in USD per million tokens
PRICE_INPUT_PER_MILLION=0.15
PRICE_OUTPUT_PER_MILLION=0.60

# Cost logging path
COST_LOG_PATH=logs/cost.jsonl
```

### Running with the Fake Provider

For local development and automated testing without external API credentials:
```env
LLM_PROVIDER=fake
LLM_MODEL=llama3.1:8b
```

### Running with an OpenAI-Compatible Provider

To connect to Groq, Ollama, Gemini, or OpenRouter:
```env
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_your_api_key_here
LLM_MODEL=llama-3.1-8b-instant
LLM_FALLBACK_MODEL=llama-3.1-70b-versatile
```

---

## SSE Streaming Format

The `POST /chat` endpoint streams Server-Sent Events (SSE) with `media_type="text/event-stream"`.

### Chunk Events
```text
data: {"delta": "For Zephyr RTOS, configure the device in your devicetree overlay "}

data: {"delta": "with the compatible string 'bosch,bme280'."}
```

### Completion Event
```text
event: done
data: {"usage": {"input_tokens": 580, "output_tokens": 42, "estimated": false}, "cost_usd": 0.000112, "sources": ["samples/sensor/bme280/arduino_i2c.overlay"]}
```

---

## Retry and Fallback Behavior

1. **Exponential Backoff with Full Jitter**:
   $$\text{delay} = \text{random.uniform}(0, \min(8.0, 0.5 \times 2^{\text{attempt}}))$$
   - Base delay: `0.5s`, Maximum cap: `8.0s`.
   - Retries on network connection errors, timeouts, HTTP 429, and HTTP 5xx errors.
   - Non-retryable errors (HTTP 400, 401, 403, 404) fail immediately.

2. **No Retry After Streaming Starts**:
   Once any token delta has been streamed to the client, the provider will never retry the request to avoid duplicate or corrupted output.

3. **Fallback Model**:
   If the primary model encounters a retryable network error or timeout *before* any tokens are streamed, it seamlessly switches to `LLM_FALLBACK_MODEL`. The cost log accurately records which model answered and marks `fallback_used: true`.

---

## Token Usage and Cost Tracking

Every LLM call appends a structured record to `logs/cost.jsonl`:
```json
{
  "provider": "openai_compat",
  "model": "llama-3.1-8b-instant",
  "input_tokens": 580,
  "output_tokens": 42,
  "estimated": false,
  "latency_ms": 320.5,
  "cost_usd": 0.000112,
  "success": true,
  "fallback_used": false,
  "timestamp": "2026-10-31T18:00:00.123456+00:00"
}
```

### `GET /usage` Endpoint

Aggregates daily UTC statistics from `logs/cost.jsonl`:

```bash
curl http://localhost:8000/usage
```

Example response:
```json
{
  "2026-10-31": {
    "calls": 12,
    "input_tokens": 9400,
    "output_tokens": 3100,
    "cost_usd": 0.00327
  }
}
```

---

## GitHub Actions CI Pipeline

The CI workflow `.github/workflows/ci.yml` runs automatically on pushes and pull requests targeting `main`.

### Stages
1. **`test` Job**:
   - Sets up Python 3.12.
   - Installs dependencies from `requirements-dev.txt`.
   - Sets `LLM_PROVIDER=fake`.
   - Runs Ruff linter: `ruff check .`
   - Runs Ruff format check: `ruff format --check .`
   - Runs test suite: `pytest -q`
2. **`docker-smoke-test` Job**:
   - Runs after `test` succeeds.
   - Builds image `boardbridge:ci` from `Dockerfile`.
   - Starts container with `LLM_PROVIDER=fake` on port 8000.
   - Verifies liveness: `curl -fsS http://localhost:8000/health`.

### Why CI Uses a Fake LLM
Continuous Integration uses the `FakeLLMProvider` rather than a real LLM provider because:
1. **Deterministic Results**: Test assertions require consistent, predictable output.
2. **Cost Avoidance**: Running test suites on every commit would consume external API credits.
3. **Rate Limits**: CI runners make frequent concurrent calls that trigger third-party API rate limits.
4. **Reliability**: Eliminates test failures caused by external network flakiness.
5. **No Secret Leakage**: CI does not need real API keys stored in repository secrets.

---

## Pre-commit Hooks

BoardBridge uses `pre-commit` with Ruff for automated linting and formatting on every commit.

### Setup
```bash
pip install pre-commit
pre-commit install
```

### Run on All Files
```bash
pre-commit run --all-files
```

---

## Deployment to Render

BoardBridge is ready for deployment as a Docker Web Service on [Render](https://render.com/).

### Deployment Steps
1. Push repository changes to GitHub.
2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** > **Web Service**.
4. Select **Build and deploy from a Git repository** and connect `surhendhaar07/BoardBridge`.
5. Select **Docker** as the Runtime environment.
6. Instance type: **Free** (or Starter).
7. Configure Environment Variables in Render:
   - `ENVIRONMENT`: `production`
   - `LLM_PROVIDER`: `openai_compat` (or `fake`)
   - `LLM_BASE_URL`: e.g. `https://api.groq.com/openai/v1`
   - `LLM_MODEL`: e.g. `llama-3.1-8b-instant`
   - `LLM_API_KEY`: your secret API key
   - `DATABASE_URL`: Hosted PostgreSQL connection string with pgvector (e.g. from Neon, Supabase, or Render PostgreSQL).
8. Click **Create Web Service**.
9. Once deployed, verify:
   ```bash
   curl https://<your-render-subdomain>.onrender.com/health
   curl https://<your-render-subdomain>.onrender.com/ready
   ```

### Free-Tier Deployment Limitations
- **Ephemeral Storage**: Free instances have ephemeral filesystems. Cost logs saved to `logs/cost.jsonl` are reset on container restarts. In Week 2 Session 4, cost logs transition to persistent PostgreSQL storage.
- **Spin-down**: Free Render Web Services spin down after 15 minutes of inactivity; the first request after spin-down may take ~50 seconds to warm up.

---

## Local Development Commands

```bash
# Setup virtual environment & dependencies
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run pre-commit checks across all files
pre-commit run --all-files

# Run linter and formatter checks directly
ruff check .
ruff format --check .

# Run automated tests
pytest -q

# Run Docker Compose stack (db + api)
docker compose up --build

# Run local development server directly
uvicorn app.main:app --reload
curl localhost:8000/health
curl localhost:8000/ready
```

## Live link
- Service Root: https://boardbridge.onrender.com
- Health Check: https://boardbridge.onrender.com/health
- Readiness Check: https://boardbridge.onrender.com/ready
