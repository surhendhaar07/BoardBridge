"""Embedding provider abstraction for BoardBridge RAG ingestion.

Supports FakeEmbedder for fast, deterministic, offline testing, and
LocalEmbedder for CPU inference using sentence-transformers/all-MiniLM-L6-v2.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Protocol


class Embedder(Protocol):
    """Protocol defining the interface for BoardBridge embedding providers."""

    model: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of text strings into normalized vector arrays."""
        ...


class FakeEmbedder:
    """Deterministic, offline pseudo-embedder for CI and automated testing."""

    def __init__(self, dim: int = 384, model: str = "fake") -> None:
        self.dim = dim
        self.model = model

    def _embed_single(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        words = text.strip().split()
        if not words:
            words = ["<empty>"]

        for word in words:
            h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            pos = h % self.dim
            val = ((h >> 8) % 1000) / 500.0 - 1.0
            if val == 0.0:
                val = 0.5
            vec[pos] += val

        # Ensure vector is never all zeros
        if all(v == 0.0 for v in vec):
            vec[0] = 1.0

        # L2 normalization to unit length
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [round(v / norm, 6) for v in vec]
        else:
            vec[0] = 1.0

        return vec

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return deterministic normalized vectors of length self.dim."""
        return [self._embed_single(t) for t in texts]


class LocalEmbedder:
    """Local CPU embedder using sentence-transformers."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        dim: int = 384,
        batch_size: int = 32,
        device: str = "cpu",
    ) -> None:
        self.model = model_name
        self.dim = dim
        self.batch_size = batch_size
        self.device = device

        # Lazy import so CI and tests can run without sentence-transformers/torch
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for LocalEmbedder. "
                "Install with 'pip install -r requirements-embed.txt'."
            ) from exc

        self._model = SentenceTransformer(self.model, device=self.device)
        actual_dim = self._model.get_sentence_embedding_dimension()
        if actual_dim is not None and actual_dim != self.dim:
            raise ValueError(
                f"Embedding model dimension mismatch: expected {self.dim}, "
                f"got {actual_dim} from '{self.model}'."
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Encode texts into normalized 384-dimensional Python float lists."""
        if not texts:
            return []

        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        result: list[list[float]] = embeddings.tolist()
        if result and len(result[0]) != self.dim:
            raise ValueError(f"Output vector dimension mismatch: expected {self.dim}, got {len(result[0])}.")
        return result


def get_embedder(settings: Any = None) -> Embedder:
    """Provider factory returning FakeEmbedder or LocalEmbedder based on configuration."""
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    provider = getattr(settings, "embedding_provider", "fake").lower()
    model = getattr(settings, "embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    dim = getattr(settings, "embedding_dim", 384)

    if provider == "fake":
        return FakeEmbedder(dim=dim, model=model)
    elif provider == "local":
        return LocalEmbedder(model_name=model, dim=dim)
    else:
        raise ValueError(f"Unknown embedding provider '{provider}'. Must be 'fake' or 'local'.")
