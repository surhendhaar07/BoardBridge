"""Factory functions for instantiating LLM providers."""
from __future__ import annotations

from app.config import Settings, get_settings
from app.llm.base import LLMProvider
from app.llm.fake import FakeLLMProvider
from app.llm.openai_compat import OpenAICompatProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Create the primary LLM provider based on application configuration."""
    cfg = settings or get_settings()
    provider_type = cfg.llm_provider.lower().strip()

    if provider_type == "fake":
        return FakeLLMProvider(default_model=cfg.llm_model)

    if provider_type in {"openai", "openai_compat"}:
        return OpenAICompatProvider(
            base_url=cfg.llm_base_url,
            api_key=cfg.llm_api_key,
            default_model=cfg.llm_model,
            timeout_seconds=cfg.llm_timeout_seconds,
            max_retries=cfg.llm_max_retries,
            backoff_base_seconds=cfg.llm_backoff_base_seconds,
        )

    raise ValueError(f"Unsupported LLM provider '{cfg.llm_provider}'. Expected 'fake' or 'openai_compat'.")


def get_fallback_provider(settings: Settings | None = None) -> LLMProvider | None:
    """Create the fallback LLM provider if configured, otherwise None."""
    cfg = settings or get_settings()
    fallback_model = (cfg.llm_fallback_model or "").strip()
    if not fallback_model:
        return None

    provider_type = cfg.llm_provider.lower().strip()
    if provider_type == "fake":
        return FakeLLMProvider(default_model=fallback_model)

    base_url = cfg.llm_fallback_base_url or cfg.llm_base_url
    api_key = cfg.llm_fallback_api_key if cfg.llm_fallback_api_key is not None else cfg.llm_api_key

    return OpenAICompatProvider(
        base_url=base_url,
        api_key=api_key,
        default_model=fallback_model,
        timeout_seconds=cfg.llm_timeout_seconds,
        max_retries=cfg.llm_max_retries,
        backoff_base_seconds=cfg.llm_backoff_base_seconds,
    )

