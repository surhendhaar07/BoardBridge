"""Tests for LLM providers: Fake and OpenAI-compatible with retries, timeout, and backoff."""

import asyncio

import httpx
import pytest

from app.llm.base import LLMError, NonRetryableLLMError, RetryableLLMError
from app.llm.fake import FakeLLMProvider
from app.llm.openai_compat import OpenAICompatProvider, calculate_backoff


def test_fake_provider_generates_response():
    async def run():
        provider = FakeLLMProvider(default_model="test-model")
        chunks = []
        async for chunk in provider.stream([{"role": "user", "content": "How to blink LED?"}]):
            chunks.append(chunk)

        # Should yield text deltas and final usage chunk
        text_deltas = [c.delta for c in chunks if c.delta]
        full_text = "".join(text_deltas)
        assert "Zephyr RTOS" in full_text
        assert chunks[-1].usage is not None
        assert chunks[-1].usage.input_tokens > 0
        assert chunks[-1].usage.output_tokens > 0

    asyncio.run(run())


def test_openai_compat_streams_chunks():
    async def run():
        sse_data = (
            b'data: {"choices": [{"delta": {"content": "Zephyr "}}]}\n\n'
            b'data: {"choices": [{"delta": {"content": "RTOS"}}]}\n\n'
            b'data: {"usage": {"prompt_tokens": 12, "completion_tokens": 6}}\n\n'
            b"data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=sse_data)

        provider = OpenAICompatProvider(
            base_url="https://api.openai-mock.com/v1",
            api_key="mock-key",
            default_model="llama3",
            transport=httpx.MockTransport(handler),
        )

        chunks = []
        async for chunk in provider.stream([{"role": "user", "content": "hello"}]):
            chunks.append(chunk)

        text = "".join(c.delta for c in chunks if c.delta)
        assert text == "Zephyr RTOS"
        assert chunks[-1].usage is not None
        assert chunks[-1].usage.input_tokens == 12
        assert chunks[-1].usage.output_tokens == 6
        assert chunks[-1].usage.estimated is False

    asyncio.run(run())


def test_http_503_retries_and_eventually_succeeds():
    async def run():
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(503, content=b"Service Unavailable")
            return httpx.Response(
                200,
                content=b'data: {"choices": [{"delta": {"content": "Success"}}]}\n\ndata: [DONE]\n\n',
            )

        provider = OpenAICompatProvider(
            base_url="https://api.openai-mock.com/v1",
            default_model="test-model",
            max_retries=2,
            backoff_base_seconds=0.01,  # fast backoff for tests
            transport=httpx.MockTransport(handler),
        )

        chunks = []
        async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)

        assert call_count == 2
        assert "".join(c.delta for c in chunks if c.delta) == "Success"

    asyncio.run(run())


def test_http_401_does_not_retry():
    async def run():
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(401, content=b'{"error": "Unauthorized"}')

        provider = OpenAICompatProvider(
            base_url="https://api.openai-mock.com/v1",
            default_model="test-model",
            max_retries=3,
            backoff_base_seconds=0.01,
            transport=httpx.MockTransport(handler),
        )

        with pytest.raises(NonRetryableLLMError) as exc_info:
            async for _ in provider.stream([{"role": "user", "content": "hi"}]):
                pass

        assert call_count == 1
        assert exc_info.value.status_code == 401

    asyncio.run(run())


def test_timeout_retries_and_eventually_fails():
    async def run():
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.ReadTimeout("Read timed out")

        provider = OpenAICompatProvider(
            base_url="https://api.openai-mock.com/v1",
            default_model="test-model",
            max_retries=2,
            backoff_base_seconds=0.01,
            transport=httpx.MockTransport(handler),
        )

        with pytest.raises(RetryableLLMError):
            async for _ in provider.stream([{"role": "user", "content": "hi"}]):
                pass

        # Initial attempt + 2 retries = 3 total attempts
        assert call_count == 3

    asyncio.run(run())


def test_backoff_delay_stays_within_configured_limits():
    base = 0.5
    cap = 8.0
    for attempt in range(15):
        for _ in range(20):
            delay = calculate_backoff(attempt, base=base, cap=cap)
            assert 0.0 <= delay <= cap
            max_bound = min(cap, base * (2**attempt))
            assert delay <= max_bound


def test_no_retry_after_streaming_starts():
    async def run():
        call_count = 0

        class FailingStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices": [{"delta": {"content": "First partial text"}}]}\n\n'
                raise httpx.ReadError("Connection lost mid-stream")

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, stream=FailingStream())

        provider = OpenAICompatProvider(
            base_url="https://api.openai-mock.com/v1",
            default_model="test-model",
            max_retries=3,
            backoff_base_seconds=0.01,
            transport=httpx.MockTransport(handler),
        )

        yielded_chunks = []
        with pytest.raises(LLMError) as exc_info:
            async for chunk in provider.stream([{"role": "user", "content": "hi"}]):
                yielded_chunks.append(chunk)

        # First chunk was emitted before error
        assert len(yielded_chunks) == 1
        assert yielded_chunks[0].delta == "First partial text"
        # Never retried because partial text was already yielded!
        assert call_count == 1
        assert "Stream interrupted after partial output" in str(exc_info.value)

    asyncio.run(run())
