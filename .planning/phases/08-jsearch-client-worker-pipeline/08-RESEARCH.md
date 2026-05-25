# Phase 8: JSearch Client & Worker Pipeline - Research

**Researched:** 2026-05-25
**Domain:** JSearch RapidAPI client, APScheduler 3.x BlockingScheduler, SQLite runs table, pipeline orchestration
**Confidence:** HIGH (mapper shape verified against test fixture; APScheduler via official docs + installed version; workflow JSON confirmed headers/params)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- HTTP via sync `httpx.Client` (no async inside BlockingScheduler job)
- JSearch endpoint: `https://jsearch.p.rapidapi.com/search`
- Auth: `X-RapidAPI-Key` + `X-RapidAPI-Host: jsearch.p.rapidapi.com` from `RAPIDAPI_KEY` env var
- Multi-query: one call per `ranking_puestos` title (or `search_query` setting)
- Per-query error isolation: 429/network on one query logs and continues; never aborts batch
- `app/pipeline.py::run_pipeline()` imports NO Streamlit, NO APScheduler
- `run_pipeline` accepts injected `storage`, `embedder` (testability)
- `runs` table (STORE-05): id, started_at, finished_at, fetched, deduped, scored, new_seen, errors TEXT
- `mark_seen(job_id)` (STORE-07): sets `seen=1`; persists across restarts
- Dedup against stored: a job already in DB (by stable id) is not re-scored or re-counted as new
- `search_country` default `es`, `num_pages` = 1, `date_posted` = `month` on first run else `3days`

### Claude's Discretion
- Exact `run_pipeline` return type (structured result with counts + scored jobs)
- `record_run` / `get_recent_runs` method signatures on SQLiteStorage + Protocol
- Whether to add `respx` to dev deps or use `unittest.mock` / `monkeypatch` for httpx mocking
- Timeout value for JSearch requests (10-30s recommended; see research below)

### Deferred Ideas (OUT OF SCOPE)
- Notifications/digest delivery (Phase 9)
- UI status panel consuming runs table (Phase 10)
- `num_pages` exposed in UI (v2.x)
</user_constraints>

---

## Summary

Phase 8 wires three pieces: a JSearch HTTP client, a shared pipeline function, and the already-scaffolded worker scheduler. The mapper field verification is the most critical pre-coding step. The existing `jsearch_mapper` was already written against the correct raw API shape (confirmed via the verified test fixture in `tests/dedup/test_normalize.py` line 231-248 and the archived n8n workflow JSON). The mapper is correct and needs no field-level changes — only the `stable_job_id` basis (company + title + location) is used, not `job_id`, which is intentional for cross-source dedup stability.

APScheduler 3.11.2 is already installed. Its BlockingScheduler logs job exceptions via `EVENT_JOB_ERROR` and continues running — exceptions inside a job body do not crash the scheduler. The `worker.py` stub is correctly configured (`coalesce`, `misfire_grace_time`, `max_instances=1`, `ZoneInfo`).

The dedup-against-stored pattern is simple: call `storage.was_seen(job.id)` before scoring and exclude already-stored jobs from the new-scored count (they still upsert but are marked as not-new). No embedding comparison against stored items is required — the stable ID hash is sufficient for cross-run dedup.

**Primary recommendation:** Implement `app/sources/jsearch.py` first (sync httpx, multi-query, per-query try/except), then `app/pipeline.py` (thin orchestrator calling existing dedup/scoring), then storage additions (runs table + mark_seen), then wire worker.py. Add `respx` to dev deps for clean httpx mocking.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| JSearch HTTP fetch | `app/sources/jsearch.py` | — | Isolated source client; all external I/O in one place |
| Normalization + dedup | `app/dedup/` (existing) | — | Already implemented; pipeline calls it |
| Scoring | `app/scoring/scorer.py` (existing) | — | Already implemented Phase 7 |
| Pipeline orchestration | `app/pipeline.py` (new) | — | Single shared function; no UI/scheduler import |
| Scheduled execution | `worker.py` (existing stub) | — | APScheduler BlockingScheduler process |
| Persistence (runs table) | `app/storage/sqlite.py` | `app/storage/protocol.py` | Mirrors existing jobs/settings pattern |
| Dedup against stored | `app/pipeline.py` via `storage.was_seen()` | — | Stable ID hash check; no re-embedding |

