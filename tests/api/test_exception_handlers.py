"""Tests de exception handlers de FastAPI para BuscadorDeEmpleo (OBS-03).

Verifica que cada excepción de capa que propaga hasta el router sea convertida
en un JSONResponse limpio con código HTTP correcto y envelope {"error": {...}}.
También verifica que el handler genérico NO filtra stack trace al cliente
(anti information disclosure — T-05-03).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import get_cached_cv_profile, get_storage
from app.errors import CVParseError, NormalizationError, ScoringError, StorageError


# ─── Helpers para inyectar excepciones ──────────────────────────────────────


def _raise_cv_parse_error():
    """Dep override que lanza CVParseError."""
    raise CVParseError("fallo al parsear el CV")


def _raise_normalization_error():
    """Dep override que lanza NormalizationError."""
    raise NormalizationError("fallo al normalizar la oferta")


def _raise_scoring_error():
    """Dep override que lanza ScoringError."""
    raise ScoringError("fallo al puntuar la oferta")


def _raise_storage_error():
    """Dep override que lanza StorageError."""
    raise StorageError("fallo al acceder al storage")


def _raise_generic_error():
    """Dep override que lanza una excepción genérica no controlada."""
    raise RuntimeError("internal secret path /usr/local/lib/python/error.py line 42")


# ─── Tests de handlers específicos ──────────────────────────────────────────


def test_cv_parse_error_returns_422():
    """CVParseError propagada al router → JSONResponse 422 con envelope limpio.

    Sobreescribimos get_cached_cv_profile en /jobs/score para inyectar CVParseError
    (lo que importa es que el handler la capture, independientemente del endpoint).
    """
    app.dependency_overrides[get_cached_cv_profile] = _raise_cv_parse_error
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/jobs/score", json={"jobs": []})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["type"] == "CVParseError"
        assert "message" in body["error"]
        assert body["error"]["message"] != ""
    finally:
        app.dependency_overrides = {}


def test_normalization_error_returns_422():
    """NormalizationError propagada al router → JSONResponse 422 con envelope limpio."""
    # NormalizationError se puede disparar desde /jobs/normalize — sobreescribir get_storage
    # no es directo, pero podemos usar una ruta que dependa de get_cached_cv_profile
    # para simular un Depends que lanza NormalizationError.
    # Estrategia: sobreescribir get_cached_cv_profile (usado en /jobs/score) para lanzar NormalizationError.
    app.dependency_overrides[get_cached_cv_profile] = _raise_normalization_error
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/jobs/score", json={"jobs": []})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["type"] == "NormalizationError"
        assert "message" in body["error"]
    finally:
        app.dependency_overrides = {}


def test_scoring_error_returns_422():
    """ScoringError propagada al router → JSONResponse 422 con envelope limpio."""
    app.dependency_overrides[get_cached_cv_profile] = _raise_scoring_error
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.post("/jobs/score", json={"jobs": []})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert body["error"]["type"] == "ScoringError"
        assert "message" in body["error"]
    finally:
        app.dependency_overrides = {}


def test_storage_error_returns_503():
    """StorageError propagada al router → JSONResponse 503 con envelope limpio."""
    app.dependency_overrides[get_storage] = _raise_storage_error
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/jobs/history")
        assert resp.status_code == 503
        body = resp.json()
        assert "error" in body
        assert body["error"]["type"] == "StorageError"
        assert "message" in body["error"]
    finally:
        app.dependency_overrides = {}


def test_generic_exception_returns_500_without_stack_trace():
    """Exception genérica no controlada → 500 con 'Internal server error'; sin stack trace ni paths.

    Verifica el invariante de seguridad T-05-03: el handler genérico NO filtra el
    mensaje real de la excepción ni rutas de ficheros al cliente (anti information disclosure).
    """
    app.dependency_overrides[get_storage] = _raise_generic_error
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/jobs/history")
        assert resp.status_code == 500
        body = resp.json()
        assert "error" in body
        # El mensaje debe ser el genérico — NO el str de la excepción
        assert body["error"]["message"] == "Internal server error"
        # Anti-leak: el str real con el path interno NO debe aparecer en el body
        body_str = resp.text
        assert "internal secret path" not in body_str
        assert "/usr/local/lib" not in body_str
        assert "line 42" not in body_str
    finally:
        app.dependency_overrides = {}


def test_batch_resilience_not_broken_by_handlers(api_client_with_cv):
    """Regresión batch: /jobs/process con oferta mal formada → 200 + errors[] no vacío.

    Los exception handlers NO deben romper la resiliencia de batch existente.
    Una oferta mal formada (company_name=int, title=None) provoca TypeError en el
    mapper → va a errors[], no produce 500.
    """
    payload = {
        "sources": [
            {
                "source": "generic",
                "offers": [
                    {"company_name": 12345, "title": None}  # int en lugar de str → TypeError
                ]
            }
        ]
    }
    resp = api_client_with_cv.post("/jobs/process", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "errors" in body
    assert len(body["errors"]) > 0  # la oferta mal formada va a errors[]
