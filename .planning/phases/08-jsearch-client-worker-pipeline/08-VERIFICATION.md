---
phase: 08-jsearch-client-worker-pipeline
verified: 2026-05-25T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 8: JSearch Client + Worker Pipeline — Verification Report

**Phase Goal:** The app fetches job offers from JSearch under its own power and a
background worker process runs the full pipeline on a schedule; the pipeline function
is shared so a manual UI trigger and the scheduled worker produce identical results.

**Verified:** 2026-05-25T00:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification (phase completed via code-review-fix path
in an interrupted autonomous run; VERIFICATION.md was never generated)

**Note on code evolution:** The codebase has progressed through phases 9 and 10 since
phase 8 shipped. The files verified below are the live code. Phase 8's core artefacts
(`app/sources/jsearch.py`, `app/pipeline.py`, `app/storage/sqlite.py`, `worker.py`)
remain in place and intact, with the code-review fixes (CR-01, CR-02) merged in.
Additive phase-9/10 code (notifications, Streamlit UI) was grafted on without altering
the phase-8 contracts.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Worker fetches JSearch → normalize → dedup (incl. cross-run) → score → persist on schedule, without UI container | VERIFIED | `worker.py` uses `BlockingScheduler` as a standalone process; imports and calls `app.pipeline.run_pipeline` which executes every step |
| SC2 | 429/network/non-JSON error on one JSearch query does not abort others; partial results persist; per-query error logged | VERIFIED | `_do_get` catches `(ValueError, KeyError)` (including `json.JSONDecodeError`) and returns `[]`; `fetch_jsearch_query` catches `httpx.HTTPError`; tests `test_fetch_jsearch_query_non_json_returns_empty` and `test_fetch_all_queries_non_json_does_not_abort_sibling_queries` both pass (CR-01 fix confirmed present) |
| SC3 | Each run creates a row in the `runs` table with fetched/deduped/scored/new_seen fields | VERIFIED | `SQLiteStorage.record_run()` exists and inserts into the `runs` table (lines 308–344 of `sqlite.py`); `test_run_pipeline_creates_run_row` and `test_record_run_creates_row` both pass |
| SC4 | `mark_seen` persists across process restarts; a prior-run job is treated as already-seen and not re-scored | VERIFIED | `mark_seen` issues `UPDATE jobs SET seen = 1 WHERE id = ?`; `test_mark_seen_persists_across_restart` confirms a new `SQLiteStorage` instance on the same db file reads `seen=1`; `test_run_pipeline_dedup_against_stored` confirms `was_seen` correctly short-circuits re-scoring |
| SC5 | `run_pipeline()` is callable from any Python context — no Streamlit/APScheduler import inside `pipeline.py` | VERIFIED | Module-level imports in `app/pipeline.py` contain no `streamlit` or `apscheduler`; heavy deps use deferred `import` inside `run_pipeline()`; `test_pipeline_no_streamlit_apscheduler` and `test_run_pipeline_still_import_clean` both pass; manual check `python -c "import app.pipeline"` confirmed both modules absent from `sys.modules` |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/sources/jsearch.py` | JSearch HTTP client with per-query isolation | VERIFIED | 193 lines; `fetch_jsearch_query`, `fetch_all_queries`, `_do_get` fully implemented; CR-01 fix at lines 113–123; WR-04 auth-failure handling at lines 104–111 |
| `app/pipeline.py` | Shared `run_pipeline()` callable from any context | VERIFIED | 478 lines; `PipelineResult` dataclass; `run_pipeline()` with dependency injection; `_fetch_all` shim for test patching; `rescore_stored()` (phase-10 addition); no top-level streamlit/apscheduler imports |
| `app/storage/sqlite.py` | `runs` table + `record_run`, `get_recent_runs`, `mark_seen`, `was_seen` | VERIFIED | All four methods present; `runs` table created in `init_db()` at lines 91–110; idempotent `ALTER TABLE` migration for `channel`/`notified` columns added in phase 9 |
| `worker.py` | APScheduler `BlockingScheduler` calling shared pipeline | VERIFIED | 74 lines; `BlockingScheduler` with `ZoneInfo("Europe/Madrid")`, `coalesce=True`, `misfire_grace_time=3600`, `max_instances=1`; `next_run_time=datetime.now()` (WR-03 fix) fires immediately on startup; imports `run_pipeline` from `app.pipeline` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `worker.py` | `app/pipeline.py` | `from app.pipeline import run_pipeline as _pipeline_run` (line 18) | WIRED | Import at module level; called in the `run_pipeline()` wrapper at line 25 |
| `app/pipeline.py` | `app/sources/jsearch.py` | `from app.sources.jsearch import fetch_all_queries` (line 27); `_fetch_all` shim at line 56 | WIRED | Module-level import; `_fetch_all` called at line 256 inside `run_pipeline` |
| `app/pipeline.py` | `app/storage/sqlite.py` | deferred `from app.storage import get_storage_backend` + `storage.record_run(...)` line 341 | WIRED | Both `was_seen` (line 292) and `record_run` (line 341) called in every pipeline execution path |
| `app/pipeline.py` | `app/dedup` | `from app.dedup import deduplicate, normalize_jobs` (line 24) | WIRED | Both called in run_pipeline steps 5 and 6 |
| `app/pipeline.py` | `app/scoring/scorer.py` | `from app.scoring.scorer import score_job` (line 26) | WIRED | Called per-job in step 8 (line 300) |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `app/pipeline.py::run_pipeline` | `raw_jobs` | `_fetch_all(queries, settings)` → `fetch_all_queries` → `httpx.Client.get` → `resp.json().get("data", [])` | Yes — live HTTP call to JSearch RapidAPI; mocked in tests only | FLOWING |
| `app/storage/sqlite.py::record_run` | runs row | `INSERT INTO runs (...)` parameterized SQL | Yes — writes real integers from `PipelineResult` | FLOWING |
| `app/storage/sqlite.py::was_seen` | `bool` | `SELECT 1 FROM jobs WHERE id = ?` | Yes — queries live jobs table | FLOWING |
| `app/storage/sqlite.py::mark_seen` | `seen` column | `UPDATE jobs SET seen = 1 WHERE id = ?` | Yes — updates live row on disk; verified durable across process restart | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `test_fetch_jsearch_query_non_json_returns_empty` | `pytest tests/sources/test_jsearch.py::test_fetch_jsearch_query_non_json_returns_empty -q` | pass | PASS |
| `test_fetch_all_queries_non_json_does_not_abort_sibling_queries` | `pytest tests/sources/test_jsearch.py::test_fetch_all_queries_non_json_does_not_abort_sibling_queries -q` | pass | PASS |
| `test_run_pipeline_creates_run_row` | `pytest tests/test_pipeline.py::test_run_pipeline_creates_run_row -q` | pass | PASS |
| `test_mark_seen_persists_across_restart` | `pytest tests/storage/test_runs.py::test_mark_seen_persists_across_restart -q` | pass | PASS |
| `test_pipeline_no_streamlit_apscheduler` | `pytest tests/test_pipeline.py::test_pipeline_no_streamlit_apscheduler -q` | pass | PASS |
| Full phase-8 test suite | `python -m pytest tests/sources/ tests/test_pipeline.py tests/storage/ -q` | **49 passed, 5 warnings** | PASS |
| Import cleanliness (live Python) | `python -c "import app.pipeline; ..."` | `streamlit in sys.modules: False` / `apscheduler in sys.modules: False` | PASS |

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| SRC-01 | JSearch HTTP client using httpx; key from env only | SATISFIED | `app/sources/jsearch.py`; `os.environ.get("RAPIDAPI_KEY", "")` inside function, never at module level |
| SRC-02 | Multi-query fetch; 429/partial failure does not abort batch | SATISFIED | `fetch_all_queries` loops per-query; `fetch_jsearch_query` catches `httpx.HTTPError`; `_do_get` catches `(ValueError, KeyError)` for non-JSON responses (CR-01 fix) |
| SRC-03 | Fetch resilient to partial failures; errors logged and skipped | SATISFIED | Per-query `try/except httpx.HTTPError` plus `(ValueError, KeyError)` catch; `run_pipeline` outer `except Exception` prevents full abort |
| SCHED-01 | Worker as a separate process using APScheduler BlockingScheduler | SATISFIED | `worker.py` uses `BlockingScheduler`; separate Docker service in `docker-compose.yml` |
| SCHED-02 | Shared pipeline callable by both worker and UI | SATISFIED | `app/pipeline.py::run_pipeline` is the single shared callable; worker imports it at module level; UI calls it via the "Run now" button (phase 10) |
| SCHED-03 | Schedule configurable; ZoneInfo; coalesce/grace; survives restarts | SATISFIED | `schedule_interval_hours` read from settings DB; `ZoneInfo("Europe/Madrid")`; `coalesce=True`, `misfire_grace_time=3600`; `next_run_time=datetime.now()` for immediate fire on restart |
| STORE-05 | `runs` table; `record_run` + `get_recent_runs` | SATISFIED | Table created in `init_db()`; `record_run` inserts fetched/deduped/scored/new_seen/errors/channel/notified; `get_recent_runs` returns ordered rows |
| STORE-07 | `mark_seen(id)` persists across restarts; no re-notify | SATISFIED | `UPDATE jobs SET seen = 1 WHERE id = ?` writes to disk; `was_seen` queries by id; both confirmed by tests including restart test |
| QA-06 | Tests for JSearch client, pipeline worker, storage runs | SATISFIED | `tests/sources/test_jsearch.py` (11 tests), `tests/test_pipeline.py` (10 tests), `tests/storage/test_runs.py` (5 tests), `tests/storage/test_sqlite.py`, `tests/storage/test_undelivered.py` — all 49 in scope pass |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `worker.py` | 18 | `from app.pipeline import run_pipeline as _pipeline_run` at module level (while APScheduler is also imported at module level) | Info | No practical issue: `worker.py` is ONLY run as `__main__` (its own process); it is never imported by Streamlit. The risk flagged in CLAUDE.md ("Hilo en segundo plano dentro de Streamlit") is not triggered here. |

No blocker or warning anti-patterns found. No TODO/FIXME/placeholder comments in phase-8 files. No stub returns. No hardcoded credentials.

---

### Human Verification Required

None. All five success criteria are verifiable from the codebase and test results. No visual, real-time, or external-service behavior requires human observation for this phase's goals.

---

## Gaps Summary

No gaps. All five ROADMAP success criteria are met:

1. **SC1 (Worker pipeline on schedule):** `worker.py` runs as a standalone `BlockingScheduler` process, imports `run_pipeline` from `app.pipeline`, and calls it on a configurable interval with immediate first-fire.

2. **SC2 (Per-query error isolation — CR-01 fix confirmed):** The code-review fix is present and active. `_do_get` in `app/sources/jsearch.py` wraps `resp.json()` in `try/except (ValueError, KeyError)` (lines 113–123), which catches `json.JSONDecodeError` (a `ValueError` subclass). Two dedicated tests (`test_fetch_jsearch_query_non_json_returns_empty` and `test_fetch_all_queries_non_json_does_not_abort_sibling_queries`) pass and cover the exact invariant.

3. **SC3 (runs table row per execution):** `record_run` inserts a complete row after every `run_pipeline` call. The call is outside the fetch/score try/except blocks so it runs even when errors occurred (CR-02 fix also confirmed — `_get_cv_profile` catches `ValueError` per-file).

4. **SC4 (mark_seen durable across restarts):** `mark_seen` uses a parameterized `UPDATE` to disk; `test_mark_seen_persists_across_restart` opens a second `SQLiteStorage` instance on the same file and confirms `seen=1` is still set.

5. **SC5 (pipeline.py import-clean):** No top-level `streamlit` or `apscheduler` import in `app/pipeline.py`. Both `test_pipeline_no_streamlit_apscheduler` and the live Python check confirm neither module appears in `sys.modules` after `import app.pipeline`.

---

_Verified: 2026-05-25T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
