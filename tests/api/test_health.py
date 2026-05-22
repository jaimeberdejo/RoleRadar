"""Tests de GET /health.

Verifica que el endpoint de health check responde correctamente.
"""
from __future__ import annotations


def test_health_ok(api_client):
    """GET /health → 200 con {status: ok}."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
