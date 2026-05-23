"""Tests de los endpoints del router jobs (parte normalize + score).

Cubre:
    - POST /jobs/normalize: happy path (oferta válida → jobs con 1 elemento)
    - POST /jobs/normalize: batch resiliente (1 válida + 1 mal formada → jobs=1, errors=1)
    - POST /jobs/score: sin CVProfile cacheado → 404 con mención a /cv/parse
    - POST /jobs/score: con CVProfile cacheado → 200 con ScoredJob que tiene score_total

Nota: tests de /jobs/process y GET /jobs/history se añaden en Plan 04.
"""
from __future__ import annotations

import pytest

from tests.conftest import EXPECTED_PROFILE


def test_normalize_ok(api_client, sample_arbeitnow_payload):
    """POST /jobs/normalize con una oferta Arbeitnow válida → 200, jobs=1, errors=[]."""
    response = api_client.post(
        "/jobs/normalize",
        json={"source": "arbeitnow", "offers": [sample_arbeitnow_payload]},
    )
    assert response.status_code == 200, f"Esperado 200, obtenido {response.status_code}: {response.text}"
    data = response.json()
    assert "jobs" in data, "La respuesta debe tener el campo 'jobs'"
    assert "errors" in data, "La respuesta debe tener el campo 'errors'"
    assert len(data["jobs"]) == 1, f"Esperado 1 job, obtenido {len(data['jobs'])}"
    assert data["errors"] == [], f"Esperado errors=[], obtenido {data['errors']}"


def test_normalize_batch_resiliente(api_client, sample_arbeitnow_payload, sample_malformed_payload):
    """POST /jobs/normalize con 1 válida + 1 mal formada → jobs=1, errors=1 (API-07/NORM-04)."""
    response = api_client.post(
        "/jobs/normalize",
        json={
            "source": "arbeitnow",
            "offers": [sample_arbeitnow_payload, sample_malformed_payload],
        },
    )
    assert response.status_code == 200, f"Esperado 200, obtenido {response.status_code}: {response.text}"
    data = response.json()
    assert len(data["jobs"]) == 1, f"Esperado 1 job válido, obtenido {len(data['jobs'])}"
    assert len(data["errors"]) == 1, f"Esperado 1 error, obtenido {len(data['errors'])}"
    # El batch no se rompe — la oferta válida sigue en jobs
    assert data["jobs"][0]["title"] == "AI Engineer"


def test_score_sin_cv_profile_404(api_client):
    """POST /jobs/score sin CVProfile cacheado → 404 con detalle que menciona /cv/parse."""
    # api_client NO tiene get_cached_cv_profile sobreescrito → usa el real → 404
    response = api_client.post(
        "/jobs/score",
        json={"jobs": []},
    )
    assert response.status_code == 404, f"Esperado 404, obtenido {response.status_code}: {response.text}"
    detail = response.json().get("detail", "").lower()
    assert "cv/parse" in detail, f"El detalle debe mencionar '/cv/parse', obtenido: {detail!r}"


def test_score_ok(api_client_with_cv, sample_job_remote):
    """POST /jobs/score con CVProfile cacheado → 200, 1 ScoredJob con score_total."""
    response = api_client_with_cv.post(
        "/jobs/score",
        json={"jobs": [sample_job_remote.model_dump()]},
    )
    assert response.status_code == 200, f"Esperado 200, obtenido {response.status_code}: {response.text}"
    data = response.json()
    assert isinstance(data, list), f"La respuesta debe ser una lista, obtenido {type(data)}"
    assert len(data) == 1, f"Esperado 1 ScoredJob, obtenido {len(data)}"
    scored = data[0]
    assert "job" in scored, "ScoredJob debe tener campo 'job'"
    assert "score" in scored, "ScoredJob debe tener campo 'score'"
    assert "score_total" in scored["score"], "JobScore debe tener campo 'score_total'"
    score_total = scored["score"]["score_total"]
    assert 0 <= score_total <= 100, f"score_total debe estar en [0, 100], obtenido {score_total}"


def test_score_batch_resiliente_job_invalido(api_client_with_cv):
    """POST /jobs/score con un job que causa excepción en score_job no tumba el batch."""
    from unittest.mock import patch

    # Parchear score_job para que falle en el primer job
    with patch("app.api.routes.jobs.score_job", side_effect=RuntimeError("error simulado")):
        response = api_client_with_cv.post(
            "/jobs/score",
            json={"jobs": [
                {
                    "id": "job-fail",
                    "title": "Test Job",
                    "company": "TestCo",
                    "location": "Remote",
                    "remote": "remote",
                    "description": "Test",
                    "source": "test",
                }
            ]},
        )
    # El batch es resiliente — no devuelve 500; devuelve lista vacía o parcial
    assert response.status_code == 200, f"Esperado 200 (batch resiliente), obtenido {response.status_code}"
    data = response.json()
    assert isinstance(data, list)
    # El job fallido se omite → lista vacía
    assert len(data) == 0, f"Esperado lista vacía (job fallido omitido), obtenido {len(data)}"
