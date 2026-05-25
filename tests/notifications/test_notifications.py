"""RED guard tests for app/notifications — NOTIF-01, NOTIF-02, NOTIF-03, D-02, D-06, D-11, D-14.

These tests FAIL until Waves 1-2 build app.notifications and the storage query
(SQLiteStorage.get_undelivered_qualifying). They lock the exact contracts before
any implementation exists:
- Digest rendering: title/company/score/recommendation/reasons/URL per offer (D-05)
- Telegram channel sends full digest and marks seen (NOTIF-01)
- Email channel sends full digest and marks seen (NOTIF-01)
- Channel resolution: auto-detect telegram vs email vs None from env vars (NOTIF-02)
- Silent skip when no channel configured — nothing marked seen (NOTIF-02 / D-10)
- Delivery failure leaves seen=0, job reappears in next run (NOTIF-03 / D-10)
- Delivery success marks seen=1, absent from next digest (NOTIF-03 / SC4)
- Qualifying filter: only strong_fit/good_fit above threshold (NOTIF-03)
- Import cleanliness: no streamlit / apscheduler (D-02)
- Chunking at 4096-char offer boundaries (D-06)
- runs table has channel + notified columns (D-14)
- Multi-chunk partial failure: later chunk failure does NOT un-deliver earlier chunks (D-11)

All imports of app.notifications.* go inside test functions (# noqa: PLC0415) because
app.notifications does not exist yet — module-level import would break collection.
All secrets set via monkeypatch.setenv — never hardcoded.
"""
from __future__ import annotations

import sqlite3
import sys
from unittest.mock import MagicMock, patch

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

def _make_scored_job(
    job_id: str,
    *,
    recommendation: Recommendation = Recommendation.good_fit,
    score_total: int = 82,
    reasons: list[str] | None = None,
) -> ScoredJob:
    """Deterministic ScoredJob for notification tests.

    Mirrors the helper shape from tests/test_pipeline.py and tests/storage/test_runs.py.
    """
    if reasons is None:
        reasons = ["Python match", "Remote OK"]
    job = Job(
        id=job_id,
        title="AI Engineer",
        company="Corp",
        location="Barcelona",
        remote=RemoteJob.remote,
        description="We build AI systems.",
        url=f"https://example.com/apply/{job_id}",
        source="jsearch",
    )
    score = JobScore(
        score_total=score_total,
        recommendation=recommendation,
        desglose=Desglose(
            encaje_puesto=88,
            encaje_skills=80,
            encaje_ubicacion=95,
            encaje_seniority=72,
        ),
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        reasons_for=reasons,
        reasons_against=["Kubernetes gap"],
        matched_skills=["Python"],
        missing_requirements=["Kubernetes"],
        deal_breaker_hit=False,
        deal_breaker_cual=None,
    )
    return ScoredJob(job=job, score=score)


