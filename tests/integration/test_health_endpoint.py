"""Integration tests for the /health endpoint.

Tests verify the deep health check shape and status codes under various
dependency states. DB and OpenAI failures cause 503; Redis failure is
degraded (200 with redis=down).

Marked integration (not live) — runs without real Telegram or real OpenAI
by mocking the individual check coroutines.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
class TestHealthEndpoint:
    def test_all_ok_returns_200(self):
        """When all checks pass, /health returns 200 with status=ok."""
        with patch("app.main._check_db", new_callable=AsyncMock) as mock_db, \
             patch("app.main._check_redis", new_callable=AsyncMock) as mock_redis, \
             patch("app.main._check_openai", new_callable=AsyncMock) as mock_openai:

            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["checks"]["db"] == "ok"
        assert body["checks"]["redis"] == "ok"
        assert body["checks"]["openai"] == "ok"

    def test_db_down_returns_503(self):
        """A failing DB check causes 503 with status=degraded."""
        with patch("app.main._check_db", new_callable=AsyncMock, side_effect=Exception("connection refused")), \
             patch("app.main._check_redis", new_callable=AsyncMock), \
             patch("app.main._check_openai", new_callable=AsyncMock):

            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert "down" in body["checks"]["db"]

    def test_redis_down_returns_200_degraded(self):
        """Redis failure alone does NOT cause 503 — degraded mode is acceptable."""
        with patch("app.main._check_db", new_callable=AsyncMock), \
             patch("app.main._check_redis", new_callable=AsyncMock, side_effect=Exception("env var unset")), \
             patch("app.main._check_openai", new_callable=AsyncMock):

            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "down" in body["checks"]["redis"]

    def test_openai_down_returns_503(self):
        """A failing OpenAI check causes 503."""
        with patch("app.main._check_db", new_callable=AsyncMock), \
             patch("app.main._check_redis", new_callable=AsyncMock), \
             patch("app.main._check_openai", new_callable=AsyncMock, side_effect=Exception("timeout")):

            client = TestClient(app)
            resp = client.get("/health")

        assert resp.status_code == 503
        body = resp.json()
        assert body["status"] == "degraded"
        assert "down" in body["checks"]["openai"]

    def test_response_structure(self):
        """Response always contains {status, checks} with db/redis/openai keys."""
        with patch("app.main._check_db", new_callable=AsyncMock), \
             patch("app.main._check_redis", new_callable=AsyncMock), \
             patch("app.main._check_openai", new_callable=AsyncMock):

            client = TestClient(app)
            resp = client.get("/health")

        body = resp.json()
        assert "status" in body
        assert "checks" in body
        assert set(body["checks"].keys()) == {"db", "redis", "openai"}
