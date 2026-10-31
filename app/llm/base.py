"""Base abstractions and protocols for LLM providers."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from app.schemas import TokenUsage


class LLMError(Exception):
    """Base class for all LLM errors."""


class NonRetryableLLMError(LLMError):
    """Error that must not be retried (e.g., HTTP 400, 401, 403, 404)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RetryableLLMError(LLMError):
    """Error that can be retried (e.g., network error, timeout, HTTP 429, 5xx)."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class StreamChunk:
    """A streaming chunk emitted by an LLM provider."""

    delta: str = ""
    usage: TokenUsage | None = None
    model: str | None = None


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for provider-independent LLM implementations."""

    provider_name: str
    default_model: str

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream response chunks for given chat messages."""
        ...

