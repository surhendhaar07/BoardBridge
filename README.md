# BoardBridge

## Problem
Firmware engineers developing embedded systems often struggle to identify the correct drivers, devicetree bindings, Kconfig options, and working samples in the large Zephyr RTOS repository. With thousands of source files and hardware configurations, manually finding compatible components can consume significant development time and lead to configuration errors. Existing documentation searches may not provide a complete, board-specific answer connecting the driver, hardware description, and build configuration. BoardBridge solves this problem by combining repository indexing, hybrid code search, and Retrieval-Augmented Generation (RAG) to provide source-cited technical answers. Its AI research agent further investigates complex hardware integration questions and flags claims that cannot be verified against the source code.

## Who it is for
Embedded Firmware Engineer: An engineer at an EV charging startup in Coimbatore migrating controller firmware to a new ARM Cortex-M development board.
Embedded Systems Developer: A developer working with Zephyr RTOS who needs to identify compatible sensors, peripheral drivers, devicetree properties, Kconfig options, and reference implementations quickly.

## Signature feature
Board Bring-up Sheet: Enter a development board and a sensor or peripheral to generate a structured integration report containing the relevant driver source, devicetree compatible string and properties, required Kconfig options, hardware configuration considerations, and related sample code. Each technical claim is linked to supporting source files and line references. Unsupported or unverified claims are explicitly flagged rather than presented as confirmed facts.

## Hardest problem (my interview story)
The hardest engineering challenge in BoardBridge is reliably ingesting and indexing more than 25,000 repository files, including C source code, headers, YAML devicetree bindings, Kconfig files, board definitions, and documentation. Processing such a large repository requires resumable background jobs, progress tracking, retry handling, and duplicate prevention. If a worker crashes halfway through ingestion, the system must resume from the last reliable checkpoint without reprocessing completed files unnecessarily or creating duplicate chunks. I plan to address this through persistent job states, content-based identifiers, idempotent indexing, and automated crash-recovery tests.

## Dataset
| Source | Link | Documents | Pages | Licence / terms |
|---|---|---|---|---|
| Zephyr RTOS source repository | [GitHub](https://github.com/zephyrproject-rtos/zephyr) | 25,000+ target files across C, headers, YAML, Kconfig, devicetree, board definitions, samples, and documentation | Not applicable to source files; record page counts for ingested PDFs or other paginated documents, if included | Apache-2.0 for files covered by that licence; verify individual file headers and third-party component licences |

## 10 real questions
See [docs/QUESTIONS.md](docs/QUESTIONS.md).

## LLM Provider Architecture

BoardBridge uses a decoupled, provider-independent LLM architecture located in `app/llm/`:
- `app/llm/base.py`: Defines the `LLMProvider` Protocol and `StreamChunk` data model.
- `app/llm/fake.py`: Deterministic, offline fake provider used for local testing and CI without API keys.
- `app/llm/openai_compat.py`: Robust client for OpenAI-compatible endpoints (Ollama, Groq, Gemini OpenAI endpoint, vLLM, OpenRouter) with configurable timeout, exponential backoff with full jitter, and streaming chunk handling.
- `app/llm/factory.py`: Provider factory that instantiates the configured primary and fallback providers.
- `app/llm/manager.py`: Manages SSE response streaming, fallback model failover, and cost logging.
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

## Environment Variable Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

Configuration variables supported in `.env`:

```env
APP_NAME=BoardBridge
ENVIRONMENT=local

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

## Retry and Fallback Behavior

1. **Exponential Backoff with Full Jitter**:
   $$\text{delay} = \text{random.uniform}(0, \min(\text{cap}, \text{base} \times 2^{\text{attempt}}))$$
   - Base delay: `0.5s`, Maximum cap: `8.0s`.
   - Retries on network connection errors, timeouts, HTTP 429, and HTTP 5xx errors.
   - Non-retryable errors (HTTP 400, 401, 403, 404) fail immediately.

2. **No Retry After Streaming Starts**:
   Once any token delta has been streamed to the client, the provider will never retry the request to avoid duplicate or corrupted output.

3. **Fallback Model**:
   If the primary model encounters a retryable network error or timeout *before* any tokens are streamed, it seamlessly switches to `LLM_FALLBACK_MODEL`. The cost log accurately records which model answered and marks `fallback_used: true`.

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

## Run it
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                 # Windows: copy .env.example .env
uvicorn app.main:app --reload
curl http://localhost:8000/health
```

## Automated Testing
```bash
ruff check .
pytest -q
```
