from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "BoardBridge"
    environment: str = "local"  # local | ci | production

    # Database configuration (PostgreSQL / pgvector)
    database_url: str | None = None

    # Primary LLM provider configuration
    llm_provider: str = "fake"  # fake | openai | openai_compat
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    llm_model: str = "llama3.1:8b"

    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 3
    llm_backoff_base_seconds: float = 0.5

    # Fallback LLM configuration
    llm_fallback_model: str | None = None
    llm_fallback_base_url: str | None = None
    llm_fallback_api_key: str | None = None

    # Pricing in USD per million tokens
    price_input_per_million: float = 0.0
    price_output_per_million: float = 0.0

    # Cost logging path
    cost_log_path: str = "logs/cost.jsonl"

    # Embedding provider configuration
    embedding_provider: str = "fake"  # fake | local
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384


@lru_cache
def get_settings() -> Settings:
    return Settings()