---

## 1. Raw JSearch `/search` Response Shape

### Top-Level Envelope

```json
{
  "status": "OK",
  "request_id": "uuid-string",
  "parameters": { "query": "...", "page": "1", "num_pages": "1", "country": "es" },
  "data": [ /* array of job objects */ ]
}
```

[VERIFIED: tests/dedup/test_normalize.py `_JSEARCH_JOB` fixture (2026-05-23); CITED: dev.to/anuoluwapoae/job-search-api; CITED: openwebninja.com/api/jsearch]

### Per-Job Fields in `data[]`

The following fields are confirmed present. The mapper uses a subset marked **USED**.

| Field | Type | Notes | Mapper Action |
|-------|------|-------|---------------|
| `job_id` | str | RapidAPI internal ID (UUID-like) | **NOT used** — stable_job_id uses company+title+location |
| `employer_name` | str \| null | Company name | **USED** → `Job.company` |
| `employer_logo` | str \| null | Logo URL | Ignored |
| `employer_website` | str \| null | — | Ignored |
| `employer_company_type` | str \| null | — | Ignored |
| `job_publisher` | str | Source site (LinkedIn, Indeed…) | Ignored |
| `job_title` | str | Position title | **USED** → `Job.title` |
| `job_employment_type` | str \| null | FULLTIME, PARTTIME, CONTRACTOR | Ignored (no schema field) |
| `job_description` | str | Plain text (NOT HTML) | **USED** → `Job.description` |
| `job_is_remote` | bool | True=remote | **USED** → `Job.remote` |
| `job_apply_link` | str \| null | Direct apply URL | **USED** → `Job.url` |
| `job_apply_is_direct` | bool | — | Ignored |
| `apply_options` | array | [{publisher, apply_link}] | Ignored |
| `job_posted_at_datetime_utc` | str \| null | ISO 8601 UTC e.g. "2026-05-20T00:00:00.000Z" | **USED** (preferred over timestamp) |
| `job_posted_at_timestamp` | int \| null | Unix seconds | **USED** (fallback if ISO null) |
| `job_city` | str \| null | City | **USED** via `_jsearch_location()` |
| `job_state` | str \| null | State/region | **USED** via `_jsearch_location()` |
| `job_country` | str \| null | ISO country code | **USED** via `_jsearch_location()` |
| `job_location` | str \| null | Composed string e.g. "Chicago, IL" | **USED** (preferred in `_jsearch_location()`) |
| `job_latitude` | float \| null | — | Ignored |
| `job_longitude` | float \| null | — | Ignored |
| `job_min_salary` | float \| null | Min salary value | **USED** → `Salary.min` |
| `job_max_salary` | float \| null | Max salary value | **USED** → `Salary.max` |
| `job_salary_currency` | str \| null | e.g. "USD", "EUR" | **USED** → `Salary.moneda` |
| `job_salary_period` | str \| null | "YEAR", "MONTH", "WEEK", "DAY", "HOUR" | **USED** → `Salary.periodo` via `_JSEARCH_PERIODO` dict |
| `job_highlights` | object \| null | {"Qualifications": [...], "Responsibilities": [...]} | Ignored |
| `job_required_experience` | object \| null | Nested object | Ignored |
| `job_required_skills` | array \| null | List of skill strings | Ignored (description used instead) |
| `job_required_education` | object \| null | — | Ignored |
| `job_benefits` | array \| null | — | Ignored |
| `job_google_link` | str \| null | — | Ignored |
| `job_offer_expiration_datetime_utc` | str \| null | — | Ignored |
| `job_onet_soc` | str \| null | — | Ignored |
| `job_naics_code` | str \| null | — | Ignored |

### Mapper Verdict: No Changes Required

The existing `jsearch_mapper` in `app/dedup/mappers.py` correctly maps all confirmed fields. The test fixture `_JSEARCH_JOB` (lines 231-248 in `test_normalize.py`) was written against the raw API shape (not n8n-transformed) and all 5 mapper tests pass against it. Key design choices verified as correct:

