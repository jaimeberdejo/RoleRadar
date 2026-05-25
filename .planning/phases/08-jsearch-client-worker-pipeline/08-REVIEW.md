---
phase: 08-jsearch-client-worker-pipeline
reviewed: 2026-05-25T00:00:00Z
depth: deep
files_reviewed: 5
files_reviewed_list:
  - app/sources/jsearch.py
  - app/pipeline.py
  - app/storage/sqlite.py
  - app/storage/protocol.py
  - worker.py
findings:
  critical: 2
  warning: 4
  info: 1
  total: 7
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-05-25T00:00:00Z
**Depth:** deep (cross-file call-chain analysis)
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 8 introduces the JSearch HTTP client, the shared pipeline orchestrator, and the APScheduler worker. The secret-handling and SQL-injection posture are solid (RAPIDAPI_KEY never hardcoded or logged, all SQL uses parameterized queries). The overall batch-resilience design is good, but two gaps break the stated invariants: (1) the per-query error isolation in `fetch_jsearch_query` does not cover non-httpx exceptions from `resp.json()`, violating SRC-02, and (2) `_get_cv_profile` propagates `ValueError` for any non-sha256 JSON file found in the cache directory, killing the entire pipeline run and silently skipping `record_run`. Both are reachable in production.

Four additional warnings cover metric-semantic ambiguity, a lossy error type mismatch, the worker's absence of an immediate first-fire, and weak diagnostics for auth failures. One info item covers a duplicate storage construction.

---

## Critical Issues

### CR-01: `json.JSONDecodeError` from `resp.json()` breaks per-query isolation (SRC-02 violated)

**File:** `app/sources/jsearch.py:88`

**Issue:** `_do_get` calls `resp.json()` after `raise_for_status()`. If the RapidAPI endpoint returns a non-JSON body (HTML error page, gateway timeout, maintenance response — all real-world occurrences), `resp.json()` raises `json.JSONDecodeError`, which is **not** a subclass of `httpx.HTTPError`. The `except httpx.HTTPError` block in `fetch_jsearch_query` (line 71) does not catch it.

The exception propagates up through `fetch_all_queries` (which has no per-query try/except), killing all queries that come after the failing one. The SRC-02 invariant ("a 429 or network error on one query does not abort the others") is documented and tested, but is factually broken for any malformed-response error.

At the `pipeline.py` level the broad `except Exception` at line 176 does catch it, but at that point **all queries** (not just the failing one) have already been aborted.

**Fix:**
```python
def _do_get(
    client: httpx.Client,
    headers: dict,
    params: dict,
    query: str,
) -> list[dict]:
    """Execute GET, handle 429, parse response. May raise httpx.HTTPError."""
    resp = client.get(JSEARCH_BASE, headers=headers, params=params)
    if resp.status_code == 429:
        logger.warning("JSearch 429 for query=%r — skipping", query)
        return []
    resp.raise_for_status()
    try:
        return resp.json().get("data", [])
    except (ValueError, KeyError) as exc:
        # json.JSONDecodeError is a subclass of ValueError
        logger.warning(
            "JSearch non-JSON response for query=%r (status=%d): %s",
            query, resp.status_code, exc,
        )
        return []
```

