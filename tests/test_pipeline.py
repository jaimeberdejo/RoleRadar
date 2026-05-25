"""RED guard tests for app/pipeline.py — SCHED-03, QA-06.

These tests FAIL until Wave 2 creates app/pipeline.py.
They define the exact expected behaviour of run_pipeline():
- Import cleanliness: no streamlit or apscheduler pulled in at module level (QA-06)
- Returns a PipelineResult with correct attribute contract
- Dedup-against-stored: a job already in DB is not re-scored or re-counted (QA-06 / SC4)
- Partial fetch error does not raise — errors accumulate in result.errors (SCHED-03)
- A runs row is written after each pipeline invocation (STORE-05)

Mock strategy:
- storage: real SQLiteStorage on tmp_path (isolated; no data/jobs.db touched)
- embedder: FakeEmbedder (no torch / BGE-M3 download)
- fetch: monkeypatch via unittest.mock.patch on app.pipeline._fetch_all
- LLM: not called (fetch returns [] or already-stored job skips scoring)
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scored_job(job_id: str = "pipeline-test-job-1") -> ScoredJob:
    """Deterministic ScoredJob for pipeline tests."""
    job = Job(
        id=job_id,
        title="AI Engineer",
        company="PipelineCorp",
        location="Barcelona",
        remote=RemoteJob.remote,
        description="We build AI pipelines.",
        source="jsearch",
    )
    score = JobScore(
        score_total=82,
        recommendation=Recommendation.good_fit,
        desglose=Desglose(
            encaje_puesto=88,
            encaje_skills=80,
            encaje_ubicacion=95,
            encaje_seniority=72,
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


# ---------------------------------------------------------------------------
# QA-06 success criterion 5: no streamlit / apscheduler import at module level
# ---------------------------------------------------------------------------

def test_pipeline_no_streamlit_apscheduler():
    """Importing app.pipeline must not pull streamlit or apscheduler into sys.modules.

    Ensures the shared pipeline function is importable from any Python context
    (worker, test, future UI button) without heavyweight scheduler or UI deps.
    """
    # Scrub any leftover streamlit / apscheduler state
    for mod in list(sys.modules.keys()):
        if "streamlit" in mod or "apscheduler" in mod:
            del sys.modules[mod]

    import app.pipeline  # noqa: F401

    assert "streamlit" not in sys.modules, (
        "pipeline.py must not import streamlit at module level"
    )
    assert "apscheduler" not in sys.modules, (
        "pipeline.py must not import apscheduler at module level"
    )


# ---------------------------------------------------------------------------
# Basic PipelineResult contract
# ---------------------------------------------------------------------------

def test_run_pipeline_returns_pipeline_result(tmp_path):
    """run_pipeline returns a PipelineResult with correct attributes on empty fetch."""
    from app.pipeline import run_pipeline  # noqa: PLC0415

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    fake_embedder = FakeEmbedder()

    with patch("app.pipeline._fetch_all", return_value=[]):
        result = run_pipeline(storage=storage, embedder=fake_embedder)

    assert hasattr(result, "fetched"), "PipelineResult must have 'fetched'"
    assert hasattr(result, "deduped"), "PipelineResult must have 'deduped'"
    assert hasattr(result, "scored"), "PipelineResult must have 'scored'"
    assert hasattr(result, "new_seen"), "PipelineResult must have 'new_seen'"
    assert hasattr(result, "errors"), "PipelineResult must have 'errors'"
    assert hasattr(result, "scored_jobs"), "PipelineResult must have 'scored_jobs'"
    assert result.fetched == 0, "Empty fetch → fetched == 0"


# ---------------------------------------------------------------------------
# QA-06 / SC4: dedup-against-stored
# ---------------------------------------------------------------------------

def test_run_pipeline_dedup_against_stored(tmp_path):
    """A job already in the DB must not be re-scored or re-counted as new.

    Steps:
    1. Pre-populate DB with one scored job.
    2. Patch _fetch_all to return a raw dict whose stable ID matches that job.
    3. Call run_pipeline.
    4. Assert new_seen == 0 (not a new insertion) and scored == 0 (not re-scored).
    """
    from app.pipeline import run_pipeline  # noqa: PLC0415

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    fake_embedder = FakeEmbedder()

    # Pre-populate with a job whose id matches the SHA-256 stable id that the
    # raw dict below will produce after normalization via jsearch_mapper.
    # stable_job_id("PipelineCorp", "AI Engineer", "Barcelona") = this hash.
    _EXISTING_ID = "c9b290b3eea4a66298d2beab5757ce9b5e461325a2cd50ae5c69dddf006bef9f"
    existing = _make_scored_job(_EXISTING_ID)
    storage.upsert_scored_jobs([existing])

    # Build a raw JSearch-like dict that normalizes to the same stable job id.
    # We rely on the pipeline using was_seen(job.id) to detect duplicates.
    # The stable id is SHA-256(company|title|location) — match exactly.
    raw_already_stored = {
        "job_title": "AI Engineer",
        "employer_name": "PipelineCorp",
        "job_description": "We build AI pipelines.",
        "job_apply_link": "https://pipelinecorp.com/jobs/1",
        "job_is_remote": True,
        "job_location": "Barcelona",
        "job_city": None,
        "job_state": None,
        "job_country": None,
        "job_posted_at_datetime_utc": None,
        "job_posted_at_timestamp": None,
        "job_min_salary": None,
        "job_max_salary": None,
        "job_salary_currency": None,
        "job_salary_period": None,
    }

    with patch("app.pipeline._fetch_all", return_value=[raw_already_stored]):
        result = run_pipeline(storage=storage, embedder=fake_embedder)

    assert result.new_seen == 0, (
        "Already-stored job must not be counted as new (new_seen must be 0)"
    )
    assert result.scored == 0, (
        "Already-stored job must not be re-scored (scored must be 0)"
    )


# ---------------------------------------------------------------------------
# SCHED-03: partial fetch error does not raise
# ---------------------------------------------------------------------------

def test_run_pipeline_partial_fetch_error_does_not_raise(tmp_path):
    """run_pipeline completes without raising even when the fetch accumulates errors.

    Simulates a fetch that returns no jobs and a non-empty errors list
    (e.g. a 429 on one of the queries). The pipeline must not re-raise.
    """
    from app.pipeline import run_pipeline  # noqa: PLC0415

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    fake_embedder = FakeEmbedder()

    # Simulate _fetch_all raising internally for one query by patching to raise
    with patch("app.pipeline._fetch_all", side_effect=Exception("query error")):
        # run_pipeline must catch this and NOT re-raise
        result = run_pipeline(storage=storage, embedder=fake_embedder)

    assert result is not None, "run_pipeline must return a result even on fetch error"
    assert len(result.errors) > 0, "Fetch errors must be recorded in result.errors"


# ---------------------------------------------------------------------------
# STORE-05: run row written after pipeline execution
# ---------------------------------------------------------------------------

def test_run_pipeline_creates_run_row(tmp_path):
    """After run_pipeline, get_recent_runs returns at least one row with count fields."""
    from app.pipeline import run_pipeline  # noqa: PLC0415

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    fake_embedder = FakeEmbedder()

    with patch("app.pipeline._fetch_all", return_value=[]):
        run_pipeline(storage=storage, embedder=fake_embedder)

    runs = storage.get_recent_runs(limit=1)

    assert len(runs) == 1, "run_pipeline must write a row to the runs table"
    run_row = runs[0]
    assert "fetched" in run_row, "runs row must have 'fetched' key"
    assert "deduped" in run_row, "runs row must have 'deduped' key"
    assert "scored" in run_row, "runs row must have 'scored' key"
    assert "new_seen" in run_row, "runs row must have 'new_seen' key"