- **`job_id` not used for `Job.id`**: `stable_job_id(company, title, location)` is the right approach for cross-source dedup stability. [VERIFIED: codebase design doc]
- **`job_description` is plain text**: JSearch returns plain text, not HTML. The mapper does NOT strip HTML. This is correct — unlike Arbeitnow which returns HTML. [VERIFIED: test fixture; CITED: openwebninja.com]
- **`_jsearch_location()`**: prefers `job_location` (composed string) over city/state/country assembly. This is correct — `job_location` is confirmed present and usually formatted. [VERIFIED: test_jsearch_mapper_location_compuesta_sin_job_location]
- **Salary `periodo` mapping**: `_JSEARCH_PERIODO` dict maps YEAR→anual, MONTH→mensual, WEEK→semanal, DAY→diario, HOUR→por hora. Correct. [VERIFIED: test_jsearch_mapper_salary]
- **`job_is_remote=False` → `RemoteJob.unknown`**: correct — false remote does not mean onsite, just unspecified. [VERIFIED: test_jsearch_mapper_remote_y_posted_at]

**One gap to address**: the mapper does not map `job_employment_type` (FULLTIME/CONTRACTOR). The `Job` schema has no field for this, so it is correctly ignored. No action needed.

---

## 2. JSearch `/search` Request Parameters

### Required Headers

```python
headers = {
    "X-RapidAPI-Key": os.environ["RAPIDAPI_KEY"],
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
}
```

[VERIFIED: docs/archive/n8n/n8n/workflow.json node "JSearch"]

### Query Parameters

| Param | Type | Required | Values | Notes |
|-------|------|----------|--------|-------|
| `query` | str | YES | e.g. `"AI Engineer"` | One call per query term |
| `page` | str/int | NO | default `"1"` | Always 1 (num_pages=1 covers it) |
| `num_pages` | str/int | NO | `"1"` | Keep at 1; exposed as setting |
| `date_posted` | str | NO | `"all"`, `"today"`, `"3days"`, `"week"`, `"month"` | First-run logic: `"month"` if DB empty, else `"3days"` |
| `country` | str | NO | ISO 2-letter code e.g. `"es"`, `"us"` | From `search_country` setting (default `"es"`) |
| `employment_types` | str | NO | `"FULLTIME"`, `"CONTRACTOR"`, etc. | Not used in Phase 8 |
| `language` | str | NO | e.g. `"en_GB"` | Not used in Phase 8 |

[VERIFIED: docs/archive/n8n/n8n/workflow.json; CITED: openwebninja.com/api/jsearch; ASSUMED: exact values of `date_posted` enum — `"month"` and `"3days"` confirmed by n8n workflow code comment]

The n8n workflow used: `query`, `page`, `num_pages`, `date_posted` — no `country` in the archived workflow (country filtering may work via query string like `"AI Engineer in Spain"`). The CONTEXT.md decision is to pass `country` param directly.

### Rate Limits and 429 Behavior

[ASSUMED — free tier limits not confirmed from official JSearch docs in this session; based on general RapidAPI free tier behavior]

- Free tier: typically 200-500 requests/month total (varies by plan). JSearch specifically is commonly cited at ~200 requests/month on the free tier.
- 429 response: `{"message": "You have exceeded the MONTHLY quota for Requests..."}` with HTTP 429
- No `Retry-After` header reliably present on RapidAPI 429s
- **Phase 8 decision (from CONTEXT.md)**: on 429, log per-query and continue to next query — no retry within the run. This is correct: the free-tier monthly quota means retrying immediately would waste quota.

### Recommended Timeout

```python
httpx.Client(timeout=20.0)  # 20s: generous for JSearch (P95 ~5s), handles occasional slowness
```

[ASSUMED: based on typical RapidAPI response times; no official JSearch SLA published]

---

## 3. httpx Sync Client Pattern for JSearch

### Client Structure