def _make_200_response() -> MagicMock:
    """Mock httpx response: 200 OK from Telegram Bot API."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True, "result": {}}
    return resp


def _make_error_response(code: int = 400) -> MagicMock:
    """Mock httpx response: error from Telegram Bot API."""
    resp = MagicMock()
    resp.status_code = code
    resp.json.return_value = {
        "ok": False,
        "error_code": code,
        "description": "Bad Request",
    }
    return resp


# ---------------------------------------------------------------------------
# Test 1: format_offer_block renders all required fields (NOTIF-01 / D-05)
# ---------------------------------------------------------------------------

def test_format_offer_block():
    """format_offer_block output contains title, company, score, recommendation, reason, URL."""
    from app.notifications.digest import format_offer_block  # noqa: PLC0415

    sjob = _make_scored_job("fmt-test-1", score_total=82, reasons=["Python match", "Remote OK"])
    block = format_offer_block(sjob)

    assert "AI Engineer" in block, "title must appear in block"
    assert "Corp" in block, "company must appear in block"
    assert "82" in block, "score_total must appear in block"
    assert "good_fit" in block, "recommendation value must appear in block"
    assert "Python match" in block, "at least one reason_for must appear in block"
    assert f"https://example.com/apply/fmt-test-1" in block, "URL must appear in block"


# ---------------------------------------------------------------------------
# Test 2: telegram channel sends all qualifying jobs (NOTIF-01)
# ---------------------------------------------------------------------------

def test_telegram_channel_sends_digest(tmp_path, monkeypatch):
    """send_digest with telegram channel delivers all qualifying jobs and returns DigestResult."""
    from app.notifications import send_digest  # noqa: PLC0415

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("tg-job-1"),
        _make_scored_job("tg-job-2"),
    ])
    storage.set_setting("notification_channel", "telegram")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    with patch("app.notifications.telegram.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.post.return_value = _make_200_response()

        result = send_digest(storage, storage.get_settings())

    assert result.channel == "telegram", f"expected channel='telegram', got {result.channel!r}"
    assert result.delivered == 2, f"expected delivered=2, got {result.delivered}"
    assert instance.post.call_count >= 1, "httpx.Client.post must be called at least once"


# ---------------------------------------------------------------------------
# Test 3: email channel sends all qualifying jobs (NOTIF-01)
# ---------------------------------------------------------------------------

def test_email_channel_sends_digest(tmp_path, monkeypatch):
    """send_digest with email channel delivers all qualifying jobs via SMTP."""
    from app.notifications import send_digest  # noqa: PLC0415

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("email-job-1"),
        _make_scored_job("email-job-2"),
    ])
    storage.set_setting("notification_channel", "email")

    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USER", "test@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-fake")

    with patch("app.notifications.email_smtp.smtplib.SMTP") as MockSMTP:
        mock_smtp = MockSMTP.return_value.__enter__.return_value
        mock_smtp.send_message.return_value = None

        result = send_digest(storage, storage.get_settings())

    assert result.channel == "email", f"expected channel='email', got {result.channel!r}"
    assert result.delivered == 2, f"expected delivered=2, got {result.delivered}"
    assert mock_smtp.send_message.called, "smtp.send_message must be called"


# ---------------------------------------------------------------------------
# Test 4: channel resolution — only telegram env set (NOTIF-02 / D-03)
# ---------------------------------------------------------------------------

def test_channel_resolution_telegram_only(monkeypatch):
    """resolve_channel returns 'telegram' when only TELEGRAM env vars are set."""
    from app.notifications.digest import resolve_channel  # noqa: PLC0415

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    channel = resolve_channel({"notification_channel": "auto"})
    assert channel == "telegram", f"expected 'telegram', got {channel!r}"


# ---------------------------------------------------------------------------
# Test 5: channel resolution — only email env set (NOTIF-02)
# ---------------------------------------------------------------------------

def test_channel_resolution_email_only(monkeypatch):
    """resolve_channel returns 'email' when only SMTP env vars are set."""
    from app.notifications.digest import resolve_channel  # noqa: PLC0415

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USER", "test@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password-fake")

    channel = resolve_channel({"notification_channel": "auto"})
    assert channel == "email", f"expected 'email', got {channel!r}"


# ---------------------------------------------------------------------------
# Test 6: no channel configured — silent skip, nothing marked seen (NOTIF-02 / D-10)
# ---------------------------------------------------------------------------

def test_channel_resolution_none_silent(tmp_path, monkeypatch):
    """send_digest silently skips delivery when no channel is configured; seen stays 0."""
    from app.notifications import send_digest  # noqa: PLC0415

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    db_path = str(tmp_path / "test.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    storage.upsert_scored_jobs([_make_scored_job("nochan-job-1")])

    result = send_digest(storage, storage.get_settings())

    assert result.channel is None, f"expected channel=None, got {result.channel!r}"
    assert result.delivered == 0, f"expected delivered=0, got {result.delivered}"

    # Verify the job is still unseen in the DB
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT seen FROM jobs WHERE id = ?", ("nochan-job-1",)
    ).fetchone()
    conn.close()
    assert row is not None, "job row must exist"
    assert row[0] == 0, "seen must remain 0 when no channel is configured"


# ---------------------------------------------------------------------------
# Test 7: delivery failure leaves seen=0; job reappears in next digest (NOTIF-03 / D-10)
# ---------------------------------------------------------------------------

def test_delivery_failure_leaves_seen_0(tmp_path, monkeypatch):
    """When Telegram POST returns an error, job stays seen=0 and reappears next run."""
    from app.notifications import send_digest  # noqa: PLC0415

    db_path = str(tmp_path / "test.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    storage.set_setting("notification_channel", "telegram")
    storage.upsert_scored_jobs([_make_scored_job("fail-job-1")])

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    with patch("app.notifications.telegram.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.post.return_value = _make_error_response(400)

        result = send_digest(storage, storage.get_settings())

    assert len(result.errors) > 0, "errors must be non-empty on delivery failure"
    assert result.delivered == 0, f"expected delivered=0, got {result.delivered}"

    # seen must remain 0
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT seen FROM jobs WHERE id = ?", ("fail-job-1",)).fetchone()
    conn.close()
    assert row[0] == 0, "seen must be 0 when delivery failed"

    # Job must reappear in next qualifying query
    reappeared = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])
    assert len(reappeared) == 1, "failed job must reappear in next qualifying query"
    assert reappeared[0].job.id == "fail-job-1"


# ---------------------------------------------------------------------------
# Test 8: delivery success marks seen=1; absent from next digest (NOTIF-03 / SC4)
# ---------------------------------------------------------------------------

def test_delivery_success_marks_seen_1(tmp_path, monkeypatch):
    """Successful delivery marks seen=1; a fresh storage instance returns [] next run."""
    from app.notifications import send_digest  # noqa: PLC0415

    db_path = str(tmp_path / "test.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    storage.set_setting("notification_channel", "telegram")
    storage.upsert_scored_jobs([_make_scored_job("success-job-1")])

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    with patch("app.notifications.telegram.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.post.return_value = _make_200_response()

        result = send_digest(storage, storage.get_settings())

    assert result.delivered == 1, f"expected delivered=1, got {result.delivered}"

    # Verify seen=1 in DB
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT seen FROM jobs WHERE id = ?", ("success-job-1",)).fetchone()
    conn.close()
    assert row[0] == 1, "seen must be 1 after successful delivery"

    # Simulate restart: new storage instance on same DB file
    storage2 = SQLiteStorage(db_path)
    storage2.init_db()
    next_run = storage2.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])
    assert next_run == [], "delivered job must be absent from next run's qualifying query"


# ---------------------------------------------------------------------------
# Test 9: qualifying filter excludes maybe and below-threshold jobs (NOTIF-03)
# ---------------------------------------------------------------------------

def test_qualifying_filter_excludes_maybe_low_score(tmp_path):
    """Only strong_fit/good_fit jobs above min_score threshold qualify for digest."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    storage.upsert_scored_jobs([
        _make_scored_job("qual-good-85", recommendation=Recommendation.good_fit, score_total=85),
        _make_scored_job("qual-maybe-90", recommendation=Recommendation.maybe, score_total=90),
        _make_scored_job("qual-strong-50", recommendation=Recommendation.strong_fit, score_total=50),
    ])

    result = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])

    assert len(result) == 1, f"expected 1 qualifying job, got {len(result)}"
    assert result[0].job.id == "qual-good-85", (
        "only the good_fit-85 job should qualify "
        "(maybe-90 excluded by recommendation, strong_fit-50 excluded by threshold)"
    )


