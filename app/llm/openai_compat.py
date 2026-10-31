"""OpenAI-compatible LLM provider with timeout, retry, backoff, and streaming."""
from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.base import LLMError, LLMProvider, NonRetryableLLMError, RetryableLLMError, StreamChunk
from app.llm.cost import estimate_tokens
from app.schemas import TokenUsage

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS_CODES = {400, 401, 403, 404}


def calculate_backoff(attempt: int, base: float = 0.5, cap: float = 8.0) -> float:
    """Calculate exponential backoff with full jitter: delay in [0, min(cap, base * 2^attempt)]."""
    max_delay = min(cap, base * (2 ** attempt))
    return random.uniform(0, max_delay)


class OpenAICompatProvider(LLMProvider):
    """Client for OpenAI-compatible LLM endpoints (Ollama, Groq, Gemini, vLLM, etc.)."""

    provider_name: str = "openai_compat"

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        default_model: str = "llama3.1:8b",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 0.5,
        backoff_cap_seconds: float = 8.0,
        client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_cap_seconds = backoff_cap_seconds
        self._custom_client = client
        self._transport = transport

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_client(self) -> httpx.AsyncClient:
        if self._custom_client is not None:
            return self._custom_client
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(self.timeout_seconds),
        )

    def calculate_backoff_delay(self, attempt: int) -> float:
        """Instance method exposing the backoff formula."""
        return calculate_backoff(
            attempt,
            base=self.backoff_base_seconds,
            cap=self.backoff_cap_seconds,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat completions with retries, exponential backoff, and full jitter."""
        active_model = model or self.default_model
        endpoint = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": active_model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        # Track full text for fallback token estimation if provider does not return usage
        input_text = " ".join(m.get("content", "") for m in messages)
        accumulated_text = ""
        provider_usage: TokenUsage | None = None

        has_streamed_any_text = False
        attempt = 0

        while True:
            try:
                client = self._get_client()
                try:
                    async with client.stream(
                        "POST",
                        endpoint,
                        json=payload,
                        headers=self._get_headers(),
                        timeout=self.timeout_seconds,
                    ) as response:
                        if response.status_code in NON_RETRYABLE_STATUS_CODES:
                            raise NonRetryableLLMError(
                                f"HTTP {response.status_code} error from LLM provider",
                                status_code=response.status_code,
                            )
                        if response.status_code in RETRYABLE_STATUS_CODES:
                            raise RetryableLLMError(
                                f"HTTP {response.status_code} error from LLM provider",
                                status_code=response.status_code,
                            )
                        if response.status_code != 200:
                            raise NonRetryableLLMError(
                                f"Unexpected HTTP {response.status_code} error from LLM provider",
                                status_code=response.status_code,
                            )

                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line or not line.startswith("data:"):
                                continue

                            data_str = line[5:].strip()
                            if data_str == "[DONE]":
                                break

                            try:
                                chunk_json = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue

                            # Check for stream usage reported in chunk
                            raw_usage = chunk_json.get("usage")
                            if raw_usage:
                                provider_usage = TokenUsage(
                                    input_tokens=int(raw_usage.get("prompt_tokens", 0)),
                                    output_tokens=int(raw_usage.get("completion_tokens", 0)),
                                    estimated=False,
                                )

                            choices = chunk_json.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}).get("content", "")
                                if delta:
                                    has_streamed_any_text = True
                                    accumulated_text += delta
                                    yield StreamChunk(delta=delta, model=active_model)

                finally:
                    # Close client only if we created it locally
                    if self._custom_client is None:
                        await client.aclose()

                # If request finished successfully, yield final usage chunk and return
                final_usage = provider_usage or TokenUsage(
                    input_tokens=estimate_tokens(input_text),
                    output_tokens=estimate_tokens(accumulated_text),
                    estimated=True,
                )
                yield StreamChunk(delta="", usage=final_usage, model=active_model)
                return

            except NonRetryableLLMError:
                # Do not retry non-retryable client errors (400, 401, 403, 404)
                raise

            except Exception as exc:
                # Check critical requirement: never retry once any answer text has already been streamed
                if has_streamed_any_text:
                    # Note: We must never retry once output has been streamed to the client
                    # to prevent partial duplicate responses or corrupted output streams.
                    raise LLMError(f"Stream interrupted after partial output: {exc}") from exc

                is_retryable = (
                    isinstance(exc, (RetryableLLMError, httpx.TimeoutException, httpx.NetworkError))
                )

                if is_retryable and attempt < self.max_retries:
                    delay = self.calculate_backoff_delay(attempt)
                    attempt += 1
                    await asyncio.sleep(delay)
                    continue

                if isinstance(exc, RetryableLLMError):
                    raise
                if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
                    raise RetryableLLMError(f"Network error communicating with LLM: {exc}") from exc
                raise LLMError(f"LLM call failed: {exc}") from exc