```python
# app/sources/jsearch.py
import httpx
import logging
import os
from app.models.schemas import Job

logger = logging.getLogger(__name__)

JSEARCH_BASE = "https://jsearch.p.rapidapi.com/search"
JSEARCH_HOST = "jsearch.p.rapidapi.com"
DEFAULT_TIMEOUT = 20.0

def fetch_jsearch_query(
    query: str,
    *,
    date_posted: str = "3days",
    num_pages: int = 1,
    country: str = "es",
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch one JSearch query. Returns list of raw job dicts from data[].
    On 429 or network error: logs and returns []. Never raises.
    """
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": JSEARCH_HOST,
    }
    params = {
        "query": query,
        "page": "1",
        "num_pages": str(num_pages),
        "date_posted": date_posted,
        "country": country,
    }
    _client = client or httpx.Client(timeout=DEFAULT_TIMEOUT)
    try:
        resp = _client.get(JSEARCH_BASE, headers=headers, params=params)
        if resp.status_code == 429:
            logger.warning("JSearch 429 for query=%r — skipping", query)
            return []
        resp.raise_for_status()
        return resp.json().get("data", [])
    except httpx.HTTPError as exc:
        logger.warning("JSearch HTTP error for query=%r: %s", query, exc)
        return []
    finally:
        if client is None:  # we created it; close it
            _client.close()
```

[VERIFIED: httpx 0.28.1 installed; sync Client API confirmed; pattern derived from CONTEXT.md decisions]

### Multi-Query Loop (in pipeline)

```python
def _fetch_all(queries: list[str], settings: dict) -> list[dict]:
    """One httpx.Client shared across all queries in a run."""
    date_posted = settings.get("date_posted_override", "3days")
    country = settings.get("search_country", "es")
    num_pages = int(settings.get("num_pages", "1"))
    all_raw: list[dict] = []
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        for q in queries:
            raw = fetch_jsearch_query(q, date_posted=date_posted,
                                      num_pages=num_pages, country=country,
                                      client=client)
            logger.info("JSearch query=%r fetched=%d", q, len(raw))
            all_raw.extend(raw)
    return all_raw
```

Key: share one `httpx.Client` across queries in a single run (connection pool reuse, no per-query context manager overhead). Each query's errors are isolated inside `fetch_jsearch_query`.

### Mocking httpx for Tests

`respx` is not installed and not in `pyproject.toml`. Use `unittest.mock.patch` on the httpx response:

```python
# Pattern already used in project: monkeypatch + MagicMock
from unittest.mock import MagicMock, patch

def test_jsearch_429_isolation():
    mock_resp_429 = MagicMock()
    mock_resp_429.status_code = 429

    mock_resp_ok = MagicMock()
    mock_resp_ok.status_code = 200
    mock_resp_ok.raise_for_status = lambda: None
    mock_resp_ok.json.return_value = {"data": [{"job_title": "AI Engineer", ...}]}

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = [mock_resp_429, mock_resp_ok]
        # ... call fetch_all(["query1", "query2"])
        # query1 → 429 → returns []; query2 → ok → returns 1 job
```

**Option**: add `respx>=0.21` to `[dependency-groups] dev` for cleaner httpx mocking. The planner should decide; the `unittest.mock` approach works without new deps.

[VERIFIED: existing tests use `monkeypatch` + `MagicMock` pattern throughout]

---

## 4. APScheduler 3.11.2 BlockingScheduler — Correctness Confirmation

### Installed Version

APScheduler 3.11.2 is installed [VERIFIED: `pip show apscheduler`].

### worker.py Pattern — Verified Correct

The existing `worker.py` stub is correctly structured:

```python
scheduler = BlockingScheduler(
    timezone=ZoneInfo("Europe/Madrid"),
    job_defaults={
        "coalesce": True,          # if multiple fires accumulated, run only once
        "misfire_grace_time": 3600, # allow up to 1h late start
        "max_instances": 1,        # never run two pipeline instances in parallel
    },
)
scheduler.add_job(run_pipeline, "interval", hours=interval_hours, id="pipeline")
scheduler.start()
```

[VERIFIED: apscheduler.readthedocs.io/en/3.x/userguide.html; VERIFIED: installed version 3.11.2]

### Exception Behavior — Key Confirmation

**APScheduler 3.x does NOT crash the scheduler when a job raises an exception.** The executor catches exceptions, emits `EVENT_JOB_ERROR`, and logs the traceback. The BlockingScheduler continues running and will fire the job again on the next interval.

This is the correct behavior for Phase 8: if `run_pipeline()` raises (e.g., DB locked, unexpected error), the scheduler logs it and retries at next interval.

