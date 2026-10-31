"""Tests for fallback model behavior and cost log accuracy."""
import asyncio
import json

import pytest

from app.config import Settings
from app.llm.base import LLMError, RetryableLLMError
from app.llm.fake import FakeLLMProvider
from app.llm.manager import stream_rag_chat


def test_primary_timeout_followed_by_successful_fallback(tmp_path):
    async def run():
        cost_log = tmp_path / "cost.jsonl"
        settings = Settings(
            cost_log_path=str(cost_log),
            price_input_per_million=1.0,
            price_output_per_million=2.0,
        )

        primary = FakeLLMProvider(
            default_model="primary-model",
            error_to_raise=RetryableLLMError("Read timed out"),
        )
        fallback = FakeLLMProvider(
            default_model="fallback-model",
            custom_chunks=["Fallback answer for Zephyr."],
        )

        events = []
        async for event in stream_rag_chat(
            messages=[{"role": "user", "content": "How to configure I2C?"}],
            sources=["samples/sensor/bme280/README.rst"],
            primary_provider=primary,
            fallback_provider=fallback,
            settings=settings,
        ):
            events.append(event)

        full_output = "".join(events)
        assert "Fallback answer for Zephyr." in full_output
        assert "event: done" in full_output

        # Check cost log record
        lines = cost_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["model"] == "fallback-model"
        assert record["fallback_used"] is True
        assert record["success"] is True
        assert record["cost_usd"] > 0

    asyncio.run(run())


def test_fallback_model_failure_handled_safely(tmp_path):
    async def run():
        cost_log = tmp_path / "cost.jsonl"
        settings = Settings(cost_log_path=str(cost_log))

        primary = FakeLLMProvider(
            default_model="primary-model",
            error_to_raise=RetryableLLMError("Primary failed"),
        )
        fallback = FakeLLMProvider(
            default_model="fallback-model",
            error_to_raise=RetryableLLMError("Fallback failed too"),
        )

        with pytest.raises(LLMError):
            async for _ in stream_rag_chat(
                messages=[{"role": "user", "content": "test"}],
                sources=[],
                primary_provider=primary,
                fallback_provider=fallback,
                settings=settings,
            ):
                pass

        # Verify failure record logged
        lines = cost_log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["success"] is False
        assert record["fallback_used"] is True

    asyncio.run(run())


def test_primary_success_does_not_invoke_fallback(tmp_path):
    async def run():
        cost_log = tmp_path / "cost.jsonl"
        settings = Settings(cost_log_path=str(cost_log))

        primary = FakeLLMProvider(
            default_model="primary-model",
            custom_chunks=["Primary answer."],
        )
        fallback = FakeLLMProvider(
            default_model="fallback-model",
            custom_chunks=["Should not be called"],
        )

        events = []
        async for event in stream_rag_chat(
            messages=[{"role": "user", "content": "test"}],
            sources=[],
            primary_provider=primary,
            fallback_provider=fallback,
            settings=settings,
        ):
            events.append(event)

        full_output = "".join(events)
        assert "Primary answer." in full_output
        assert "Should not be called" not in full_output

        lines = cost_log.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["model"] == "primary-model"
        assert record["fallback_used"] is False
        assert record["success"] is True

    asyncio.run(run())


def test_fallback_not_triggered_after_partial_output(tmp_path):
    async def run():
        cost_log = tmp_path / "cost.jsonl"
        settings = Settings(cost_log_path=str(cost_log))

        primary = FakeLLMProvider(
            default_model="primary-model",
            custom_chunks=["Partial output started "],
            error_to_raise=RetryableLLMError("Connection broke mid-stream"),
            fail_after_stream=True,
        )
        fallback = FakeLLMProvider(
            default_model="fallback-model",
            custom_chunks=["Fallback replacement."],
        )

        events = []
        with pytest.raises(LLMError):
            async for event in stream_rag_chat(
                messages=[{"role": "user", "content": "test"}],
                sources=[],
                primary_provider=primary,
                fallback_provider=fallback,
                settings=settings,
            ):
                events.append(event)

        full_output = "".join(events)
        # First chunk was sent, fallback must NEVER be called
        assert "Partial output started" in full_output
        assert "Fallback replacement" not in full_output

        lines = cost_log.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[0])
        assert record["success"] is False
        assert record["fallback_used"] is False

    asyncio.run(run())
