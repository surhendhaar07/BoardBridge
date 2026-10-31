from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.llm.cost import aggregate_usage
from app.llm.factory import get_fallback_provider, get_llm_provider
from app.llm.manager import stream_rag_chat
from app.rag import build_rag_messages, retrieve_zephyr_context
from app.schemas import ChatRequest

app = FastAPI(title="BoardBridge", version="0.1.0")

SettingsDep = Annotated[Settings, Depends(get_settings)]


@app.get("/health")
def health(settings: SettingsDep) -> dict:
    """Liveness: the process is up. Fast and does not call the LLM or DB."""
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@app.get("/ready")
def ready(settings: SettingsDep) -> dict:
    """Readiness probe: application is ready to handle traffic."""
    return {"status": "ready", "app": settings.app_name, "environment": settings.environment}


@app.post("/chat")
async def chat(request: ChatRequest, settings: SettingsDep) -> StreamingResponse:
    """Stream RAG answers using Server-Sent Events (SSE)."""
    try:
        # Retrieve verified Zephyr RTOS context
        context, sources = retrieve_zephyr_context(request.query)
        messages = build_rag_messages(request.query, context, sources)

        # Instantiate providers
        primary_provider = get_llm_provider(settings)
        fallback_provider = get_fallback_provider(settings)

        generator = stream_rag_chat(
            messages=messages,
            sources=sources,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            settings=settings,
        )

        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {exc}") from exc


@app.get("/usage")
def usage(settings: SettingsDep) -> dict:
    """Return aggregated daily LLM usage and cost statistics from logs/cost.jsonl."""
    return aggregate_usage(settings.cost_log_path)