**Action required**: `run_pipeline()` should wrap its body in a broad try/except, log structured errors, and re-raise only if appropriate. For APScheduler's error logging, do NOT catch exceptions at the top of `run_pipeline` to suppress them silently — let them bubble to APScheduler's executor so `EVENT_JOB_ERROR` fires correctly and the error is logged with traceback.

[CITED: apscheduler.readthedocs.io/en/3.x/userguide.html; CITED: github.com/agronholm/apscheduler/issues/652]

### `max_instances=1` Behavior

When `max_instances=1` and the pipeline is still running from a previous firing, the new execution attempt is skipped (treated as a misfire). If within `misfire_grace_time`, it may run immediately after the first completes; if beyond `misfire_grace_time`, it is discarded. With `coalesce=True` and a 6h interval, this never happens in practice unless BGE-M3 loading takes > 6h.

[CITED: apscheduler.readthedocs.io/en/3.x/userguide.html]

### Note on APScheduler v4

Context7 returned v4 API snippets (AsyncScheduler, `add_schedule`). The project uses **v3.x** API (`BlockingScheduler`, `add_job`). Do not use v4 API patterns.

---

## 5. `runs` Table + Dedup-Against-Stored

### `runs` Table Schema

```sql
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    fetched     INTEGER DEFAULT 0,
    deduped     INTEGER DEFAULT 0,
    scored      INTEGER DEFAULT 0,
    new_seen    INTEGER DEFAULT 0,
    errors      TEXT    -- JSON array of error strings, or NULL
);
```

**Rationale:**
- `fetched`: total raw jobs returned by JSearch across all queries
- `deduped`: count after normalization + deduplication (unique jobs in this batch)
- `scored`: count actually sent to LLM scoring (= deduped minus already-in-DB)
- `new_seen`: count inserted as new rows in jobs table (not already present)
- `errors`: JSON list of error messages (per-query 429s, scoring failures, etc.) — nullable for clean runs

**Methods to add to SQLiteStorage + Protocol:**

```python
def record_run(
    self,
    *,
    started_at: str,
    finished_at: str,
    fetched: int,
    deduped: int,
    scored: int,
    new_seen: int,
    errors: list[str] | None = None,
) -> None: ...

def get_recent_runs(self, limit: int = 10) -> list[dict]: ...
```

### `mark_seen(job_id)` Implementation

The `jobs` table already has `seen INTEGER DEFAULT 0`. Add:

```python
def mark_seen(self, job_id: str) -> None:
    with closing(self._connect()) as conn:
        with conn:
            conn.execute("UPDATE jobs SET seen = 1 WHERE id = ?", (job_id,))
```

And extend Protocol:
```python
def mark_seen(self, job_id: str) -> None: ...
```

Note: Phase 8 adds the method + persistence. Phase 9 calls it after delivery. The pipeline in Phase 8 does NOT call `mark_seen` (seen=0 until notified).

### Dedup Against Already-Stored Jobs — Recommended Approach

**Simple and correct**: use `storage.was_seen(job.id)` after deduplication to partition the deduped batch into new vs already-stored:

```python
deduped_jobs = deduplicate(normalized, embedder=embedder)

new_jobs = []
already_stored_ids = set()
for job in deduped_jobs:
    if storage.was_seen(job.id):
        already_stored_ids.add(job.id)
    else:
        new_jobs.append(job)

# Score only new jobs
scored = [score_job(j, user_profile, cv_profile, embedder, client=llm_client)
          for j in new_jobs]

# Upsert all (new + re-seen) — upsert_scored_jobs is idempotent
# But only score new ones → scored count = len(new_jobs)
```

**Why this is sufficient**: `was_seen()` checks by stable ID (SHA-256 of company+title+location). The stable ID is cross-run deterministic, so a job from a previous run will have the same ID and be recognized without re-embedding against stored vectors. No vector store comparison needed. This matches the project's in-memory-per-run dedup philosophy.

**Edge case**: a job that changed score or description since last seen — the upsert will update `score_total`, `recommendation`, `score_json`, and `last_seen` but preserve `first_seen` and `seen`. The pipeline can choose to re-score already-stored jobs if desired, but the CONTEXT.md decision is to not re-score (saves LLM quota).

[VERIFIED: app/storage/sqlite.py `was_seen()` and `upsert_scored_jobs()` patterns]

### First-Run Detection

