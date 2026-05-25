---
phase: 08-jsearch-client-worker-pipeline
plan: "01"
subsystem: testing
tags: [pytest, red-guard, jsearch, pipeline, sqlite, httpx, mocking]

# Dependency graph
requires:
  - phase: 07-scoring-enrichment
    provides: ScoredJob, JobScore, FakeEmbedder, conftest helpers

provides:
  - RED guard tests for JSearch HTTP client (SRC-01, SRC-02)
  - RED guard tests for shared pipeline (SCHED-03, QA-06)
  - RED guard tests for runs table and mark_seen (STORE-05, STORE-07)
  - tests/sources/ package established

affects:
  - 08-02 (JSearch client implementation turns these tests GREEN)
  - 08-03 (pipeline implementation turns test_pipeline.py GREEN)
  - 08-04 (storage additions turn test_runs.py GREEN)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "unittest.mock.patch on app.sources.jsearch.httpx.Client for httpx mocking without respx"
    - "MockClient.return_value.__enter__.return_value pattern for context-manager client mocking"
    - "_make_scored_job helper in test module (mirrors test_sqlite.py pattern)"
    - "RED guard test file per-module: tests fail with ImportError/AttributeError until implementation ships"

key-files:
  created:
    - tests/sources/__init__.py
    - tests/sources/test_jsearch.py
    - tests/storage/test_runs.py
    - tests/test_pipeline.py
  modified: []

key-decisions:
  - "unittest.mock.patch used for httpx mocking (no respx dependency added)"
  - "test_run_pipeline_partial_fetch_error patches _fetch_all to raise Exception — pipeline must catch and record, not re-raise"
  - "test_mark_seen_persists_across_restart uses sqlite3 directly to verify column value after new storage instance (not relying on SQLiteStorage API)"
  - "fetch_all_queries named as top-level function (not a pipeline method) — tests import it directly from app.sources.jsearch"

patterns-established:
  - "Pattern: httpx.Client context-manager mock via MockClient.return_value.__enter__.return_value.get.side_effect"
  - "Pattern: RED state confirmed by running pytest and asserting ImportError or AttributeError"
  - "Pattern: capture_get side_effect to inspect headers passed to client.get()"

requirements-completed:
  - SRC-01
  - SRC-02
  - SRC-03
  - SCHED-03
  - STORE-05
  - STORE-07
  - QA-06

# Metrics
duration: 3min
completed: 2026-05-25
---

# Phase 08 Plan 01: RED Guard Test Scaffolding Summary

**15 RED guard tests across 3 new test files that define exact expected behaviour for JSearch client, shared pipeline, and SQLite runs/mark_seen additions — all fail with ImportError or AttributeError until Wave 1/2 implementations ship.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-25T08:28:08Z
- **Completed:** 2026-05-25T08:31:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Created `tests/sources/__init__.py` + `tests/sources/test_jsearch.py` with 5 tests covering SRC-01 (successful fetch), SRC-02 (429 isolation), network error handling, and RAPIDAPI_KEY-from-env assertion
- Created `tests/test_pipeline.py` with 5 tests covering import cleanliness (no streamlit/apscheduler), PipelineResult contract, dedup-against-stored, partial fetch error resilience, and runs row creation
- Created `tests/storage/test_runs.py` with 5 tests covering record_run counts, errors serialization, ordering, mark_seen flag, and mark_seen persistence across storage restarts
- All 15 tests collected without SyntaxError; all fail RED as intended

## Task Commits

Each task was committed atomically:

1. **Task 1: tests/sources/__init__.py + test_jsearch.py (SRC-01, SRC-02)** - `dac1bf8` (test)
2. **Task 2: tests/test_pipeline.py (SCHED-03, QA-06)** - `3f9dd5d` (test)
3. **Task 3: tests/storage/test_runs.py (STORE-05, STORE-07)** - `cb58f21` (test)

## Files Created/Modified

- `tests/sources/__init__.py` - Empty package marker for new test subdirectory
- `tests/sources/test_jsearch.py` - 5 RED guard tests: fetch success, 429 returns [], network error returns [], 429 isolation across queries, RAPIDAPI_KEY from env
- `tests/test_pipeline.py` - 5 RED guard tests: no streamlit/apscheduler in sys.modules, PipelineResult attributes, dedup-against-stored skips re-score, partial fetch error non-raising, runs row written
- `tests/storage/test_runs.py` - 5 RED guard tests: record_run row counts, errors stored as JSON, ordering most-recent-first, mark_seen sets flag, mark_seen persists across restart

## Decisions Made

- Used `unittest.mock.patch` on `app.sources.jsearch.httpx.Client` rather than adding `respx` — no new dependency needed, consistent with existing project mock pattern
- `fetch_all_queries` tested as a top-level importable function (not pipeline-internal), giving tests a clean surface to call with two queries and a settings dict
- `test_run_pipeline_partial_fetch_error_does_not_raise` patches `_fetch_all` to raise `Exception` and asserts `result.errors` is non-empty — this matches CONTEXT.md decision that the pipeline catches and records errors without re-raising
- `test_mark_seen_persists_across_restart` queries SQLite directly (via `sqlite3.connect`) rather than through a SQLiteStorage method to ensure the assertion doesn't accidentally pass if a future method reads from in-memory state

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 15 RED guard tests ready; Wave 1 (08-02) creates `app/sources/jsearch.py` + `app/sources/__init__.py` to turn `test_jsearch.py` GREEN
- Wave 1 (08-02) also adds `record_run`, `get_recent_runs`, `mark_seen` to SQLiteStorage to turn `test_runs.py` GREEN
- Wave 2 (08-03) creates `app/pipeline.py` to turn `test_pipeline.py` GREEN
- No blockers

---
*Phase: 08-jsearch-client-worker-pipeline*
*Completed: 2026-05-25*
