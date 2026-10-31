"""Request and response models for BoardBridge."""
from pydantic import BaseModel, Field, model_validator


class StructuredAnswer(BaseModel):
    answer: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False


class DoneEventData(BaseModel):
    usage: TokenUsage
    cost_usd: float
    sources: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    message: str | None = None
    question: str | None = None

    @model_validator(mode="after")
    def validate_query(self) -> "ChatRequest":
        query = (self.message or self.question or "").strip()
        if not query:
            raise ValueError("Either 'message' or 'question' must be provided and non-empty.")
        return self

    @property
    def query(self) -> str:
        return (self.message or self.question or "").strip()


class DailyUsage(BaseModel):
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
