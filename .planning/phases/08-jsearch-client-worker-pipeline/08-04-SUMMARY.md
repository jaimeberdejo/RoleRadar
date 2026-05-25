---
phase: "08-jsearch-client-worker-pipeline"
plan: "04"
subsystem: "pipeline"
tags: ["pipeline", "worker", "orchestration", "scheduling", "scoring", "dedup"]

dependency_graph:
  requires:
    - "08-02 (JSearch client: fetch_all_queries)"
    - "08-03 (SQLiteStorage: record_run, get_recent_runs, was_seen, upsert_scored_jobs)"
    - "07-xx (score_job v2 signature with embedder injection)"
    - "app/dedup (normalize_jobs, deduplicate)"
    - "app/config/loader (load_user_profile)"
    - "app/cv/cache (load_cached_profile)"
  provides:
    - "app/pipeline.py::run_pipeline — shared pipeline callable from worker + UI"
    - "app/pipeline.py::PipelineResult — structured result dataclass"
    - "worker.py — real scheduler job calling the shared pipeline"
  affects:
    - "Phase 9 (notifications will call run_pipeline + mark_seen)"
    - "Phase 10 (UI 'Run now' button calls run_pipeline; reads PipelineResult)"

tech_stack:
  added: []
  patterns:
    - "Dependency-injectable run_pipeline(*,storage,embedder,llm_client,profile_path)"
    - "Module-level _fetch_all shim for testability via patch('app.pipeline._fetch_all')"
    - "Deferred imports for heavy deps (BgeM3Embedder, get_storage_backend, load_user_profile)"
    - "Fetch-error resilience: Exception caught at top level, not re-raised (SCHED-03)"
    - "Per-job score_job error isolation: exception logged, job skipped, run continues"
    - "First-run detection via get_history(limit=1) → date_posted='month' vs '3days'"
    - "Dedup-against-stored via was_seen(job.id) hash check (O(n) lookups, no re-embedding)"

key_files:
  created:
    - "app/pipeline.py — PipelineResult dataclass + run_pipeline() orchestrator"
  modified:
    - "worker.py — replaced stub with real import + wrapper over app.pipeline.run_pipeline"
    - "tests/test_pipeline.py — Rule 1 fix: corrected pre-populated job id to actual SHA-256"

decisions:
  - "Expose _fetch_all as a module-level function (not inline) so tests can patch it at 'app.pipeline._fetch_all' without patching the original fetch_all_queries in app.sources.jsearch"
  - "Fetch exceptions caught at the top level of run_pipeline (not per-query) since _fetch_all already does per-query isolation internally. run_pipeline catches the outer exception for any fatal fetch failure and records it in result.errors"
  - "result.scored = len(new_jobs) BEFORE scoring (i.e., jobs scheduled to be scored), result.new_seen = len(scored_list) AFTER (i.e., successfully scored + persisted). This distinction matters for monitoring error rates"
  - "CV profile falls back to empty CVProfile if no cache exists rather than failing the pipeline — acceptable since score_job emits a warning and uses neutral skills score (50)"
  - "worker.py uses a thin wrapper (run_pipeline → _pipeline_run) so the scheduler still calls a local 'run_pipeline' symbol while the real logic lives in app.pipeline"

metrics:
  duration: "~15 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 2
  files_created: 1
  files_modified: 2
---

# Phase 08 Plan 04: Shared Pipeline + Worker Wiring Summary

**One-liner:** Shared `run_pipeline()` orchestrator in `app/pipeline.py` tying fetch→normalize→dedup→score→upsert→record_run, with worker.py wired to call it via APScheduler.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create app/pipeline.py with PipelineResult and run_pipeline() | 3d650ce | app/pipeline.py (created), tests/test_pipeline.py (Rule 1 fix) |
| 2 | Wire worker.py to call the real run_pipeline() | 99fba57 | worker.py |

## What Was Built

### app/pipeline.py

The shared pipeline orchestrator that ties together all Phase 8 components:

- **`PipelineResult`** dataclass: `fetched`, `deduped`, `scored`, `new_seen`, `errors: list[str]`, `scored_jobs: list[ScoredJob]`
- **`_fetch_all(queries, settings)`**: module-level shim over `fetch_all_queries` — enables `patch("app.pipeline._fetch_all")` in tests without patching the source module
- **`run_pipeline(*, storage, embedder, llm_client, profile_path)`**: dependency-injectable pipeline with steps:
  1. Build missing deps (deferred imports: `BgeM3Embedder`, `get_storage_backend`)
  2. Load `UserProfile` from YAML + `CVProfile` from disk cache (empty fallback if no cache)
  3. Determine `date_posted`: `"month"` on first run (empty jobs table), `"3days"` subsequently
  4. Fetch via `_fetch_all` — exceptions caught and added to `result.errors`, never re-raised
  5. Normalize via `normalize_jobs(raw, "jsearch")` — per-offer errors collected in `result.errors`
  6. Deduplicate within batch via `deduplicate(jobs, embedder, umbral)` using semantic clustering
  7. Dedup against stored: `was_seen(job.id)` SHA-256 hash check — no re-embedding
  8. Score each new job via `score_job(job, user_profile, cv_profile, embedder)` — per-job exceptions isolated and logged
  9. Upsert all scored jobs via `storage.upsert_scored_jobs`
  10. Record run metrics via `storage.record_run(started_at, finished_at, fetched, deduped, scored, new_seen, errors)`
  11. Emit structured log summary

**CRITICAL invariant (QA-06 / success criterion 5):** `import app.pipeline` does NOT pull `streamlit` or `apscheduler` into `sys.modules`. Verified in `test_pipeline_no_streamlit_apscheduler`.

### worker.py

The existing stub `run_pipeline()` was replaced with a thin wrapper that:
- Imports `app.pipeline.run_pipeline as _pipeline_run` at module level
- Calls `_pipeline_run()` and logs the `PipelineResult` counts
- Keeps all scheduler configuration unchanged (BlockingScheduler, ZoneInfo, coalesce, misfire_grace_time, max_instances=1, settings-driven interval)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected test pre-populated job id to match actual SHA-256**
- **Found during:** Task 1 verification (test_run_pipeline_dedup_against_stored failing after 4/5 tests passed)
- **Issue:** `_make_scored_job("pipeline-test-job-1")` pre-populated the DB with id `"pipeline-test-job-1"` (a plain string), but `normalize_jobs` + `jsearch_mapper` produces `stable_job_id("PipelineCorp", "AI Engineer", "Barcelona")` = `c9b290b3eea4a66298d2beab5757ce9b5e461325a2cd50ae5c69dddf006bef9f`. `was_seen(computed_sha256)` returned False → job counted as new.
- **Fix:** Updated the test to use `_EXISTING_ID = "c9b290b3eea4a66298d2beab5757ce9b5e461325a2cd50ae5c69dddf006bef9f"` and call `_make_scored_job(_EXISTING_ID)`. The test comment already stated the intent: *"Build a raw JSearch-like dict that normalizes to the same stable job id."*
- **Files modified:** `tests/test_pipeline.py`
- **Commit:** 3d650ce

## Verification Results

```
SC5 PASS: no streamlit/apscheduler in sys.modules after import app.pipeline

tests/sources/test_jsearch.py .....  [5 passed]
tests/test_pipeline.py      .....    [5 passed]
tests/storage/test_runs.py  .....    [5 passed]

Full suite: 253 passed, 5 warnings in 5.20s

worker imports OK
grep -c "stub|no implementado" worker.py → 0
grep -c "from app.pipeline import" worker.py → 1
secrets grep → 0
```

## Known Stubs

None. `run_pipeline()` is fully wired end-to-end with all Phase 8 components.

## Threat Flags

No new network endpoints or trust-boundary surface introduced beyond what was already registered in the Phase 8 threat model (T-08-09 through T-08-13).

## Self-Check: PASSED

- `app/pipeline.py` exists: FOUND
- `worker.py` updated: FOUND
- Commits exist: 3d650ce (FOUND), 99fba57 (FOUND)
- All 5 pipeline tests GREEN: PASSED
- Full suite 253 tests GREEN: PASSED
- No streamlit/apscheduler in sys.modules: PASSED
