"""Fake LLM provider for testing and offline local development."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from app.llm.base import LLMProvider, StreamChunk
from app.llm.cost import estimate_tokens
from app.schemas import TokenUsage


class FakeLLMProvider(LLMProvider):
    """Deterministic, offline fake LLM provider for BoardBridge."""

    provider_name: str = "fake"

    def __init__(
        self,
        default_model: str = "fake-model",
        custom_chunks: list[str] | None = None,
        error_to_raise: Exception | None = None,
        fail_after_stream: bool = False,
        chunk_delay_seconds: float = 0.0,
    ) -> None:
        self.default_model = default_model
        self.custom_chunks = custom_chunks
        self.error_to_raise = error_to_raise
        self.fail_after_stream = fail_after_stream
        self.chunk_delay_seconds = chunk_delay_seconds

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream simulated response chunks."""
        active_model = model or self.default_model

        if self.error_to_raise and not self.fail_after_stream:
            raise self.error_to_raise

        # Determine prompt text to estimate input tokens
        input_text = " ".join(m.get("content", "") for m in messages)
        input_tokens = estimate_tokens(input_text)

        if self.custom_chunks is not None:
            chunks = self.custom_chunks
        else:
            # Generate realistic Zephyr-related chunks
            chunks = [
                "For Zephyr RTOS, configure the device in your devicetree overlay ",
                "with the compatible string 'bosch,bme280' and enable ",
                "CONFIG_SENSOR=y in prj.conf.",
            ]

        accumulated_text = ""
        for i, chunk in enumerate(chunks):
            if self.chunk_delay_seconds > 0:
                await asyncio.sleep(self.chunk_delay_seconds)

            accumulated_text += chunk
            yield StreamChunk(delta=chunk, model=active_model)

            # Check if configured to simulate failure mid-stream
            if self.fail_after_stream and self.error_to_raise and i == 0:
                raise self.error_to_raise

        output_tokens = estimate_tokens(accumulated_text)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated=True,
        )
        yield StreamChunk(delta="", usage=usage, model=active_model)