# ---------------------------------------------------------------------------
# Test 10: import cleanliness — no streamlit / apscheduler (D-02)
# ---------------------------------------------------------------------------

def test_notifications_no_streamlit_apscheduler():
    """Importing app.notifications must not pull streamlit or apscheduler into sys.modules."""
    # Scrub any leftover streamlit / apscheduler state
    for mod in list(sys.modules.keys()):
        if "streamlit" in mod or "apscheduler" in mod:
            del sys.modules[mod]

    import app.notifications  # noqa: F401, PLC0415

    assert "streamlit" not in sys.modules, (
        "app.notifications must not import streamlit at module level"
    )
    assert "apscheduler" not in sys.modules, (
        "app.notifications must not import apscheduler at module level"
    )


# ---------------------------------------------------------------------------
# Test 11: 4096-char chunking — >=2 chunks, no offer split (D-06)
# ---------------------------------------------------------------------------

def test_telegram_chunking_large_digest():
    """chunk_offers produces >=2 chunks for large digests; no offer block is split."""
    from app.notifications.digest import chunk_offers  # noqa: PLC0415

    header = "BuscadorDeEmpleo digest\n"
    # 60 blocks of ~120 chars each = ~7200 chars, forcing at least 2 chunks
    offer_blocks = [f"Job {i:02d} @ Company{i:02d}\n  Score: 82/100 (good_fit)\n  + Python match\n  https://example.com/jobs/{i:04d}" for i in range(60)]

    chunks = chunk_offers(header, offer_blocks)

    assert len(chunks) >= 2, f"expected >=2 chunks for 60 blocks, got {len(chunks)}"
    for chunk in chunks:
        assert len(chunk) <= 4096, f"chunk exceeds 4096 chars: {len(chunk)}"

    # Every offer block must appear intact in exactly one chunk
    for block in offer_blocks:
        count = sum(1 for chunk in chunks if block in chunk)
        assert count == 1, f"block must appear in exactly one chunk, found in {count}"


# ---------------------------------------------------------------------------
# Test 12: runs table has channel + notified columns (D-14)
# ---------------------------------------------------------------------------