```python
def _is_first_run(storage: Storage) -> bool:
    """True if no jobs exist yet (empty DB = first run)."""
    history = storage.get_history(limit=1)
    return len(history) == 0
```

Use this to set `date_posted`: `"month"` on first run, `"3days"` thereafter.

---

## Architecture Patterns

### `app/pipeline.py` — Recommended Structure

```python
# app/pipeline.py
"""
Shared pipeline. NO imports of streamlit or apscheduler at module level.
Called by worker.py (scheduled) and UI (manual trigger, Phase 10).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class PipelineResult:
    fetched: int = 0
    deduped: int = 0
    scored: int = 0
    new_seen: int = 0
    errors: list[str] = field(default_factory=list)
    scored_jobs: list = field(default_factory=list)  # list[ScoredJob]

def run_pipeline(
    *,
    storage=None,   # Storage | None — if None, construct default
    embedder=None,  # Embedder | None — if None, construct BgeM3Embedder (heavy)
    llm_client=None,  # instructor client | None — if None, build from env
    profile_path=None,  # Path | None — for tests
) -> PipelineResult:
    ...
```

**Import discipline**: `app/pipeline.py` must never import `streamlit` or `apscheduler` at module level. The success criterion test is:

```python
def test_pipeline_no_streamlit_apscheduler():
    import sys
    # ensure clean state
    for mod in list(sys.modules.keys()):
        if "streamlit" in mod or "apscheduler" in mod:
            del sys.modules[mod]
    import app.pipeline  # noqa: F401
    assert "streamlit" not in sys.modules
    assert "apscheduler" not in sys.modules
```

### Project Structure (New Files)

```
app/
├── sources/
│   └── jsearch.py          # JSearch HTTP client (NEW)
├── pipeline.py             # Shared run_pipeline() (NEW)
├── storage/
│   ├── sqlite.py           # Add: runs table, record_run, get_recent_runs, mark_seen
│   └── protocol.py         # Add: record_run, get_recent_runs, mark_seen signatures
tests/
├── sources/
│   └── test_jsearch.py     # NEW: 429 isolation, multi-query, field mapping
├── test_pipeline.py        # NEW: pipeline integration, no-import test
├── storage/
│   └── test_runs.py        # NEW: record_run, get_recent_runs, mark_seen persistence
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| httpx response lifecycle | Manual connection mgmt | `with httpx.Client() as c:` | Automatic close + connection pool |
| APScheduler job isolation | Custom thread/exception wrapping | Let APScheduler's executor handle | It already catches, logs, emits EVENT_JOB_ERROR |
| Cross-run dedup by embedding | Vector search against all stored embeddings | `storage.was_seen(job.id)` hash check | Stable ID hash is sufficient; no vector DB needed |
| Job-level retry on 429 | Exponential backoff loop | Log + skip query | Monthly quota exhaustion makes retry counterproductive |

---

## Common Pitfalls

### Pitfall 1: Async Event Loop Inside BlockingScheduler

**What goes wrong**: if `run_pipeline` calls `asyncio.run()` or uses `await` without wrapping, and the BlockingScheduler runs it in a thread, a RuntimeError about "no running event loop" may appear inconsistently.

**Why it happens**: BlockingScheduler executes jobs in a ThreadPoolExecutor thread that has no running event loop.

**How to avoid**: use sync `httpx.Client` (already the CONTEXT.md decision). If any async function must be called, wrap with `asyncio.run()` at the call site inside the job body — do NOT use `asyncio.get_event_loop()`.

### Pitfall 2: httpx.Client Used After `with` Block Closes It

**What goes wrong**: sharing a client instance and accidentally closing it mid-loop.

**How to avoid**: the multi-query pattern in `_fetch_all()` creates one client in a `with` block and passes it to `fetch_jsearch_query` (which checks `if client is None` before closing). Only the outer `with` closes the connection.

### Pitfall 3: `was_seen()` Returns True for Jobs NOT Yet Scored

**What goes wrong**: `was_seen()` returns True if the row exists in the `jobs` table. But `upsert_scored_jobs()` inserts first. If the pipeline has a partial failure (normalized but not yet scored), a subsequent run won't score those jobs.

**How to avoid**: `upsert_scored_jobs()` is only called AFTER scoring. The pipeline scores first, then upserts. `was_seen()` on an existing row means it was scored+stored in a previous complete run. The upsert-before-score pattern would be the bug.

### Pitfall 4: `job_description` HTML Stripping (JSearch vs Arbeitnow)

**What goes wrong**: applying HTML stripping to JSearch descriptions (as done in arbeitnow_mapper).

**Why it's wrong**: JSearch returns plain text in `job_description`. The `jsearch_mapper` does NOT strip HTML, correctly. Applying `re.sub(r"<[^>]+>", " ", ...)` to plain text is harmless but unnecessary.

**Confirmed**: the test fixture confirms plain text: `"Build internal developer tooling."` with no HTML.

### Pitfall 5: `num_pages` Parameter as Integer vs String

**What goes wrong**: JSearch may expect numeric params as strings in the query string. httpx serializes integers correctly, but being explicit avoids surprises.

**How to avoid**: `str(num_pages)` in the params dict, matching the n8n workflow pattern.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `pytest tests/ -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SRC-01 | JSearch client fetches and returns raw data | unit | `pytest tests/sources/test_jsearch.py -x` | Wave 0 |
| SRC-02 | 429 on one query does not abort other queries | unit | `pytest tests/sources/test_jsearch.py::test_429_isolation -x` | Wave 0 |
| SRC-03 | jsearch_mapper field mapping correct | unit | `pytest tests/dedup/test_normalize.py -k jsearch -x` | EXISTS (5 tests) |
| SCHED-01 | worker.py runs without crashing (smoke) | smoke | `python worker.py &` — manual | Exists (stub) |
| SCHED-02 | run_pipeline() called on schedule (integration) | manual | Manual observation | N/A |
| SCHED-03 | run_pipeline exception does not kill scheduler | unit | `pytest tests/test_pipeline.py::test_exception_continues -x` | Wave 0 |
| STORE-05 | runs table created and record_run writes correct counts | unit | `pytest tests/storage/test_runs.py -x` | Wave 0 |
| STORE-07 | mark_seen persists seen=1 across storage restarts | unit | `pytest tests/storage/test_runs.py::test_mark_seen_persists -x` | Wave 0 |
| QA-06 | pipeline importable without streamlit/apscheduler | unit | `pytest tests/test_pipeline.py::test_no_streamlit_apscheduler -x` | Wave 0 |
| QA-06 | dedup-against-stored: prior-run job not re-scored | unit | `pytest tests/test_pipeline.py::test_dedup_against_stored -x` | Wave 0 |

