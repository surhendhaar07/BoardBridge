"""Database connection and readiness verification for BoardBridge."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger("boardbridge.db")


def check_database_readiness(database_url: str | None) -> dict[str, Any]:
    """Verify PostgreSQL database readiness.

    Returns:
        {"status": "ready", "database": "not configured"} when DATABASE_URL is not set.
        {"status": "ready", "database": "ok"} when SELECT 1 succeeds.

    Raises:
        HTTPException(503) when database connection or query fails without exposing credentials.
    """
    if not database_url or not database_url.strip():
        return {"status": "ready", "database": "not configured"}

    try:
        import psycopg

        with psycopg.connect(database_url.strip(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                cur.fetchone()
        return {"status": "ready", "database": "ok"}
    except Exception as exc:
        # Log generic error without printing credentials
        logger.warning("Database readiness probe failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Database connection check failed",
        ) from exc