def test_runs_table_has_channel_notified(tmp_path):
    """After init_db, the runs table must have channel and notified columns."""
    db_path = str(tmp_path / "test.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()

    conn = sqlite3.connect(db_path)
    cursor = conn.execute("PRAGMA table_info(runs)")
    col_names = [row[1] for row in cursor.fetchall()]
    conn.close()

    assert "channel" in col_names, (
        f"runs table must have 'channel' column; found columns: {col_names}"
    )
    assert "notified" in col_names, (
        f"runs table must have 'notified' column; found columns: {col_names}"
    )


# ---------------------------------------------------------------------------
# Test 13: multi-chunk partial failure — later chunk failure does NOT un-deliver
#          earlier chunks (D-11 / D-06 multi-chunk atomicity)
# ---------------------------------------------------------------------------

def test_telegram_partial_chunk_failure_marks_only_delivered(tmp_path, monkeypatch):
    """A later Telegram chunk failing must NOT un-deliver or mark-seen earlier chunks' jobs.

    Setup:
    - Upsert enough qualifying good_fit jobs (score 82) to produce >=2 chunks.
    - Patch httpx.Client.post: first call returns 200, second call returns 500.
    - Call send_digest.

    Assertions:
    - DigestResult.errors is non-empty (the failed chunk was recorded).
    - Jobs in the first (200) chunk have seen=1 in the DB.
    - Jobs in the failed (500) chunk have seen=0 in the DB.
    - Failed-chunk job IDs reappear in get_undelivered_qualifying; delivered IDs do not.
    """
    from app.notifications import send_digest  # noqa: PLC0415
    from app.notifications.digest import chunk_offers, format_offer_block  # noqa: PLC0415

    db_path = str(tmp_path / "test.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    storage.set_setting("notification_channel", "telegram")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token-fake")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456789")

    # Build enough jobs with padded reasons to force >=2 chunks at 4096 chars.
    # Each block is ~150 chars; ~28 jobs should exceed 4096 after a header.
    # Use 40 to be safe.
    n_jobs = 40
    job_ids = [f"partial-job-{i:03d}" for i in range(n_jobs)]
    scored_jobs = [
        _make_scored_job(
            jid,
            recommendation=Recommendation.good_fit,
            score_total=82,
            reasons=[f"Python match job {i}", "Remote OK is great for this role"],
        )
        for i, jid in enumerate(job_ids)
    ]
    storage.upsert_scored_jobs(scored_jobs)

    # Determine which job IDs land in which chunk by replicating the impl's logic.
    # (The implementation must produce blocks and chunks in the same order as the query.)
    header = "BuscadorDeEmpleo digest\n"
    blocks = [format_offer_block(sj) for sj in scored_jobs]
    chunks = chunk_offers(header, blocks)
    assert len(chunks) >= 2, (
        f"precondition failed: expected >=2 chunks with {n_jobs} jobs, got {len(chunks)}"
    )

    # Map each job_id to its chunk index via block substring presence.
    # chunk_offers guarantees each block appears intact in exactly one chunk.
    job_id_to_chunk: dict[str, int] = {}
    for jid, block in zip(job_ids, blocks):
        for chunk_idx, chunk in enumerate(chunks):
            if block in chunk:
                job_id_to_chunk[jid] = chunk_idx
                break

    first_chunk_ids = [jid for jid, cidx in job_id_to_chunk.items() if cidx == 0]
    later_chunk_ids = [jid for jid, cidx in job_id_to_chunk.items() if cidx >= 1]
    assert len(first_chunk_ids) > 0, "there must be jobs in the first chunk"
    assert len(later_chunk_ids) > 0, "there must be jobs in later chunks"

    # Patch: first POST returns 200, all subsequent return 500.
    side_effects = [_make_200_response()] + [_make_error_response(500)] * (len(chunks) + 2)

    with patch("app.notifications.telegram.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.post.side_effect = side_effects

        result = send_digest(storage, storage.get_settings())

    # D-11 assertions
    assert len(result.errors) > 0, "errors must be non-empty: the failed chunk must be reported"

    conn = sqlite3.connect(db_path)

    # First-chunk jobs must be seen=1 (delivered)
    for jid in first_chunk_ids:
        row = conn.execute("SELECT seen FROM jobs WHERE id = ?", (jid,)).fetchone()
        assert row is not None, f"job {jid} must exist in DB"
        assert row[0] == 1, f"job {jid} (first chunk, 200) must have seen=1 after delivery"

    # Later-chunk jobs must be seen=0 (not delivered due to 500 error)
    for jid in later_chunk_ids:
        row = conn.execute("SELECT seen FROM jobs WHERE id = ?", (jid,)).fetchone()
        assert row is not None, f"job {jid} must exist in DB"
        assert row[0] == 0, f"job {jid} (failed chunk, 500) must have seen=0"

    conn.close()

    # Failed-chunk IDs reappear in next qualifying query; delivered IDs do not.
    next_run = storage.get_undelivered_qualifying(70, ["strong_fit", "good_fit"])
    next_run_ids = {sj.job.id for sj in next_run}

    for jid in later_chunk_ids:
        assert jid in next_run_ids, (
            f"failed-chunk job {jid} must reappear in next qualifying query"
        )
    for jid in first_chunk_ids:
        assert jid not in next_run_ids, (
            f"delivered job {jid} must NOT reappear in next qualifying query"
        )
