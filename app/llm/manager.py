"""Streaming and fallback execution manager for BoardBridge."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from app.config import Settings
from app.llm.base import LLMError, LLMProvider, RetryableLLMError
from app.llm.cost import CostRecord, calculate_cost, estimate_tokens, log_cost
from app.schemas import DoneEventData, TokenUsage


async def stream_rag_chat(
    messages: list[dict[str, str]],
    sources: list[str],
    primary_provider: LLMProvider,
    fallback_provider: LLMProvider | None,
    settings: Settings,
) -> AsyncIterator[str]:
    """Execute streaming LLM call with fallback model support and SSE output formatting.

    SSE Format:
        data: {"delta": "Generated text"}\n\n
        event: done\n
        data: {"usage": {...}, "cost_usd": 0.001, "sources": [...]}\n\n
    """
    start_time = time.monotonic()
    active_provider = primary_provider
    active_model = primary_provider.default_model
    fallback_used = False
    has_streamed_any_text = False
    final_usage: TokenUsage | None = None
    accumulated_output = ""

    try:
        # Step 1: Attempt generation with primary provider
        try:
            async for chunk in primary_provider.stream(messages):
                if chunk.delta:
                    has_streamed_any_text = True
                    accumulated_output += chunk.delta
                    yield f"data: {json.dumps({'delta': chunk.delta})}\n\n"
                if chunk.usage:
                    final_usage = chunk.usage
                if chunk.model:
                    active_model = chunk.model

        except Exception as primary_err:
            # Check fallback conditions:
            # 1. Fallback provider must be configured.
            # 2. No text has been streamed yet (switching models mid-stream would duplicate/corrupt output).
            # 3. Error is retryable (timeout, network error, 429, 5xx).
            can_fallback = (
                fallback_provider is not None
                and not has_streamed_any_text
                and isinstance(primary_err, RetryableLLMError | TimeoutError | ConnectionError)
            )

            if not can_fallback:
                # If partial text was already sent, or primary error is non-retryable, fail immediately
                # Note: We must not switch to fallback model once any partial answer text has been
                # streamed to the client, as doing so would duplicate or corrupt the response.
                raise

            # Step 2: Switch to fallback model
            fallback_used = True
            active_provider = fallback_provider
            active_model = fallback_provider.default_model

            async for chunk in fallback_provider.stream(messages):
                if chunk.delta:
                    has_streamed_any_text = True
                    accumulated_output += chunk.delta
                    yield f"data: {json.dumps({'delta': chunk.delta})}\n\n"
                if chunk.usage:
                    final_usage = chunk.usage
                if chunk.model:
                    active_model = chunk.model

        # Calculate final tokens and cost
        if final_usage is None:
            input_text = " ".join(m.get("content", "") for m in messages)
            final_usage = TokenUsage(
                input_tokens=estimate_tokens(input_text),
                output_tokens=estimate_tokens(accumulated_output),
                estimated=True,
            )

        latency_ms = round((time.monotonic() - start_time) * 1000.0, 2)
        cost_usd = calculate_cost(
            final_usage.input_tokens,
            final_usage.output_tokens,
            settings.price_input_per_million,
            settings.price_output_per_million,
        )

        # Record success to cost log
        record = CostRecord(
            provider=active_provider.provider_name,
            model=active_model,
            input_tokens=final_usage.input_tokens,
            output_tokens=final_usage.output_tokens,
            estimated=final_usage.estimated,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            success=True,
            fallback_used=fallback_used,
        )
        log_cost(record, log_path=settings.cost_log_path)

        # Emit completion SSE event
        done_payload = DoneEventData(
            usage=final_usage,
            cost_usd=cost_usd,
            sources=sources,
        )
        yield f"event: done\ndata: {json.dumps(done_payload.model_dump())}\n\n"

    except Exception as exc:
        latency_ms = round((time.monotonic() - start_time) * 1000.0, 2)
        # Log failure record
        fail_record = CostRecord(
            provider=active_provider.provider_name,
            model=active_model,
            input_tokens=0,
            output_tokens=0,
            estimated=True,
            latency_ms=latency_ms,
            cost_usd=0.0,
            success=False,
            fallback_used=fallback_used,
        )
        log_cost(fail_record, log_path=settings.cost_log_path)
        raise LLMError(f"LLM streaming failed: {exc}") from exc
