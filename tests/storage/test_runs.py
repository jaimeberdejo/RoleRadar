"""RED guard tests for SQLiteStorage runs table additions — STORE-05, STORE-07.

These tests FAIL until Wave 1 adds record_run, get_recent_runs, and mark_seen
to SQLiteStorage (and creates the runs table in init_db).

Tests cover:
- STORE-05: record_run writes a row with correct counts; get_recent_runs returns
  rows ordered most-recent-first
- STORE-07: mark_seen sets seen=1 for a job; persists across a new storage
  instance pointing to the same db file (confirms SQLite persistence, not in-memory)

All tests use tmp_path fixtures — never touch data/jobs.db.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone

import pytest

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

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_scored_job(job_id: str = "runs-test-job-1") -> ScoredJob:
    """Deterministic ScoredJob for storage/runs tests."""
    job = Job(
        id=job_id,
        title="AI Engineer",
        company="RunsCorp",
        location="Barcelona",
        remote=RemoteJob.remote,
        description="Test job for runs table.",
        source="test",
    )
    score = JobScore(
        score_total=75,
        recommendation=Recommendation.good_fit,
        desglose=Desglose(
            encaje_puesto=80,
            encaje_skills=75,
            encaje_ubicacion=90,
            encaje_seniority=65,
        ),
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        reasons_for=["Python match"],
        reasons_against=[],
        matched_skills=["Python"],
        missing_requirements=[],
        deal_breaker_hit=False,
        deal_breaker_cual=None,
    )
    return ScoredJob(job=job, score=score)


# ---------------------------------------------------------------------------
# STORE-05: record_run writes correct counts
# ---------------------------------------------------------------------------

def test_record_run_creates_row(tmp_path):
    """record_run inserts a row; get_recent_runs returns it with correct counts."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()

    started = _now_iso()
    finished = _now_iso()
    storage.record_run(
        started_at=started,
        finished_at=finished,
        fetched=10,
        deduped=7,
        scored=5,
        new_seen=3,
        errors=None,
    )

    runs = storage.get_recent_runs(limit=5)

    assert len(runs) == 1, "Expected exactly 1 run row after one record_run call"
    row = runs[0]
    assert row["fetched"] == 10, f"fetched mismatch: {row['fetched']}"
    assert row["deduped"] == 7, f"deduped mismatch: {row['deduped']}"
    assert row["scored"] == 5, f"scored mismatch: {row['scored']}"
    assert row["new_seen"] == 3, f"new_seen mismatch: {row['new_seen']}"


def test_record_run_with_errors(tmp_path):
    """record_run stores errors list; get_recent_runs returns it as non-null."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()

    error_list = ["query 429", "network timeout"]
    storage.record_run(
        started_at=_now_iso(),
        finished_at=_now_iso(),
        fetched=5,
        deduped=3,
        scored=2,
        new_seen=2,
        errors=error_list,
    )

    runs = storage.get_recent_runs(limit=1)
    assert len(runs) == 1

    # errors field must be non-null and contain both error strings
    run_row = runs[0]
    assert run_row.get("errors") is not None, "errors field must be non-null when errors were recorded"

    # Depending on storage implementation: errors may be stored as JSON string
    # or deserialized list. Accept either form.
    errors_value = run_row["errors"]
    if isinstance(errors_value, str):
        import json  # noqa: PLC0415
        errors_value = json.loads(errors_value)
    assert "query 429" in errors_value, "First error message must be present"
    assert "network timeout" in errors_value, "Second error message must be present"


def test_get_recent_runs_ordering(tmp_path):
    """get_recent_runs returns rows ordered most-recent-first; limit is respected."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()

    # Insert 3 runs sequentially (timestamps differ by microseconds at minimum;
    # storage implementation may use insertion order for ordering — either is fine
    # as long as limit=2 returns exactly 2 rows and most-recent is first)
    for i in range(3):
        storage.record_run(
            started_at=_now_iso(),
            finished_at=_now_iso(),
            fetched=i,
            deduped=i,
            scored=i,
            new_seen=i,
            errors=None,
        )

    runs = storage.get_recent_runs(limit=2)

    assert len(runs) == 2, "limit=2 must return exactly 2 rows out of 3"
    # Most recent run was inserted last with fetched=2
    assert runs[0]["fetched"] == 2, "Most recent run (fetched=2) must come first"


# ---------------------------------------------------------------------------
# STORE-07: mark_seen sets flag; persists across storage restart
# ---------------------------------------------------------------------------

def test_mark_seen_sets_flag(tmp_path):
    """mark_seen sets seen=1 for a job in the jobs table.

    Sequence:
    1. Insert a scored job (seen defaults to 0 after upsert).
    2. Verify was_seen() is True (row exists).
    3. Verify the raw 'seen' column is 0 (not yet delivered/marked).
    4. Call mark_seen(job_id).
    5. Verify seen column is now 1.
    """
    db_path = str(tmp_path / "test.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()

    scored_job = _make_scored_job("mark-seen-job-1")
    storage.upsert_scored_jobs([scored_job])

    # was_seen returns True because the row exists
    assert storage.was_seen("mark-seen-job-1") is True

    # Before mark_seen: seen column is 0 (not yet delivered)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT seen FROM jobs WHERE id = ?", ("mark-seen-job-1",)).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == 0, "seen must be 0 before mark_seen() is called"

    # Call mark_seen
    storage.mark_seen("mark-seen-job-1")

    # After mark_seen: seen column is 1
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT seen FROM jobs WHERE id = ?", ("mark-seen-job-1",)).fetchone()
    conn.close()
    assert row[0] == 1, "seen must be 1 after mark_seen() is called"


def test_mark_seen_persists_across_restart(tmp_path):
    """mark_seen persists across a new SQLiteStorage instance (SQLite, not in-memory).

    Creates a new storage instance on the same db file and verifies the seen=1
    flag is still set — confirming the value was written to disk, not just RAM.
    """
    db_path = str(tmp_path / "test.db")
    storage_a = SQLiteStorage(db_path)
    storage_a.init_db()

    scored_job = _make_scored_job("persist-restart-job-1")
    storage_a.upsert_scored_jobs([scored_job])
    storage_a.mark_seen("persist-restart-job-1")

    # Simulate restart: create a brand-new instance pointing to the same file
    storage_b = SQLiteStorage(db_path)
    # No init_db() needed — table already exists

    # Query raw DB via the new instance's connection method
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT seen FROM jobs WHERE id = ?", ("persist-restart-job-1",)
    ).fetchone()
    conn.close()

    assert row is not None, "Job row must exist in the DB after restart"
    assert row[0] == 1, (
        "seen=1 must persist across storage restart (SQLite, not in-memory)"
    )