### Mock Strategy Per Test

- **JSearch HTTP**: `unittest.mock.patch("app.sources.jsearch.httpx.Client")` — mock the Client class; configure `instance.get.return_value` with a MagicMock response. No `respx` needed.
- **Embedder**: inject `FakeEmbedder` (existing in `app/dedup/embedder.py`) — avoids 2-4GB BGE-M3 load.
- **LLM (scorer)**: inject `make_scoring_client(EXPECTED_ASSESSMENT)` from `tests/conftest.py` — existing pattern.
- **Storage**: `SQLiteStorage(str(tmp_path / "test.db"))` with `init_db()` — existing pattern from `tests/storage/test_sqlite.py`.

### Wave 0 Gaps

- [ ] `tests/sources/__init__.py` — new test subdirectory
- [ ] `tests/sources/test_jsearch.py` — covers SRC-01, SRC-02
- [ ] `tests/test_pipeline.py` — covers SCHED-03, QA-06 (import cleanliness, dedup-against-stored, exception propagation)
- [ ] `tests/storage/test_runs.py` — covers STORE-05, STORE-07

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| httpx | JSearch client | Yes | 0.28.1 | — |
| APScheduler | worker.py | Yes | 3.11.2 | — |
| RAPIDAPI_KEY env var | JSearch fetch | Not checked (secret) | — | Tests mock httpx; real key needed for integration |
| pytest | Tests | Yes | 9.0.3 | — |
| respx (optional) | httpx mocking | Not installed | — | Use unittest.mock.patch (existing pattern) |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | JSearch free tier is ~200 req/month (no retry-within-run strategy) | Section 2 | If higher (e.g. 500/month), retry logic would be viable and save runs |
| A2 | JSearch 429 response has no reliable Retry-After header | Section 2 | If Retry-After is present, a simple read-and-sleep would be easy to add |
| A3 | `date_posted="month"` and `"3days"` are valid enum values for JSearch | Section 2 | If values differ (e.g. "last_month", "last_3_days"), first run will error — verify with real call |
| A4 | `country="es"` filters to Spain-relevant jobs | Section 2 | May behave as "show jobs where country=es" not "show Spain-language jobs" — test with real key |
| A5 | Recommended timeout of 20s is sufficient for JSearch P95 | Section 2 | If API is slower, timeout errors will appear in logs; easily raised |

