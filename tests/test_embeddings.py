"""Unit tests for BoardBridge embedding providers and factory."""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.rag.embeddings import FakeEmbedder, LocalEmbedder, get_embedder


def test_fake_embedder_returns_configured_dimension():
    embedder_384 = FakeEmbedder(dim=384)
    res = embedder_384.embed(["Zephyr RTOS GPIO driver"])
    assert len(res) == 1
    assert len(res[0]) == 384

    embedder_128 = FakeEmbedder(dim=128)
    res_128 = embedder_128.embed(["Zephyr RTOS GPIO driver"])
    assert len(res_128[0]) == 128


def test_fake_embedder_is_deterministic():
    embedder = FakeEmbedder(dim=384)
    text = "CONFIG_SENSOR=y\nCONFIG_BME280=y"

    vec1 = embedder.embed([text])[0]
    vec2 = embedder.embed([text])[0]
    assert vec1 == vec2


def test_fake_embedder_returns_normalized_vectors():
    embedder = FakeEmbedder(dim=384)
    texts = [
        "Normal firmware text",
        "SingleWord",
        "A slightly longer sentence detailing the devicetree bindings and hardware configuration.",
    ]
    vectors = embedder.embed(texts)

    for v in vectors:
        norm = math.sqrt(sum(x * x for x in v))
        assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_fake_embedder_empty_input_not_zero_vector():
    embedder = FakeEmbedder(dim=384)
    empty_vec = embedder.embed([""])[0]
    assert len(empty_vec) == 384
    assert not all(x == 0.0 for x in empty_vec)
    norm = math.sqrt(sum(x * x for x in empty_vec))
    assert math.isclose(norm, 1.0, rel_tol=1e-3)


def test_factory_selects_fake_provider():
    settings = Settings(embedding_provider="fake", embedding_dim=384)
    embedder = get_embedder(settings)
    assert isinstance(embedder, FakeEmbedder)
    assert embedder.dim == 384
    assert embedder.model == "sentence-transformers/all-MiniLM-L6-v2"


def test_factory_unknown_provider_raises_error():
    settings = Settings(embedding_provider="unknown_provider")
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        get_embedder(settings)


def test_local_embedder_dimension_validation_mismatch():
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = 512

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        with pytest.raises(ValueError, match="dimension mismatch"):
            LocalEmbedder(
                model_name="dummy_model",
                dim=384,  # expects 384, but mock returns 512
            )
