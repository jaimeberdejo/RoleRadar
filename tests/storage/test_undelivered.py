"""RED guard tests for SQLiteStorage.get_undelivered_qualifying — D-08, D-09.

These tests FAIL until Wave 1 (plan 09-02) adds get_undelivered_qualifying to
SQLiteStorage. They lock the exact query contract before any implementation exists:

- D-09: new method get_undelivered_qualifying(min_score, recommendations) -> list[ScoredJob]
- D-08: seen/was_seen distinction — seen=1 rows are excluded from digest query
         even though was_seen() still returns True (row exists)
- Results ordered by score_total DESC

All tests use tmp_path + real SQLiteStorage + init_db — never touch data/jobs.db.
Each call to storage.get_undelivered_qualifying will raise AttributeError until
Wave 1 implements it — that is the intended RED state.
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
# Helpers
# ---------------------------------------------------------------------------

def _make_scored_job(
    job_id: str,
    *,
    recommendation: Recommendation = Recommendation.good_fit,
    score_total: int = 82,
) -> ScoredJob:
    """Deterministic ScoredJob for storage/undelivered tests.

    Mirrors the helper shape from tests/storage/test_runs.py.
    """
    job = Job(
        id=job_id,
        title="AI Engineer",
        company="UndeliveredCorp",
        location="Barcelona",
        remote=RemoteJob.remote,
        description="Test job for undelivered query.",
        url=f"https://example.com/apply/{job_id}",
        source="test",
    )
    score = JobScore(
        score_total=score_total,
        recommendation=recommendation,
        desglose=Desglose(
            encaje_puesto=80,
            encaje_skills=75,
            encaje_ubicacion=90,
            encaje_seniority=65,
        ),
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        reasons_for=["Python match", "Remote OK"],
        reasons_against=[],
        matched_skills=["Python"],
        missing_requirements=[],
        deal_breaker_hit=False,
        deal_breaker_cual=None,
    )
    return ScoredJob(job=job, score=score)


# ---------------------------------------------------------------------------
# Test 1: returns ScoredJob objects with deserialized score_json (D-09)
# ---------------------------------------------------------------------------

def test_get_undelivered_qualifying_returns_scoredjob_objects(tmp_path):
    """get_undelivered_qualifying returns a list[ScoredJob] with deserialized score_json.

    Verifies:
    - Result is a list of length 1.
    - result[0] is a ScoredJob instance with .job and .score attributes.
    - result[0].score.reasons_for is populated (proves JobScore.model_validate_json worked).
    """
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("undeliv-obj-1", recommendation=Recommendation.good_fit, score_total=82)
    ])

    result = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])

    assert isinstance(result, list), "result must be a list"
    assert len(result) == 1, f"expected 1 result, got {len(result)}"
    assert isinstance(result[0], ScoredJob), "result[0] must be a ScoredJob instance"
    assert isinstance(result[0].job, Job), "result[0].job must be a Job instance"
    assert isinstance(result[0].score, JobScore), "result[0].score must be a JobScore instance"
    assert len(result[0].score.reasons_for) > 0, (
        "reasons_for must be populated (proves score_json was deserialized via model_validate_json)"
    )


# ---------------------------------------------------------------------------
# Test 2: filters by min_score threshold (D-09)
# ---------------------------------------------------------------------------

def test_get_undelivered_qualifying_filters_threshold(tmp_path):
    """Only jobs with score_total >= min_score are returned."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("thresh-low", recommendation=Recommendation.good_fit, score_total=65),
        _make_scored_job("thresh-high", recommendation=Recommendation.good_fit, score_total=75),
    ])

    result = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])

    assert len(result) == 1, f"expected 1 result above threshold, got {len(result)}"
    assert result[0].job.id == "thresh-high", (
        f"expected thresh-high (score=75), got {result[0].job.id}"
    )


# ---------------------------------------------------------------------------
# Test 3: filters by recommendation (D-09)
# ---------------------------------------------------------------------------

def test_get_undelivered_qualifying_filters_recommendation(tmp_path):
    """Only jobs with recommendation in the provided list are returned."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("rec-maybe", recommendation=Recommendation.maybe, score_total=95),
        _make_scored_job("rec-strong", recommendation=Recommendation.strong_fit, score_total=95),
    ])

    result = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])

    assert len(result) == 1, f"expected 1 result (strong_fit only), got {len(result)}"
    assert result[0].job.id == "rec-strong", (
        f"expected rec-strong (strong_fit), got {result[0].job.id} — "
        "maybe recommendation must be excluded"
    )


# ---------------------------------------------------------------------------
# Test 4: excludes seen=1 jobs (D-08 — seen vs was_seen distinction)
# ---------------------------------------------------------------------------

def test_get_undelivered_qualifying_excludes_seen(tmp_path):
    """Jobs marked seen=1 via mark_seen are excluded from the qualifying query.

    D-08: was_seen() returns True for both seen=0 AND seen=1 rows (existence check).
    get_undelivered_qualifying must filter on seen=0 only, not just row existence.
    """
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("seen-job-1", recommendation=Recommendation.strong_fit, score_total=90)
    ])

    # was_seen returns True (row exists), but seen column is 0
    assert storage.was_seen("seen-job-1") is True, "was_seen must be True (row exists)"

    # Mark as delivered
    storage.mark_seen("seen-job-1")

    # Now the job must be excluded from qualifying query
    result = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])
    assert result == [], (
        "seen=1 job must be excluded from get_undelivered_qualifying "
        "(even though was_seen() returns True)"
    )


# ---------------------------------------------------------------------------
# Test 5: results ordered by score_total DESC (D-09)
# ---------------------------------------------------------------------------

def test_get_undelivered_qualifying_orders_by_score_desc(tmp_path):
    """get_undelivered_qualifying returns results ordered by score_total descending."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("order-low", recommendation=Recommendation.good_fit, score_total=72),
        _make_scored_job("order-high", recommendation=Recommendation.strong_fit, score_total=88),
    ])

    result = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])

    assert len(result) == 2, f"expected 2 results, got {len(result)}"
    assert result[0].score.score_total == 88, (
        f"first result must be highest score (88), got {result[0].score.score_total}"
    )
    assert result[1].score.score_total == 72, (
        f"second result must be lowest score (72), got {result[1].score.score_total}"
    )
