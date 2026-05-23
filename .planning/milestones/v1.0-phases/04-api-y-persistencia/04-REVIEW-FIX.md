---
phase: 04-api-y-persistencia
fixed_at: 2026-05-23T00:00:00Z
review_path: .planning/phases/04-api-y-persistencia/04-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 04: Code Review Fix Report

**Fixed at:** 2026-05-23T00:00:00Z
**Source review:** .planning/phases/04-api-y-persistencia/04-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, WR-01, WR-02, WR-03, IN-01, IN-03)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: Injected LLM client in `/cv/parse` is silently discarded

**Files modified:** `app/cv/parser.py`, `app/api/routes/cv.py`, `tests/api/test_cv.py`
**Commit:** 04f72e6
**Applied fix:** Option B. Added `client: "instructor.Instructor | None" = None` parameter to `parse_cv()`. When `client` is provided, it is used directly (skipping `build_instructor_client()`). The route now calls `parse_cv(pdf_bytes, client=client)` forwarding the Depends-injected client. Added `test_parse_cv_usa_cliente_inyectado` test that overrides `get_cv_llm_client` and asserts `mock_cv_client.messages.create.assert_called()`. Updated existing tests to remove now-redundant `patch("app.cv.parser.build_instructor_client")` wrappers since the injected client is used directly.

---

### WR-01: SQLite connections are never explicitly closed

**Files modified:** `app/storage/sqlite.py`
**Commit:** 53b24ad
**Applied fix:** Added `from contextlib import closing` import. Wrapped every `self._connect()` call with `closing(...)` as the outer context manager for connection lifetime. Inner `with conn:` is retained for commit/rollback transaction semantics. Applied to all four methods: `init_db`, `upsert_scored_jobs`, `was_seen`, `get_history`. Removed explicit `conn.commit()` from `init_db` and `upsert_scored_jobs` since `with conn:` handles commit on exit.

---

### WR-02: `get_user_profile_dep` is never overridden in test fixtures

**Files modified:** `tests/api/conftest.py`, `tests/conftest.py`
**Commit:** df93700
**Applied fix:** Added `EXPECTED_USER_PROFILE` module-level constant in `tests/conftest.py` (extracted from the `sample_user_profile` fixture body). Updated `sample_user_profile` fixture to return `EXPECTED_USER_PROFILE`. In `tests/api/conftest.py`, imported `get_user_profile_dep` and `EXPECTED_USER_PROFILE`, added `app.dependency_overrides[get_user_profile_dep] = lambda: EXPECTED_USER_PROFILE` to the `api_client` fixture. Tests no longer depend on `data/profile.yaml` being present on disk.

---

### WR-03: `test_process_ordena_por_score_total` cannot falsify the ordering property

**Files modified:** `tests/api/test_process.py`
**Commit:** 541e2e7
**Applied fix:** Added `_make_scoring_mock_with_skills(skills_values)` helper that creates a `MagicMock` with `side_effect` yielding `LLMJobAssessment` instances with the given `encaje_skills` values in order. The test overrides `get_scoring_llm_client` with this mock (values `[20, 90]`) and also overrides `get_embedder` with a hash-based `FakeEmbedder()` (no `default_vector`) to prevent deduplication of the two distinct offers. Added strict assertion `scores[0] > scores[-1]` so removing `sort()` in `process_jobs` would fail the test.

**Note:** requires human verification — the ordering property relies on the scoring pipeline and FakeEmbedder hash behavior both being deterministic. Logic is correct but classified as requires human verification per policy.

---

### IN-01: `GET /jobs/history` has no `response_model`

**Files modified:** `app/api/routes/jobs.py`
**Commit:** ca99401
**Applied fix:** Added `HistoryItem` Pydantic v2 model with fields: `id: str`, `title: str`, `company: str`, `score_total: int`, `recommendation: str`, `first_seen: str`, `last_seen: str`, `score: dict`. Changed `@router.get("/history")` decorator to `@router.get("/history", response_model=list[HistoryItem])` and updated return type annotation to `list[HistoryItem]`. n8n now has an OpenAPI contract for this endpoint.

---

### IN-03: `test_upsert_preserva_first_seen` does not assert `last_seen` was updated

**Files modified:** `tests/storage/test_sqlite.py`
**Commit:** 8a23e90
**Applied fix:** Captured `last_seen_after_first` after the first upsert. Increased `time.sleep` from 10ms to 20ms to ensure clock advances reliably. Added `assert row["last_seen"] > last_seen_after_first` after the second upsert. Both halves of STORE-02 are now verified: `first_seen` is preserved AND `last_seen` is updated.

---

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-05-23T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
