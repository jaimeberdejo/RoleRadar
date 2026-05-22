"""Fixtures de tests para la capa API FastAPI.

Expone:
    FakeStorage     — storage en memoria: funcional (not no-op). upsert_scored_jobs
                      puebla _seen y _jobs; was_seen lee _seen; get_history retorna
                      _jobs. Permite tests de ya_visto e historial sin SQLite.
    api_client      — TestClient con dependency_overrides completos + reset (Pitfall 7).
    api_client_with_cv — api_client + CVProfile cacheado en tmp_path.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import (
    get_cached_cv_profile,
    get_cv_llm_client,
    get_embedder,
    get_scoring_llm_client,
    get_storage,
)
from app.api.main import app
from tests.conftest import EXPECTED_ASSESSMENT, EXPECTED_PROFILE, make_scoring_client


class FakeStorage:
    """Storage en memoria para tests — sin disco, sin SQLite.

    Implementación FUNCIONAL (no no-op): upsert_scored_jobs puebla _seen +
    _jobs para que los tests de ya_visto e historial funcionen sin red
    (04-PLAN-CHECK-RESOLUTIONS.md B1+B3).
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._jobs: list[dict] = []

    def init_db(self) -> None:
        pass

    def upsert_scored_jobs(self, scored: list) -> None:
        """Persiste en memoria: añade ids a _seen y dicts a _jobs."""
        for item in scored:
            job_id = item.job.id
            self._seen.add(job_id)
            self._jobs.append({
                "id": job_id,
                "title": item.job.title,
                "company": item.job.company,
                "score_total": item.score.score_total,
                "recommendation": item.score.recommendation.value,
                "first_seen": "2026-05-22T00:00:00+00:00",
                "last_seen": "2026-05-22T00:00:00+00:00",
                "score": item.score.model_dump(),
            })

    def was_seen(self, job_id: str) -> bool:
        return job_id in self._seen

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._jobs[offset : offset + limit]


@pytest.fixture
def api_client():
    """TestClient con todos los Depends sobreescritos — cero red, cero torch.

    Sobreescribe:
    - get_storage       → FakeStorage (in-memory, funcional)
    - get_scoring_llm_client → MagicMock con EXPECTED_ASSESSMENT
    - get_cv_llm_client → MagicMock con EXPECTED_PROFILE
    - get_embedder      → FakeEmbedder (import deferido, anti-torch)

    Teardown: app.dependency_overrides = {} (Pitfall 7 — evita polución entre tests).
    """
    fake_store = FakeStorage()
    mock_scoring = make_scoring_client(EXPECTED_ASSESSMENT)
    mock_cv = MagicMock()
    mock_cv.messages.create.return_value = EXPECTED_PROFILE

    # Import deferido — evita arrastrar torch/sentence-transformers en collection time
    import numpy as np  # noqa: PLC0415
    from app.dedup.embedder import FakeEmbedder  # noqa: PLC0415

    fake_embedder = FakeEmbedder(
        default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    )

    app.dependency_overrides[get_storage] = lambda: fake_store
    app.dependency_overrides[get_scoring_llm_client] = lambda: mock_scoring
    app.dependency_overrides[get_cv_llm_client] = lambda: mock_cv
    app.dependency_overrides[get_embedder] = lambda: fake_embedder

    with TestClient(app) as client:
        yield client

    app.dependency_overrides = {}  # CRITICO: reset tras yield — previene contaminación


@pytest.fixture
def api_client_with_cv(api_client, tmp_path, monkeypatch):
    """api_client con CVProfile cacheado en tmp_path.

    Crea _current + {hash}.json en tmp_path y sobreescribe get_cached_cv_profile
    para devolver EXPECTED_PROFILE directamente. Necesario para endpoints que
    llaman a Depends(get_cached_cv_profile): /jobs/score, /jobs/process.
    """
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    fake_hash = "a" * 64
    (tmp_path / "_current").write_text(fake_hash, encoding="utf-8")
    (tmp_path / f"{fake_hash}.json").write_text(
        EXPECTED_PROFILE.model_dump_json(), encoding="utf-8"
    )
    # Override directo para mayor determinismo — no depende del filesystem en tests
    app.dependency_overrides[get_cached_cv_profile] = lambda: EXPECTED_PROFILE
    yield api_client
    app.dependency_overrides = {}  # reset tras yield
