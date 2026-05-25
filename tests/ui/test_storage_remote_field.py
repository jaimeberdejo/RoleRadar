"""RED guard test for get_history including the remote field (RESEARCH Pitfall 4, UI-08).

This test FAILS today because get_history() does not include 'remote' in the returned dict
(the remote column IS in the DB, but the dict builder omits it). The test verifies:
- After upserting a ScoredJob with remote=RemoteJob.remote, get_history()[0]["remote"] == "remote".

This guard locks the contract for the get_history fix that Plan 02 must deliver so that
rescore_stored() can reconstruct Job objects with their correct RemoteJob value.

Test uses SQLiteStorage on tmp_path — never touches data/jobs.db.
"""
from __future__ import annotations

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
# Tests
# ---------------------------------------------------------------------------

def test_get_history_includes_remote(tmp_path):
    """get_history must include 'remote' field in the returned dict.

    Steps:
    1. Upsert a ScoredJob with job.remote=RemoteJob.remote.
    2. Call get_history().
    3. Assert rows[0]["remote"] == "remote".

    RED today: get_history dict builder omits the remote key → KeyError.
    GREEN when Plan 02 adds "remote": row["remote"] to the get_history() return dict.
    """
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()

    job = Job(
        id="remote-field-test-job-1",
        title="AI Engineer",
        company="RemoteCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description="Remote AI Engineer role.",
        source="test",
    )
    score = JobScore(
        score_total=80,
        recommendation=Recommendation.good_fit,
        desglose=Desglose(
            encaje_puesto=85,
            encaje_skills=80,
            encaje_ubicacion=95,
            encaje_seniority=65,
        ),
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        reasons_for=["Remote role"],
        reasons_against=[],
        matched_skills=["Python"],
        missing_requirements=[],
        deal_breaker_hit=False,
        deal_breaker_cual=None,
    )
    storage.upsert_scored_jobs([ScoredJob(job=job, score=score)])

    rows = storage.get_history()
    assert rows, "get_history must return at least one row after upsert"
    assert rows[0]["remote"] == "remote", (
        f"get_history row must include 'remote' field with value 'remote'; "
        f"got keys={list(rows[0].keys())}"
    )
