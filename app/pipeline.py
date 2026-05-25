"""Shared pipeline orchestrator — BuscadorDeEmpleo v2.0.

`run_pipeline()` ties together all Phase 8 pieces:
  fetch → normalize → deduplicate → score (new only) → upsert → record_run

This module is intentionally import-clean:
  - NO import streamlit (success criterion 5 / QA-06)
  - NO import apscheduler
  - All heavy deps (BgeM3Embedder, get_storage_backend, load_user_profile,
    cv cache) are imported INSIDE run_pipeline() via deferred imports so the
    module stays lightweight and importable from any Python context.

_fetch_all is a thin module-level wrapper around fetch_all_queries so that
tests can patch it via `patch("app.pipeline._fetch_all", ...)`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.dedup import deduplicate, normalize_jobs
from app.models.schemas import CVProfile, ScoredJob
from app.scoring.scorer import score_job
from app.sources.jsearch import fetch_all_queries

if TYPE_CHECKING:
    from app.storage.protocol import Storage
    from app.dedup.embedder import Embedder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """Counts and output from a single pipeline run."""

    fetched: int = 0
    deduped: int = 0
    scored: int = 0
    new_seen: int = 0
    errors: list[str] = field(default_factory=list)
    scored_jobs: list[ScoredJob] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Module-level shim — patched in tests via patch("app.pipeline._fetch_all")
# ---------------------------------------------------------------------------

def _fetch_all(queries: list[str], settings: dict) -> list[dict]:
    """Thin wrapper around fetch_all_queries so tests can patch this name."""
    return fetch_all_queries(queries, settings)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_first_run(storage) -> bool:
    """True when the jobs table is empty (no prior run stored any job)."""
    return len(storage.get_history(limit=1)) == 0


def _get_cv_profile() -> CVProfile:
    """Load CVProfile from disk cache (most recent .json in data/.cache/).

    Returns a minimal empty CVProfile if no cache exists yet so the pipeline
    can run even before the user uploads their CV.
    """
    from app.cv.cache import load_cached_profile  # noqa: PLC0415

    import os  # noqa: PLC0415

    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    if cache_dir.exists():
        json_files = sorted(cache_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for json_file in json_files:
            stem = json_file.stem
            try:
                profile = load_cached_profile(stem)
            except ValueError:
                # stem is not a sha256 hex — skip non-cache files (e.g. backups, test files)
                logger.debug("_get_cv_profile: skipping non-cache file %s", json_file.name)
                continue
            if profile is not None:
                logger.debug("CV profile loaded from cache: %s", json_file.name)
                return profile

    logger.warning(
        "_get_cv_profile: no cached CV found — using empty CVProfile. "
        "Upload your CV via POST /cv/parse to enable skill matching."
    )
    return CVProfile(
        skills_tecnicas=[],
        experiencia=[],
        formacion=[],
        dominios=[],
    )


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run_pipeline(
    *,
    storage=None,
    embedder=None,
    llm_client=None,
    profile_path: str | Path | None = None,
) -> PipelineResult:
    """Fetch → normalize → deduplicate → score → persist → record run.

    Parameters
    ----------
    storage:
        Storage backend (SQLiteStorage). If None, constructs the default
        via get_storage_backend() (deferred import).
    embedder:
        Embedder instance for semantic dedup + scoring. If None, constructs
        BgeM3Embedder() (heavy: ~2.3 GB model download on first call).
    llm_client:
        instructor.Instructor client for LLM enrichment. None = use
        OPENAI_API_KEY env var inside score_job if present.
    profile_path:
        Override path to profile.yaml (used in tests).

    Returns
    -------
    PipelineResult
        Always returns — never re-raises fetch errors (SCHED-03).
    """
    result = PipelineResult()

    # ------------------------------------------------------------------
    # 1. Build injected dependencies if not provided
    # ------------------------------------------------------------------
    if storage is None:
        from app.storage import get_storage_backend  # noqa: PLC0415
        storage = get_storage_backend()

    if embedder is None:
        from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
        embedder = BgeM3Embedder()

    # ------------------------------------------------------------------
    # 2. Load settings (needed before profile so overlay can apply them)
    # ------------------------------------------------------------------
    settings = storage.get_settings()

    # ------------------------------------------------------------------
    # 3. Build effective user profile + CV profile
    #    (D-07: overlay settings pesos + deal_breakers onto profile.yaml identity)
    # ------------------------------------------------------------------
    from app.profile_overlay import build_effective_profile  # noqa: PLC0415

    user_profile = build_effective_profile(settings, profile_path)
    cv_profile = _get_cv_profile()

    # ------------------------------------------------------------------
    # 4. Determine date_posted (first-run vs subsequent)
    #    CR-01: respect the user's saved date_posted unless this is the first
    #    run, where we widen the window to "month" to backfill history.
    # ------------------------------------------------------------------
    date_posted = "month" if _is_first_run(storage) else (settings.get("date_posted") or "3days")
    settings = {**settings, "date_posted_override": date_posted}

    # ------------------------------------------------------------------
    # CR-01: build queries from the saved search_query when present, else
    # fall back to the ranking_puestos titles. search.py persists
    # search_query as a single OR-query string (e.g. '"AI Engineer" OR
    # "ML Engineer"'), so it is used as ONE query — not split.
    # ------------------------------------------------------------------
    raw_query = (settings.get("search_query") or "").strip()
    queries = [raw_query] if raw_query else [p.titulo for p in user_profile.ranking_puestos]

    # ------------------------------------------------------------------
    # 5. Fetch (SCHED-03: errors collected, not re-raised)
    # ------------------------------------------------------------------
    started_at = _now_iso()

    try:
        raw_jobs = _fetch_all(queries, settings)
        result.fetched = len(raw_jobs)
    except Exception as exc:  # noqa: BLE001
        logger.error("_fetch_all failed: %s", exc)
        result.errors.append(f"fetch: {exc}")
        raw_jobs = []

    # ------------------------------------------------------------------
    # 5. Normalize (batch-resilient)
    # ------------------------------------------------------------------
    if raw_jobs:
        jobs, norm_errors = normalize_jobs(raw_jobs, source="jsearch")
        # WR-02: preserve structured fields from norm_errors dicts as readable strings
        result.errors.extend(
            f"normalize[{e['index']}]({e.get('source', '')}): {e.get('error', e)}"
            for e in norm_errors
        )
    else:
        jobs = []

    # ------------------------------------------------------------------
    # 6. Deduplicate within batch
    # ------------------------------------------------------------------
    if jobs:
        deduped = deduplicate(
            jobs,
            embedder=embedder,
            umbral=float(settings.get("dedup_threshold", "0.85")),
        )
    else:
        deduped = []
    result.deduped = len(deduped)

    # ------------------------------------------------------------------
    # 7. Dedup against stored (hash check — was_seen, no re-embedding)
    # ------------------------------------------------------------------
    new_jobs = [j for j in deduped if not storage.was_seen(j.id)]

    # ------------------------------------------------------------------
    # 8. Score new jobs (per-job error isolation)
    # ------------------------------------------------------------------
    scored_list: list[ScoredJob] = []
    for job in new_jobs:
        try:
            job_score = score_job(
                job, user_profile, cv_profile, embedder, client=llm_client
            )
            scored_list.append(ScoredJob(job=job, score=job_score))
        except Exception as exc:  # noqa: BLE001
            logger.warning("score_job failed for job_id=%s: %s", job.id, exc)
            result.errors.append(f"score_job({job.id}): {exc}")

    result.scored_jobs = scored_list
    # WR-01: scored = jobs successfully scored (not candidates attempted)
    result.scored = len(scored_list)

    # ------------------------------------------------------------------
    # 9. Upsert scored jobs
    # ------------------------------------------------------------------
    if scored_list:
        storage.upsert_scored_jobs(scored_list)
    result.new_seen = len(scored_list)

    # ------------------------------------------------------------------
    # 10. Send digest notification (deferred import — keeps pipeline import-clean, D-12)
    #     Failures here NEVER abort the run or crash the worker (D-13).
    # ------------------------------------------------------------------
    digest_channel: str | None = None
    digest_notified = 0
    try:
        from app.notifications import send_digest  # noqa: PLC0415

        digest_result = send_digest(storage, settings)
        digest_channel = digest_result.channel
        digest_notified = digest_result.delivered
        if digest_result.errors:
            result.errors.extend(digest_result.errors)
    except Exception as exc:  # noqa: BLE001
        logger.error("send_digest failed: %s", exc)
        result.errors.append(f"notify: {exc}")

    # ------------------------------------------------------------------
    # 11. Record run metrics (AFTER digest so channel + notified land in one INSERT, D-14)
    # ------------------------------------------------------------------
    finished_at = _now_iso()
    storage.record_run(
        started_at=started_at,
        finished_at=finished_at,
        fetched=result.fetched,
        deduped=result.deduped,
        scored=result.scored,
        new_seen=result.new_seen,
        errors=result.errors if result.errors else None,
        channel=digest_channel,
        notified=digest_notified,
    )

    # ------------------------------------------------------------------
    # 12. Structured log summary
    # ------------------------------------------------------------------
    logger.info(
        "Pipeline complete: fetched=%d deduped=%d scored=%d new=%d errors=%d",
        result.fetched,
        result.deduped,
        result.scored,
        result.new_seen,
        len(result.errors),
    )
    return result


# ---------------------------------------------------------------------------
# Re-score stored jobs (no fetch — D-09)
# ---------------------------------------------------------------------------

def rescore_stored(
    *,
    storage=None,
    embedder=None,
    profile_path=None,
    limit: int = 1000,
) -> PipelineResult:
    """Re-score all stored jobs using the current effective profile.

    Reads stored jobs via get_history (which now includes the remote field after
    Plan 02), reconstructs minimal Job objects, and re-runs score_job with the
    effective profile (overlaid settings pesos + deal_breakers).

    Differences from run_pipeline:
      - NO _fetch_all call (D-09: no JSearch fetch on re-score).
      - NO record_run (re-score is not a fetch run; runs table semantics preserved).
      - description is "" (not stored in the DB) — encaje_skills will be neutral;
        documented limitation surfaced in the UI cost warning (Plan 05).

    Import-clean: no streamlit, no apscheduler. All heavy deps deferred.

    Args:
        storage: Storage backend. None → get_storage_backend() (deferred import).
        embedder: Embedder. None → BgeM3Embedder() (deferred import, heavy).
        profile_path: Override path to profile.yaml (used in tests).
        limit: Max number of stored jobs to re-score (default 1000).

    Returns:
        PipelineResult with scored = number of jobs successfully re-scored.
        Errors are isolated per job (batch-resilient).
    """
    result = PipelineResult()

    # Build dependencies if not injected
    if storage is None:
        from app.storage import get_storage_backend  # noqa: PLC0415
        storage = get_storage_backend()

    if embedder is None:
        from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
        embedder = BgeM3Embedder()

    # Build effective profile (D-07: overlay settings pesos + deal_breakers)
    settings = storage.get_settings()
    from app.profile_overlay import build_effective_profile  # noqa: PLC0415
    user_profile = build_effective_profile(settings, profile_path)
    cv_profile = _get_cv_profile()

    # Read stored jobs
    history = storage.get_history(limit=limit)

    # Reconstruct minimal Job objects and re-score
    rescored: list[ScoredJob] = []
    for row in history:
        try:
            from app.models.schemas import Job, RemoteJob  # noqa: PLC0415
            job = Job(
                id=row["id"],
                title=row["title"],
                company=row["company"],
                location=row.get("location"),
                # T-10-02-03: None remote must never crash (RemoteJob(None) raises)
                remote=RemoteJob(row["remote"]) if row.get("remote") else RemoteJob.unknown,
                url=row.get("url"),
                source=row.get("source") or "rescore",
                # description is "" — not stored; encaje_skills neutral ~50 (D-09 limitation)
            )
            job_score = score_job(job, user_profile, cv_profile, embedder, client=None)
            rescored.append(ScoredJob(job=job, score=job_score))
        except Exception as exc:  # noqa: BLE001
            logger.warning("rescore_stored: score_job failed for job_id=%s: %s", row.get("id"), exc)
            result.errors.append(f"rescore({row.get('id')}): {exc}")

    if rescored:
        storage.upsert_scored_jobs(rescored)

    result.scored = len(rescored)
    result.new_seen = len(rescored)
    result.scored_jobs = rescored

    logger.info(
        "rescore_stored complete: scored=%d errors=%d",
        result.scored,
        len(result.errors),
    )
    return result