---

## Sources

### Primary (HIGH confidence)
- `tests/dedup/test_normalize.py` lines 231-248 — `_JSEARCH_JOB` fixture: raw field names verified against API shape (2026-05-23 comment in code)
- `app/dedup/mappers.py` lines 138-213 — existing `jsearch_mapper` implementation
- `docs/archive/n8n/n8n/workflow.json` — archived n8n workflow: confirmed JSearch headers, query params, response handling
- `app/storage/sqlite.py` — existing upsert/was_seen/settings patterns to mirror
- `worker.py` — existing BlockingScheduler scaffold to confirm correct
- `pip show apscheduler` — version 3.11.2 installed
- `pip show httpx` — version 0.28.1 installed
- APScheduler 3.x official docs (apscheduler.readthedocs.io/en/3.x/userguide.html) — BlockingScheduler behavior, exception handling, job defaults

### Secondary (MEDIUM confidence)
- openwebninja.com/api/jsearch — per-job field list (30+ fields confirmed including all used by mapper)
- dev.to/anuoluwapoae/job-search-api — top-level response envelope shape (`status`, `request_id`, `data`)

### Tertiary (LOW confidence / ASSUMED)
- JSearch free tier rate limits (~200 req/month) — WebSearch only; verify in RapidAPI account dashboard
- `date_posted` enum values — confirmed "month" and "3days" from n8n code comment, not official docs

---

## RESEARCH COMPLETE

**Phase:** 8 - JSearch Client & Worker Pipeline
**Confidence:** HIGH

### Key Findings

1. **Mapper is correct — no field changes needed.** The existing `jsearch_mapper` was already written against the raw JSearch API shape. All 5 mapper tests in `test_normalize.py` pass against a fixture that matches real API output. The STATE blocker from CONTEXT.md is resolved.

2. **Raw response envelope**: `{"status", "request_id", "parameters", "data": [...]}` — the client reads `resp.json().get("data", [])` and passes each element to `jsearch_mapper`.

3. **APScheduler 3.11.2 exception safety confirmed.** Job exceptions are caught by the executor, logged with traceback, and emit `EVENT_JOB_ERROR`. The scheduler continues. No wrapping needed inside `run_pipeline`.

4. **Dedup-against-stored is a hash check, not an embedding search.** `storage.was_seen(job.id)` is sufficient. No pgvector, no embedding comparison against stored rows.

5. **Three Wave 0 test files needed**: `tests/sources/test_jsearch.py`, `tests/test_pipeline.py`, `tests/storage/test_runs.py`. `tests/dedup/test_normalize.py` already covers SRC-03 (jsearch mapper).

### Files Created
`.planning/phases/08-jsearch-client-worker-pipeline/08-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| JSearch field mapping | HIGH | Verified against test fixture + n8n workflow + multiple web sources |
| JSearch request params | HIGH | Confirmed from archived n8n workflow + web sources |
| APScheduler behavior | HIGH | Official 3.x docs + installed version confirmed |
| Rate limits | LOW | No official JSearch limits page scraped; ASSUMED from general RapidAPI free tier |
| `date_posted` enum values | MEDIUM | n8n code comment + web sources; not official API reference |

### Open Questions
1. **`date_posted` values**: verify `"month"` and `"3days"` are exactly correct enum strings against a real JSearch response (make one test call with key). Low risk — wrong values produce 0 results, not an error.
2. **`country` param behavior**: confirm `"es"` filters to Spain jobs vs. Spanish-language jobs.
3. **`respx` vs `unittest.mock`**: planner should decide whether to add `respx` to dev deps for cleaner httpx test fixtures.

### Ready for Planning
Research complete. Planner can now create PLAN.md files.
