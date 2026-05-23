---
phase: 04-api-y-persistencia
reviewed: 2026-05-23T00:00:00Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - app/api/main.py
  - app/api/deps.py
  - app/api/routes/cv.py
  - app/api/routes/jobs.py
  - app/api/routes/profile.py
  - app/storage/protocol.py
  - app/storage/sqlite.py
  - app/storage/__init__.py
findings:
  critical: 1
  warning: 3
  info: 3
  total: 7
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-05-23T00:00:00Z
**Depth:** deep
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Cross-file deep review of the FastAPI layer (routes, deps, main) and the SQLite
persistence layer, against the test suite in `tests/api/` and `tests/storage/`.

The `/jobs/process` orchestration is structurally correct: `was_seen()` is called
before `upsert_scored_jobs()`, the normalize→dedup→score order is right, jobs that
fail scoring are excluded from the upsert, and the sort-by-`score_total` DESC
happens after persistence. The SQLite upsert with `ON CONFLICT` correctly preserves
`first_seen`. SQL parameters are parameterized throughout; no injection surfaces
were found.

One critical bug was found: the injected LLM client in `POST /cv/parse` is silently
discarded — `parse_cv()` does not accept a client argument and creates its own
internally. Three warnings cover connection resource management, a brittle test
dependency on a committed file, and a test that cannot actually falsify the ordering
property it claims to cover.

---

## Critical Issues

### CR-01: Injected LLM client in `/cv/parse` is silently discarded

**File:** `app/api/routes/cv.py:41,79`

**Issue:** `parse_cv_endpoint` accepts a `client: instructor.Instructor` via
`Depends(get_cv_llm_client)` and documents it as "inyectable (sobreescrito en tests)".
However, line 79 calls `parse_cv(pdf_bytes)` — `parse_cv` takes only `pdf_bytes`
(see `app/cv/parser.py:22`) and builds its own client via `build_instructor_client()`
internally when the cache misses. The injected `client` parameter is never forwarded.

Consequences:
1. `app.dependency_overrides[get_cv_llm_client]` has zero effect in `api_client` /
   `api_client_with_cv`. Any test that sends a real PDF and expects the mock client to
   handle the LLM call will instead trigger a live `Anthropic()` SDK instantiation.
2. The tests in `tests/api/test_cv.py` happen to pass only because they patch
   `app.cv.parser.build_instructor_client` directly (the right seam), not the
   FastAPI dependency. This masks the bug.
3. When Langfuse tracing is wired in (Fase 5), it will instrument the dep-injected
   client but the CV parsing LLM calls will be invisible.

**Fix:** Add a `client` parameter to `parse_cv` and thread it through, or remove the
`Depends(get_cv_llm_client)` from the route entirely since it is unused:

```python
# Option A — remove the unused Depends (simplest fix, consistent with current behavior):
# app/api/routes/cv.py
@router.post("/parse", response_model=CVProfile)
async def parse_cv_endpoint(
    file: UploadFile = File(..., description="CV en formato PDF"),
    # client param removed — parse_cv owns its own client via build_instructor_client()
) -> CVProfile:
    ...
    profile = parse_cv(pdf_bytes)
    ...

# Option B — thread the client through (enables dep injection):
# app/cv/parser.py
def parse_cv(pdf_bytes: bytes, client: instructor.Instructor | None = None) -> CVProfile:
    h = pdf_hash(pdf_bytes)
    cached = load_cached_profile(h)
    if cached is not None:
        return cached
    raw_text = extract_text_from_pdf(pdf_bytes)
    if client is None:
        client = build_instructor_client()
    profile = extract_cv_profile(raw_text, client)
    save_cached_profile(h, profile)
    return profile

# app/api/routes/cv.py
    profile = parse_cv(pdf_bytes, client=client)
```

Option B is preferred for Langfuse tracing and full dep-injection testability.

---

## Warnings

### WR-01: SQLite connections are never explicitly closed

**File:** `app/storage/sqlite.py:43-52,57,86,122,134`

**Issue:** `_connect()` opens a new `sqlite3.Connection` on every call. Each caller
uses the connection as a context manager (`with self._connect() as conn:`). Python's
`sqlite3` context manager commits or rolls back on exit — it does **not** close the
connection. Connections remain open until the CPython garbage collector collects them.

Under a threaded FastAPI request pool, each concurrent request to
`upsert_scored_jobs`, `was_seen`, or `get_history` opens a connection that lingers
until GC. For this personal single-user tool the impact is low, but the pattern is
incorrect: the documented intent is "connection-per-call" implying the connection is
released after use.

```python
# Current (leaks the connection):
with self._connect() as conn:
    rows = conn.execute(...).fetchall()
# conn still open here

# Fix — close explicitly:
def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    conn = self._connect()
    try:
        with conn:  # commit/rollback
            rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return rows

# Or use contextlib.closing:
from contextlib import closing

def was_seen(self, job_id: str) -> bool:
    with closing(self._connect()) as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row is not None
```

### WR-02: `get_user_profile_dep` is never overridden in test fixtures — tests depend on committed `data/profile.yaml`

**File:** `tests/api/conftest.py:91-99` (api_client fixture)

**Issue:** `api_client` overrides `get_storage`, `get_scoring_llm_client`,
`get_cv_llm_client`, and `get_embedder` — but **not** `get_user_profile_dep`. Every
`/jobs/process` and `/jobs/score` test that uses `api_client_with_cv` therefore calls
`load_user_profile()` for real, which reads `data/profile.yaml` from disk via a
`_PROJECT_ROOT`-relative path.

