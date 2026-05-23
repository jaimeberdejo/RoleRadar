"""Tests e2e de POST /jobs/process y GET /jobs/history.

Cubre:
- Orden por score_total DESC (API-04)
- ya_visto=False en primer run, ya_visto=True en segundo run (STORE-03)
- Persistencia: history no vacío tras process (API-06)
- Oferta mal formada → errors, no 500 (API-07/NORM-04)
- Sin CVProfile cacheado → 404 con guía a /cv/parse
- Paginación de /jobs/history

Todos los tests: cero red, cero torch (FakeEmbedder + scoring mockeado).
"""
from __future__ import annotations

import pytest

from app.api.deps import get_storage
from app.api.main import app


# ─── Payloads de ejemplo (arbeitnow-compatible) ──────────────────────────────

def _make_offer(slug: str, title: str, company: str) -> dict:
    """Construye un payload tipo Arbeitnow válido."""
    return {
        "slug": slug,
        "company_name": company,
        "title": title,
        "description": f"<p>Looking for a {title} at {company}.</p>",
        "remote": True,
        "url": f"https://arbeitnow.com/jobs/{slug}",
        "tags": [],
        "job_types": [],
        "location": "Remote",
        "created_at": 1716350400,
    }


OFFER_AI = _make_offer("ai-engineer-techcorp-01", "AI Engineer", "TechCorp GmbH")
OFFER_ML = _make_offer("ml-engineer-datalab-02", "ML Engineer", "DataLab Inc")


def _process_body(*offers: dict, source: str = "arbeitnow") -> dict:
    """Construye el body de /jobs/process con una source."""
    return {"sources": [{"source": source, "offers": list(offers)}]}


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_process_ordena_por_score_total(api_client_with_cv):
    """Los resultados de /jobs/process se devuelven ordenados por score_total DESC."""
    body = _process_body(OFFER_AI, OFFER_ML)
    response = api_client_with_cv.post("/jobs/process", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    results = data["results"]
    assert len(results) >= 1
    scores = [r["score"]["score_total"] for r in results]
    assert scores == sorted(scores, reverse=True), f"No ordenado desc: {scores}"


def test_process_ya_visto_primer_run_false(api_client_with_cv):
    """En el primer run, ya_visto debe ser False para todas las ofertas."""
    body = _process_body(OFFER_AI)
    response = api_client_with_cv.post("/jobs/process", json=body)
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) >= 1
    assert results[0]["ya_visto"] is False, "Primera vez → ya_visto debe ser False"


def test_process_ya_visto_segundo_run(api_client_with_cv):
    """STORE-03: mismo job en segundo run → ya_visto=True.

    FakeStorage es funcional: upsert_scored_jobs añade a _seen;
    was_seen lee _seen. Usar mismo api_client_with_cv (mismo FakeStorage).
    """
    body = _process_body(OFFER_AI)
    # Primer run
    r1 = api_client_with_cv.post("/jobs/process", json=body)
    assert r1.status_code == 200, r1.text
    assert r1.json()["results"][0]["ya_visto"] is False

    # Segundo run — misma oferta, mismo id → ya_visto=True
    r2 = api_client_with_cv.post("/jobs/process", json=body)
    assert r2.status_code == 200, r2.text
    results2 = r2.json()["results"]
    assert len(results2) >= 1
    assert results2[0]["ya_visto"] is True, (
        "Segundo run con misma oferta → ya_visto debe ser True"
    )


def test_process_persiste_en_history(api_client_with_cv):
    """Tras un POST /jobs/process, GET /jobs/history devuelve >= 1 oferta."""
    body = _process_body(OFFER_AI)
    proc = api_client_with_cv.post("/jobs/process", json=body)
    assert proc.status_code == 200, proc.text

    hist = api_client_with_cv.get("/jobs/history")
    assert hist.status_code == 200, hist.text
    items = hist.json()
    assert len(items) >= 1, "Historial vacío tras procesar una oferta"
    # Cada item tiene score_total y first_seen
    item = items[0]
    assert "score_total" in item
    assert "first_seen" in item


def test_process_oferta_malformada_va_a_errors(api_client_with_cv, sample_malformed_payload):
    """Una oferta mal formada va a errors, no tumba el batch (API-07/NORM-04)."""
    body = {
        "sources": [
            {
                "source": "arbeitnow",
                "offers": [OFFER_AI, sample_malformed_payload],
            }
        ]
    }
    response = api_client_with_cv.post("/jobs/process", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["results"]) >= 1, "Al menos la oferta válida debe estar en results"
    assert len(data["errors"]) >= 1, "La oferta mal formada debe aparecer en errors"


def test_process_sin_cv_profile_404(api_client):
    """Sin CVProfile cacheado, /jobs/process responde 404 con guía a /cv/parse."""
    body = _process_body(OFFER_AI)
    response = api_client.post("/jobs/process", json=body)
    assert response.status_code == 404, response.text
    detail = response.json().get("detail", "").lower()
    assert "cv/parse" in detail or "/cv/parse" in detail, (
        f"El 404 debe mencionar /cv/parse, got: {detail!r}"
    )


def test_history_paginacion(api_client_with_cv):
    """GET /jobs/history?limit=1&offset=0 devuelve exactamente 1 resultado."""
    # Procesar 2 ofertas distintas
    body = _process_body(OFFER_AI, OFFER_ML)
    proc = api_client_with_cv.post("/jobs/process", json=body)
    assert proc.status_code == 200, proc.text

    # Pedir solo 1
    hist = api_client_with_cv.get("/jobs/history?limit=1&offset=0")
    assert hist.status_code == 200, hist.text
    items = hist.json()
    assert len(items) == 1, f"Paginación limit=1 debe devolver 1 item, got {len(items)}"