This keeps the exception inside `_do_get` (which `fetch_jsearch_query`'s `except httpx.HTTPError` wraps), so per-query isolation holds for all error types. Alternatively, catch `(httpx.HTTPError, ValueError)` in `fetch_jsearch_query`.

---

### CR-02: `_get_cv_profile` propagates `ValueError` for non-sha256 cache filenames, crashing the pipeline and suppressing `record_run`

**File:** `app/pipeline.py:86-89` (calls `app/cv/cache.py:70`)

**Issue:** `_get_cv_profile` globs `*.json` files in the cache directory and passes each `stem` to `load_cached_profile`. `load_cached_profile` calls `_validate_hash(stem)`, which raises `ValueError` if the filename stem is not a 64-character lowercase hex string. Any `.json` file placed in `data/.cache` by the user (e.g., a test file, a backup, a file named `cv_backup.json`) triggers this.

The call site in `run_pipeline` (line 157) has **no try/except**. The `ValueError` propagates to the `if __name__ == "__main__"` block in `worker.py`'s `run_pipeline()` wrapper, which also has **no try/except**. APScheduler catches and logs it — the scheduler survives — but:

1. The pipeline run is completely aborted, even though the system could safely fall back to an empty `CVProfile`.
2. `storage.record_run(...)` (line 236) is **never called**, so the run is lost from the audit trail.
3. This will repeat every scheduled interval until the foreign file is manually removed.

**Fix in `app/pipeline.py`:**
```python
def _get_cv_profile() -> CVProfile:
    from app.cv.cache import load_cached_profile  # noqa: PLC0415
    import os  # noqa: PLC0415

    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    if cache_dir.exists():
        json_files = sorted(
            cache_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for json_file in json_files:
            stem = json_file.stem
            try:
                profile = load_cached_profile(stem)
            except ValueError:
                # Filename is not a sha256 hash — skip non-cache files silently
                logger.debug("_get_cv_profile: skipping non-cache file %s", json_file.name)
                continue
            if profile is not None:
                logger.debug("CV profile loaded from cache: %s", json_file.name)
                return profile

    logger.warning(
        "_get_cv_profile: no cached CV found — using empty CVProfile. "
        "Upload your CV via POST /cv/parse to enable skill matching."
    )
    return CVProfile(skills_tecnicas=[], experiencia=[], formacion=[], dominios=[])
```

---

## Warnings

### WR-01: `result.scored` metric is semantically ambiguous — records candidates attempted, not jobs actually scored

**File:** `app/pipeline.py:207, 241`

**Issue:** `result.scored = len(new_jobs)` (line 207) counts jobs passed to the scoring loop — **before** any `score_job` calls succeed. `result.new_seen = len(scored_list)` (line 230) counts jobs that were scored successfully **and** persisted. When `score_job` raises (e.g., LLM timeout), `scored > new_seen`. The `scored` field written to `record_run` at line 241 is therefore "attempted", not "succeeded", but the column is named `scored`, which implies success to anyone reading the runs table or the UI panel.

**Fix:** Rename or split the metric in `record_run`, or at minimum clarify the docstring to prevent misinterpretation:
```python
# Option A: use a clearer field name
result.candidates = len(new_jobs)   # jobs that passed was_seen filter
result.scored = len(scored_list)    # jobs successfully scored + persisted

storage.record_run(
    ...,
    scored=result.candidates,   # renamed to candidates in record_run signature too
    new_seen=result.scored,
)
```

Or add a comment clarifying the meaning of `scored` in both `PipelineResult` and `record_run`.

---

### WR-02: `normalize_jobs` returns `list[dict]` errors but `result.errors` is `list[str]` — dict repr strings enter the runs table

**File:** `app/pipeline.py:185-186`

**Issue:** `normalize_jobs` returns `errors: list[dict]` with structured fields `{"index": int, "source": str, "error": str}`. The pipeline extends `result.errors: list[str]` using:
```python
result.errors.extend(f"normalize: {e}" for e in norm_errors)
```
This stringifies each dict via `__repr__`, producing entries like:
```
normalize: {'index': 0, 'source': 'jsearch', 'error': "missing field 'title'"}
```
These strings are then `json.dumps`-ed and stored in the `runs.errors` column, making them valid JSON but not re-parseable as structured data. The error detail (index, source, message) is buried inside a repr string rather than being a proper JSON object.

**Fix:**
```python
result.errors.extend(
    f"normalize[{e['index']}]: {e['error']}" for e in norm_errors
)
```
Or change `PipelineResult.errors` to `list[str | dict]` and keep the dict objects intact. The simpler fix is the formatted string above.

---

### WR-03: Worker does not fire pipeline immediately on startup — first run delayed by full interval

**File:** `worker.py:65`

**Issue:**
```python
scheduler.add_job(run_pipeline, "interval", hours=interval_hours, id="pipeline")
```
APScheduler's `interval` trigger fires **after** the first interval elapses. On a fresh container start (or restart after a crash), no pipeline run happens until `interval_hours` (default 6) hours later. For a job-search tool used actively, this means the user may wait 6 hours for the first result batch after every deploy or restart.

**Fix:** Add `next_run_time=datetime.now()` to fire immediately on start:
```python
from datetime import datetime

scheduler.add_job(
    run_pipeline,
    "interval",
    hours=interval_hours,
    id="pipeline",
    next_run_time=datetime.now(),   # fire immediately, then every N hours
)
```

---

### WR-04: Empty or missing `RAPIDAPI_KEY` silently returns no results with a generic error message

**File:** `app/sources/jsearch.py:54, 72`

**Issue:** When `RAPIDAPI_KEY` is not set, `os.environ.get("RAPIDAPI_KEY", "")` returns an empty string. The API responds with HTTP 401 or 403. `raise_for_status()` raises `HTTPStatusError`, which is caught by `except httpx.HTTPError` and logged as:
```
WARNING JSearch HTTP error for query='AI Engineer' Barcelona': Client error '401 Unauthorized' ...
```
There is no distinction between an auth failure and a transient network error in the log message. An operator watching logs has no immediate signal that the key is simply missing.

**Fix:** Add a pre-flight check or a more specific log on 4xx:
```python
def _do_get(...) -> list[dict]:
    resp = client.get(JSEARCH_BASE, headers=headers, params=params)
    if resp.status_code == 429:
        logger.warning("JSearch 429 for query=%r — skipping", query)
        return []
    if resp.status_code in (401, 403):
        logger.error(
            "JSearch auth failure (status=%d) for query=%r — "
            "check RAPIDAPI_KEY env var",
            resp.status_code, query,
        )
        return []
    resp.raise_for_status()
    ...
```

---

## Info

### IN-01: Worker constructs a second `SQLiteStorage` instance just to read `schedule_interval_hours`

**File:** `worker.py:43-47`

**Issue:** The `if __name__ == "__main__"` block calls `get_storage_backend()` (which calls `init_db()`) to read `schedule_interval_hours`. Then `run_pipeline()` (when it fires) calls `get_storage_backend()` again internally, creating a second connection and calling `init_db()` a second time. `init_db()` is idempotent, so no correctness harm results, but it creates unnecessary I/O on every worker startup.

**Fix:** Pass the already-constructed `_storage` into `run_pipeline`:
```python
_storage = get_storage_backend()
_settings = _storage.get_settings()
interval_hours = int(_settings.get("schedule_interval_hours", str(_DEFAULT_INTERVAL_HOURS)))

# Capture _storage in a closure or use functools.partial
import functools
_job_fn = functools.partial(_pipeline_run, storage=_storage, embedder=embedder)
scheduler.add_job(_job_fn, "interval", hours=interval_hours, id="pipeline")
```
Note: if `embedder` is constructed once in `worker.py`, this also avoids the BgeM3Embedder being re-instantiated on every pipeline run (currently it is re-instantiated each call when `embedder=None`).

---

## Findings Summary by Severity

| Severity | Count | Key Issues |
|----------|-------|------------|
| BLOCKER (Critical) | 2 | `json.JSONDecodeError` breaks per-query isolation; `_get_cv_profile` ValueError crashes pipeline and silences `record_run` |
| WARNING | 4 | Ambiguous `scored` metric; dict-in-list-str type mismatch for normalize errors; no immediate-fire on worker start; auth failures indistinguishable from network errors |
| INFO | 1 | Redundant storage construction in worker startup |

**Priority order for remediation:**
1. CR-02 — pipeline can fail on every run after an unexpected file lands in `data/.cache`
2. CR-01 — per-query isolation invariant (SRC-02) broken for non-JSON API responses
3. WR-03 — operational friction (6h delay before first batch)
4. WR-04 — diagnostics for misconfiguration
5. WR-01 / WR-02 — audit data quality

---

_Reviewed: 2026-05-25T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
