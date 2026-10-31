"""Tests for /health liveness and /ready database readiness probe."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


def test_ready_when_database_not_configured():
    def override_settings():
        return Settings(database_url=None)

    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            r = client.get("/ready")
            assert r.status_code == 200
            assert r.json() == {"status": "ready", "database": "not configured"}
    finally:
        app.dependency_overrides.clear()


def test_ready_when_database_connected():
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (1,)
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn

    def override_settings():
        return Settings(database_url="postgresql://app:secret@db:5432/rag")

    app.dependency_overrides[get_settings] = override_settings
    try:
        with patch("psycopg.connect", return_value=mock_conn):
            with TestClient(app) as client:
                r = client.get("/ready")
                assert r.status_code == 200
                assert r.json() == {"status": "ready", "database": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_ready_when_database_connection_fails():
    import psycopg

    def override_settings():
        return Settings(database_url="postgresql://app:secret@db:5432/rag")

    app.dependency_overrides[get_settings] = override_settings
    try:
        with patch("psycopg.connect", side_effect=psycopg.OperationalError("Connection refused")):
            with TestClient(app) as client:
                r = client.get("/ready")
                assert r.status_code == 503
                # Verify safe error message without exposing credentials
                assert r.json() == {"detail": "Database connection check failed"}
                assert "secret" not in r.text
    finally:
        app.dependency_overrides.clear()


def test_health_still_returns_200_when_database_unavailable():
    def override_settings():
        return Settings(
            app_name="BoardBridge",
            environment="production",
            database_url="postgresql://invalid_host:5432/rag",
        )

    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as client:
            # /health must remain an independent lightweight liveness probe
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json() == {"status": "ok", "app": "BoardBridge", "environment": "production"}
    finally:
        app.dependency_overrides.clear()
