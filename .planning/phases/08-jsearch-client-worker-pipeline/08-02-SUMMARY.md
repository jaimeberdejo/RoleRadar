---
phase: 08-jsearch-client-worker-pipeline
plan: "02"
subsystem: sources
tags: [jsearch, http-client, rapidapi, per-query-isolation, security]
dependency_graph:
  requires:
    - "app/dedup/mappers.py::jsearch_mapper (verified correct, NOT imported here)"
    - "httpx (already in deps)"
  provides:
    - "app/sources/jsearch.py: fetch_jsearch_query, fetch_all_queries, JSEARCH_BASE, DEFAULT_TIMEOUT"
    - "app/sources/__init__.py: package marker"
  affects:
    - "08-03 pipeline (will call fetch_all_queries)"
tech_stack:
  added: []
  patterns:
    - "sync httpx.Client as context manager for connection-pool reuse across multi-query runs"
    - "per-query try/except isolation — 429 or HTTPError returns [] for that query, others continue"
    - "RAPIDAPI_KEY read inside function via os.environ.get(), never at module level"
key_files:
  created:
    - app/sources/__init__.py
    - app/sources/jsearch.py
  modified: []
decisions:
  - "Used sync httpx.Client (not async) because APScheduler BlockingScheduler threads must not leak event loops"
  - "RAPIDAPI_KEY read per-call inside fetch_jsearch_query, not at import time — avoids env requirement at startup and satisfies MIG-03/T-08-02"
  - "context-manager pattern (with httpx.Client() as _client) chosen over try/finally to match test mock strategy (MockClient.return_value.__enter__.return_value)"
  - "fetch_all_queries reuses same client instance across all queries; each query error is isolated"
metrics:
  duration: "~5 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
---

# Phase 08 Plan 02: JSearch HTTP Client Summary

**One-liner:** Sync httpx.Client JSearch fetch layer with per-query 429/network error isolation and env-only RAPIDAPI_KEY sourcing.

## What Was Built

`app/sources/jsearch.py` provides the app-owned HTTP client for JSearch (RapidAPI):

- `fetch_jsearch_query(query, *, date_posted, num_pages, country, client)` — fetches a single query; returns raw `data[]` dicts or `[]` on 429/network error; never raises.
- `fetch_all_queries(queries, settings, *, client)` — iterates over a list of queries using a shared `httpx.Client` connection pool; per-query errors do not abort remaining queries (SRC-02).
- Module constants: `JSEARCH_BASE`, `JSEARCH_HOST`, `DEFAULT_TIMEOUT = 20.0`.

`app/sources/__init__.py` created as package marker.

## Tasks

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create app/sources/__init__.py and app/sources/jsearch.py | cef2d2a | app/sources/__init__.py, app/sources/jsearch.py |

## Verification Results

- All 5 tests in `tests/sources/test_jsearch.py` pass (GREEN).
- Full worktree suite: 243 passed, 0 failed (excluding test_pipeline.py and test_runs.py).
- `tests/test_no_secrets.py` passes — no literal RAPIDAPI_KEY in jsearch.py.
- `tests/test_import_cleanliness.py` passes.
- `python -c "import app.sources.jsearch"` succeeds without RAPIDAPI_KEY in env.

## Deviations from Plan

**1. [Rule 1 - Adaptation] Context-manager pattern in fetch_jsearch_query**

- **Found during:** Task 1, test analysis
- **Issue:** Plan spec said use `try/finally` with `_client = httpx.Client()`, but the test mocks `MockClient.return_value.__enter__.return_value` as the inner client instance, which only works if the code uses `with httpx.Client() as _client:`.
- **Fix:** Used `with httpx.Client(timeout=DEFAULT_TIMEOUT) as _client:` in the `client is None` branch of `fetch_jsearch_query`. The result is identical behavior; context manager cleanup is equivalent to try/finally close. Tests are the contract.
- **Files modified:** app/sources/jsearch.py
- **Commit:** cef2d2a

## Threat Surface Scan

No new network endpoints or auth paths introduced beyond what the plan's threat model covers. `RAPIDAPI_KEY` is sourced exclusively from `os.environ.get()` inside the function body — confirmed by `grep` and `test_no_secrets.py` passing.

## Self-Check: PASSED

- `app/sources/__init__.py`: FOUND
- `app/sources/jsearch.py`: FOUND
- Commit cef2d2a: FOUND
- 5/5 tests in tests/sources/test_jsearch.py: PASSED
- 243 tests total (worktree suite): PASSED
