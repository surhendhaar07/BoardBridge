"""LLM provider abstraction, cost tracking, and streaming for BoardBridge."""
from app.llm.base import (
    LLMError,
    LLMProvider,
    NonRetryableLLMError,
    RetryableLLMError,
    StreamChunk,
)
from app.llm.cost import CostRecord, aggregate_usage, calculate_cost, estimate_tokens, log_cost
from app.llm.factory import get_fallback_provider, get_llm_provider
from app.llm.fake import FakeLLMProvider
from app.llm.manager import stream_rag_chat
from app.llm.openai_compat import OpenAICompatProvider

__all__ = [
    "CostRecord",
    "FakeLLMProvider",
    "LLMError",
    "LLMProvider",
    "NonRetryableLLMError",
    "OpenAICompatProvider",
    "RetryableLLMError",
    "StreamChunk",
    "aggregate_usage",
    "calculate_cost",
    "estimate_tokens",
    "get_fallback_provider",
    "get_llm_provider",
    "log_cost",
    "stream_rag_chat",
]

