"""Tests for cost calculations, token estimation, and schema validations."""

import json

import pytest
from pydantic import ValidationError

from app.llm.cost import aggregate_usage, calculate_cost, estimate_tokens
from app.schemas import StructuredAnswer


def test_calculate_cost():
    # 1,000,000 input tokens at $1.00/M + 1,000,000 output tokens at $2.00/M = $3.00
    cost = calculate_cost(1_000_000, 1_000_000, 1.0, 2.0)
    assert cost == 3.0

    # 10,000 input tokens at $0.15/M = 0.0015; 5,000 output tokens at $0.60/M = 0.003 -> 0.0045
    cost_small = calculate_cost(10_000, 5_000, 0.15, 0.60)
    assert cost_small == 0.0045

    # Zero prices
    assert calculate_cost(100, 200, 0.0, 0.0) == 0.0


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    # "hello" has 5 characters -> ceil(5/4) = 2 tokens
    assert estimate_tokens("hello") == 2
    # 40 characters -> 10 tokens
    text_40 = "a" * 40
    assert estimate_tokens(text_40) == 10


def test_structured_answer_accepts_valid():
    ans = StructuredAnswer(
        answer="Zephyr uses devicetree bindings for BME280.",
        confidence=0.95,
        sources=["dts/bindings/sensor/bosch,bme280.yaml"],
    )
    assert ans.answer.startswith("Zephyr")
    assert ans.confidence == 0.95
    assert ans.sources == ["dts/bindings/sensor/bosch,bme280.yaml"]


def test_structured_answer_rejects_invalid_confidence():
    # Confidence > 1.0
    with pytest.raises(ValidationError):
        StructuredAnswer(
            answer="Test",
            confidence=1.5,
            sources=[],
        )

    # Confidence < 0.0
    with pytest.raises(ValidationError):
        StructuredAnswer(
            answer="Test",
            confidence=-0.1,
            sources=[],
        )


def test_aggregate_usage_missing_or_empty_log(tmp_path):
    missing_file = tmp_path / "non_existent.jsonl"
    assert aggregate_usage(missing_file) == {}

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("", encoding="utf-8")
    assert aggregate_usage(empty_file) == {}


def test_aggregate_usage_with_records_and_malformed(tmp_path):
    log_file = tmp_path / "cost.jsonl"
    records = [
        # Valid day 1
        json.dumps(
            {
                "provider": "fake",
                "model": "model-a",
                "input_tokens": 100,
                "output_tokens": 50,
                "cost_usd": 0.001,
                "timestamp": "2026-10-14T10:00:00Z",
            }
        ),
        # Corrupted line
        "{ this is invalid json }",
        # Valid day 1 again
        json.dumps(
            {
                "provider": "fake",
                "model": "model-a",
                "input_tokens": 200,
                "output_tokens": 100,
                "cost_usd": 0.002,
                "timestamp": "2026-10-14T15:30:00Z",
            }
        ),
        # Valid day 2
        json.dumps(
            {
                "provider": "openai_compat",
                "model": "model-b",
                "input_tokens": 500,
                "output_tokens": 250,
                "cost_usd": 0.005,
                "timestamp": "2026-10-15T08:00:00Z",
            }
        ),
    ]
    log_file.write_text("\n".join(records) + "\n", encoding="utf-8")

    stats = aggregate_usage(log_file)
    assert "2026-10-14" in stats
    assert stats["2026-10-14"] == {
        "calls": 2,
        "input_tokens": 300,
        "output_tokens": 150,
        "cost_usd": 0.003,
    }

    assert "2026-10-15" in stats
    assert stats["2026-15" if "2026-15" in stats else "2026-10-15"] == {
        "calls": 1,
        "input_tokens": 500,
        "output_tokens": 250,
        "cost_usd": 0.005,
    }