The tests currently pass only because `data/profile.yaml` is committed to the
repository. In a CI environment that runs from a different working directory, or if
the file is deleted/renamed, all process/score tests fail with HTTP 404 despite the
test description implying full isolation. This is a hidden environmental dependency.

```python
# Fix — add get_user_profile_dep to the overrides in api_client fixture:
# tests/api/conftest.py

from app.api.deps import (
    get_cached_cv_profile,
    get_cv_llm_client,
    get_embedder,
    get_scoring_llm_client,
    get_storage,
    get_user_profile_dep,          # add this import
)
from tests.conftest import ..., sample_user_profile_value  # a module-level UserProfile constant

# In api_client fixture:
app.dependency_overrides[get_user_profile_dep] = lambda: EXPECTED_USER_PROFILE

# Define EXPECTED_USER_PROFILE as a module-level constant in tests/api/conftest.py
# (can reuse the same values as the sample_user_profile fixture in tests/conftest.py).
```

### WR-03: `test_process_ordena_por_score_total` cannot falsify the ordering property

**File:** `tests/api/test_process.py:51-60`

**Issue:** The test sends `OFFER_AI` and `OFFER_ML` through `/jobs/process`. Both
are processed with the same `EXPECTED_ASSESSMENT` mock (returned by
`make_scoring_client`), which has fixed `encaje_skills=85` and `encaje_seniority=70`.
After the scoring pipeline, both jobs receive the same `score_total`. The assertion
`assert scores == sorted(scores, reverse=True)` is vacuously true when all values
are equal: `[X, X] == sorted([X, X], reverse=True)` is always `True` regardless of
the sort implementation. The test can never report a failure even if the `sort()` call
in `process_jobs` were removed entirely.

```python
# Fix — use a scoring mock that returns distinct scores per call:
from unittest.mock import MagicMock

def _make_score_mock_with_values(scores: list[int]):
    """Returns a scoring mock that yields successive score values."""
    from app.models.schemas import LLMJobAssessment
    mock = MagicMock()
    assessments = [
        LLMJobAssessment(
            razonamiento="test",
            puesto_detectado="AI Engineer",
            rango_puesto=1,
            encaje_skills=s,
            encaje_seniority=70,
            matched_skills=[],
            missing_requirements=[],
            reasons_for=[],
            reasons_against=[],
            deal_breaker_hit_texto=False,
        )
        for s in scores
    ]
    mock.messages.create.side_effect = assessments
    return mock

def test_process_ordena_por_score_total(api_client_with_cv):
    # Override scoring client to return 60 then 90 (OFFER_AI processed first)
    app.dependency_overrides[get_scoring_llm_client] = (
        lambda: _make_score_mock_with_values([60, 90])
    )
    body = _process_body(OFFER_AI, OFFER_ML)
    response = api_client_with_cv.post("/jobs/process", json=body)
    ...
    scores = [r["score"]["score_total"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > scores[-1], "Top score must be strictly greater than bottom"
```

---

## Info

### IN-01: `GET /jobs/history` has no `response_model` — no API contract for n8n

**File:** `app/api/routes/jobs.py:229`

**Issue:** The `@router.get("/history")` decorator has no `response_model`. FastAPI
serializes the `list[dict]` directly without validation. If `get_history` returns
an unexpected dict shape (e.g., during a schema migration), the API silently returns
malformed data without a 422. n8n consumers also get no OpenAPI schema for this
endpoint.

```python
# Define a response schema and declare it:
class HistoryItem(BaseModel):
    id: str
    title: str
    company: str
    score_total: int
    recommendation: str
    first_seen: str
    last_seen: str
    score: dict  # or JobScore if full reconstruction is desired

@router.get("/history", response_model=list[HistoryItem])
def history_endpoint(...) -> list[HistoryItem]:
    ...
```

### IN-02: `parse_cv()` in `parser.py` hard-wires its own LLM client — Langfuse tracing gap

**File:** `app/cv/parser.py:44`

**Issue:** `parse_cv` calls `build_instructor_client()` internally on every cache miss,
creating a client instance that is separate from the one tracked by the FastAPI
dependency graph. When Langfuse instrumentation is added in Fase 5, it will be wired
into the dep-injected clients in `deps.py` but will be invisible to the client
created here. CV parsing LLM calls will not appear in Langfuse traces.

This is a pre-existing design decision from Fase 2, and the client injection fix in
CR-01 (Option B) resolves it at the same time.

### IN-03: `test_upsert_preserva_first_seen` does not assert `last_seen` was updated

**File:** `tests/storage/test_sqlite.py:99-111`

**Issue:** The test correctly asserts that `first_seen` does not change on a second
upsert, but the comment "last_seen puede cambiar" implies the test trusts this
without asserting it. If the `ON CONFLICT` clause accidentally excluded `last_seen`
from the `DO UPDATE SET`, the test would still pass. The STORE-02 contract has a
dangling half.

```python
def test_upsert_preserva_first_seen(db: SQLiteStorage) -> None:
    db.upsert_scored_jobs([_make_scored_job("job-1")])
    first_seen_original = db.get_history()[0]["first_seen"]
    last_seen_after_first = db.get_history()[0]["last_seen"]

    time.sleep(0.02)  # ensure clock advances
    db.upsert_scored_jobs([_make_scored_job("job-1")])

    row = db.get_history()[0]
    assert row["first_seen"] == first_seen_original, "first_seen must not change"
    assert row["last_seen"] > last_seen_after_first, "last_seen must be updated on second upsert"
```

---

_Reviewed: 2026-05-23T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
