"""RED guard tests for app.pipeline.rescore_stored (D-09, UI-08).

These tests FAIL until Wave 1 adds rescore_stored() to app/pipeline.py.
They define the exact contract rescore_stored must satisfy:
- Does NOT call _fetch_all (no JSearch fetch).
- Re-scores stored jobs and returns a PipelineResult with scored >= 1.
- Job IDs in storage persist (upsert, not delete).
- Return value has the PipelineResult attribute contract.

Mock strategy mirrors tests/test_pipeline.py:
  - storage: real SQLiteStorage on tmp_path (never touches data/jobs.db)
  - embedder: FakeEmbedder (no torch / BGE-M3 download)
  - _fetch_all: patched to raise AssertionError if called (verifies no-fetch contract)
  - profile.yaml: written to tmp_path

Import pattern: deferred inside each test via _import() so:
  - pytest --collect-only succeeds (no collection errors).
  - Running the tests raises ImportError inside the test body (RED state).
The guard line below satisfies: grep -q "from app.pipeline import rescore_stored"
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import yaml

from app.dedup.embedder import FakeEmbedder
from app.models.schemas import (
    Desglose,
    Job,
    JobScore,
    Recommendation,
    RemoteJob,
    ScoredJob,
)
from app.storage.sqlite import SQLiteStorage


def _import():
    """Deferred import — fails with ImportError when rescore_stored is absent.

    Satisfies: from app.pipeline import rescore_stored
    """
    from app.pipeline import rescore_stored  # noqa: PLC0415
    return rescore_stored


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scored_job(job_id: str = "rescore-test-job-1") -> ScoredJob:
    """Deterministic ScoredJob for rescore tests (mirrors tests/test_pipeline.py)."""
    job = Job(
        id=job_id,
        title="AI Engineer",
        company="RescoreCorp",
        location="Barcelona",
        remote=RemoteJob.remote,
        description="We build AI pipelines.",
        source="jsearch",
    )
    score = JobScore(
        score_total=75,
        recommendation=Recommendation.good_fit,
        desglose=Desglose(
            encaje_puesto=80,
            encaje_skills=75,
            encaje_ubicacion=90,
            encaje_seniority=60,
        ),
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        reasons_for=["Python match", "Remote OK"],
        reasons_against=["Kubernetes gap"],
        matched_skills=["Python"],
        missing_requirements=["Kubernetes"],
        deal_breaker_hit=False,
        deal_breaker_cual=None,
    )
    return ScoredJob(job=job, score=score)


def _write_minimal_profile(tmp_path: Path) -> Path:
    """Write a minimal valid profile.yaml to tmp_path and return its Path."""
    profile_data = {
        "datos_personales": {
            "nombre": "Jaime Berdejo",
            "email": "test@example.com",
            "ubicacion_actual": "Barcelona",
        },
        "preferencias_ubicacion": {
            "pais": "España",
        },
        "preferencia_remoto": {
            "modalidad_ideal": "remote",
        },
        "ranking_puestos": [
            {"titulo": "AI Engineer"},
        ],
        "deal_breakers": [],
        "pesos": {
            "puesto": 0.35,
            "skills": 0.30,
            "ubicacion": 0.20,
            "seniority": 0.15,
        },
    }
    profile_path = tmp_path / "profile.yaml"
    with open(profile_path, "w") as f:
        yaml.dump(profile_data, f)
    return profile_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_rescore_does_not_fetch(tmp_path):
    """rescore_stored must NOT call _fetch_all (D-09: no JSearch fetch).

    Steps:
    1. Seed one ScoredJob in a fresh DB.
    2. Patch _fetch_all to raise AssertionError if called.
    3. Call rescore_stored — must not raise (i.e. _fetch_all was not called).
    4. Assert result.scored >= 1 (at least one job was re-scored).
    """
    rescore_stored = _import()

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([_make_scored_job()])

    profile_path = _write_minimal_profile(tmp_path)
    fake_embedder = FakeEmbedder(
        default_vector=np.array([1, 0, 0, 0], dtype=np.float32)
    )

    with patch("app.pipeline._fetch_all", side_effect=AssertionError("_fetch_all must not be called by rescore_stored")):
        result = rescore_stored(
            storage=storage,
            embedder=fake_embedder,
            profile_path=profile_path,
        )

    assert result.scored >= 1, (
        f"Expected result.scored >= 1 after re-scoring one stored job, got {result.scored}"
    )


def test_rescore_reuses_stored_job_ids(tmp_path):
    """After rescore_stored, get_history still contains the original job id.

    rescore_stored must upsert (not delete and re-insert) so the job id persists.
    """
    rescore_stored = _import()

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    original_job = _make_scored_job("rescore-persist-id-1")
    storage.upsert_scored_jobs([original_job])

    profile_path = _write_minimal_profile(tmp_path)
    fake_embedder = FakeEmbedder(
        default_vector=np.array([1, 0, 0, 0], dtype=np.float32)
    )

    with patch("app.pipeline._fetch_all", side_effect=AssertionError("no fetch")):
        rescore_stored(
            storage=storage,
            embedder=fake_embedder,
            profile_path=profile_path,
        )

    history = storage.get_history()
    ids = [row["id"] for row in history]
    assert "rescore-persist-id-1" in ids, (
        f"Original job id must persist in storage after rescore; got ids={ids}"
    )


def test_rescore_returns_pipeline_result(tmp_path):
    """rescore_stored returns a PipelineResult with 'scored' and 'errors' attributes."""
    rescore_stored = _import()

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()

    profile_path = _write_minimal_profile(tmp_path)
    fake_embedder = FakeEmbedder(
        default_vector=np.array([1, 0, 0, 0], dtype=np.float32)
    )

    with patch("app.pipeline._fetch_all", side_effect=AssertionError("no fetch")):
        result = rescore_stored(
            storage=storage,
            embedder=fake_embedder,
            profile_path=profile_path,
        )

    assert hasattr(result, "scored"), "PipelineResult must have 'scored' attribute"
    assert hasattr(result, "errors"), "PipelineResult must have 'errors' attribute"
