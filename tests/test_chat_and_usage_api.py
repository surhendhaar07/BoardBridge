"""Tests for /chat (SSE streaming) and /usage endpoints."""

import json

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_chat_streams_sse_response(tmp_path):
    cost_log = tmp_path / "cost.jsonl"

    def override_settings():
        return Settings(
            app_name="BoardBridge",
            environment="test",
            llm_provider="fake",
            cost_log_path=str(cost_log),
        )

    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            response = client.post(
                "/chat",
                json={"message": "How to connect BME280 over I2C in Zephyr?"},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            content = response.text
            # Verify SSE event lines
            assert "data: " in content
            assert '"delta":' in content
            assert "event: done" in content
            assert '"usage":' in content
            assert '"cost_usd":' in content

            # Verify cost log was created
            assert cost_log.is_file()
            lines = cost_log.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) >= 1
    finally:
        app.dependency_overrides.clear()


def test_chat_handles_invalid_request():
    with TestClient(app) as client:
        # Empty body
        r1 = client.post("/chat", json={})
        assert r1.status_code == 422

        # Empty string
        r2 = client.post("/chat", json={"message": "   "})
        assert r2.status_code == 422


def test_usage_handles_missing_and_empty_log(tmp_path):
    missing_log = tmp_path / "absent.jsonl"

    def override_settings():
        return Settings(cost_log_path=str(missing_log))

    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            res = client.get("/usage")
            assert res.status_code == 200
            assert res.json() == {}
    finally:
        app.dependency_overrides.clear()


def test_usage_aggregates_jsonl_log(tmp_path):
    cost_log = tmp_path / "cost.jsonl"
    records = [
        {
            "provider": "fake",
            "model": "model-1",
            "input_tokens": 1000,
            "output_tokens": 500,
            "cost_usd": 0.0015,
            "timestamp": "2026-10-14T12:00:00Z",
        },
        {
            "provider": "fake",
            "model": "model-1",
            "input_tokens": 2000,
            "output_tokens": 1000,
            "cost_usd": 0.0030,
            "timestamp": "2026-10-14T18:00:00Z",
        },
    ]
    cost_log.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

    def override_settings():
        return Settings(cost_log_path=str(cost_log))

    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            res = client.get("/usage")
            assert res.status_code == 200
            data = res.json()
            assert "2026-10-14" in data
            assert data["2026-10-14"] == {
                "calls": 2,
                "input_tokens": 3000,
                "output_tokens": 1500,
                "cost_usd": 0.0045,
            }
    finally:
        app.dependency_overrides.clear()
