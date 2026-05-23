---
phase: 04-api-y-persistencia
plan: "01"
subsystem: api-skeleton
tags: [fastapi, storage, protocol, dependency-injection, testing]
dependency_graph:
  requires: [app/models/schemas.py, app/config/loader.py, app/cv/cache.py, app/dedup/embedder.py]
  provides: [app/api/main.py, app/api/deps.py, app/storage/protocol.py, app/storage/sqlite.py, GET /health, GET /profile]
  affects: [tests/api/conftest.py, tests/api/test_health.py, tests/api/test_profile.py]
tech_stack:
  added: [fastapi>=0.128.0, uvicorn[standard]>=0.31.1, httpx>=0.28.1, python-multipart>=0.0.22]
  patterns: [lifespan-context-manager, dependency-overrides, runtime-checkable-protocol, deferred-imports-anti-torch]
key_files:
  created:
    - app/api/__init__.py
    - app/api/main.py
    - app/api/deps.py
    - app/api/routes/__init__.py
    - app/api/routes/profile.py
    - app/storage/__init__.py
    - app/storage/protocol.py
    - app/storage/sqlite.py
    - app/storage/supabase.py
    - tests/api/__init__.py
    - tests/api/conftest.py
    - tests/api/test_health.py
    - tests/api/test_profile.py
    - tests/storage/__init__.py
  modified:
    - pyproject.toml
decisions:
  - "uv add failed due to network unavailability; deps added directly to pyproject.toml with installed versions (fastapi 0.128.0 already in conda env)"
  - "sqlite.py and supabase.py created in Task 3 (not Plan 02) to unblock lifespan import in TestClient startup"
  - "test_profile.py placed in tests/api/test_profile.py (not test_health.py) per 04-PLAN-CHECK-RESOLUTIONS.md B2"
  - "FakeStorage is functional in-memory (not no-op): upsert_scored_jobs populates _seen set + _jobs list"
metrics:
  duration_minutes: 4
  tasks_completed: 3
  files_created: 14
  files_modified: 1
  completed_date: "2026-05-22"
---

# Phase 4 Plan 01: API Skeleton + Storage Protocol + Health/Profile Summary

FastAPI app importable torch-free in <0.2s, GET /health and GET /profile tested and green, Storage Protocol defined, SQLiteStorage complete, test infrastructure with functional FakeStorage and dependency_overrides teardown ready for Plans 02-04.

## What Was Built

### Task 1: Server deps + package init files
Added `fastapi>=0.128.0`, `uvicorn[standard]>=0.31.1`, `httpx>=0.28.1`, `python-multipart>=0.0.22` to `pyproject.toml`. Created six package `__init__` files: `app/api/`, `app/api/routes/`, `app/storage/`, `tests/api/`, `tests/storage/`. `app/storage/__init__.py` exports `Storage` and `get_storage_backend()` with deferred imports so the package is importable before sqlite.py/supabase.py exist (anti-circular, anti-torch pattern from Phase 3).

### Task 2: Storage Protocol + deps.py
`app/storage/protocol.py`: `@runtime_checkable class Storage(Protocol)` with four methods (`init_db`, `upsert_scored_jobs`, `was_seen`, `get_history`) — pure typing, zero numpy/torch. `app/api/deps.py`: six Depends providers, all with deferred imports inside function bodies (`# noqa: PLC0415`). `get_cached_cv_profile` reads `data/.cache/_current` pointer (written by `/cv/parse`, Plan 03) and raises HTTPException 404 with a message mentioning `/cv/parse`.

### Task 3: FastAPI app + routes + test infrastructure
`app/api/main.py`: `lifespan` async context manager selects SQLiteStorage or SupabaseStorage based on env vars at startup (deferred imports inside lifespan body, not at module level). `app/api/routes/profile.py`: sync `def` endpoints (not `async def`) for blocking file I/O — FastAPI runs them in its threadpool. `app/storage/sqlite.py`: complete SQLiteStorage with `ON CONFLICT(id) DO UPDATE` upsert, `check_same_thread=False`, Pydantic v2 JSON round-trip (`model_dump_json` / `model_validate_json`). `app/storage/supabase.py`: skeleton with `NotImplementedError`. `tests/api/conftest.py`: functional `FakeStorage` (upsert populates `_seen` + `_jobs`), `api_client` fixture resets `app.dependency_overrides = {}` after `yield` (Pitfall 7). Two test files: `test_health.py` and `test_profile.py` (per RESOLUTIONS.md B2 traceability).

## Test Results

```
tests/api/test_health.py    .    PASSED
tests/api/test_profile.py   ..   PASSED (2 tests)
Total: 3 passed
```

All acceptance criteria met:
- `uv run python -c "from app.api.main import app"` — completes in <0.2s, no torch
- `GET /health` → 200 `{"status": "ok"}`
- `GET /profile` → 200 with UserProfile (datos_personales present)
- `app.dependency_overrides` reset after each test
- Storage Protocol importable and runtime_checkable

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `uv add` failed due to network unavailability**
- **Found during:** Task 1
- **Issue:** `uv add fastapi "uvicorn[standard]" python-multipart httpx` failed with DNS error — PyPI unreachable.
- **Fix:** Added deps directly to `pyproject.toml` with versions already installed in the conda environment (fastapi 0.128.0, uvicorn 0.31.1, httpx 0.28.1, python-multipart 0.0.22). The plan specified minimum versions (e.g. `>=0.128.0`), which the installed versions satisfy.
- **Files modified:** `pyproject.toml`
- **Impact:** Functional equivalence — deps declared and available; `uv sync` will work when network is restored.

**2. [Rule 2 - Missing critical] `app/storage/sqlite.py` and `app/storage/supabase.py` created in Task 3 (not Plan 02)**
- **Found during:** Task 3 implementation
- **Issue:** `app/api/main.py`'s lifespan tries to import `SQLiteStorage` and `SupabaseStorage` when `TestClient` starts. Without these files the test infrastructure would fail to collect. Plan 02 was supposed to create them but this plan's tests needed them immediately.
- **Fix:** Created complete `SQLiteStorage` (implementing all four Protocol methods) and `SupabaseStorage` skeleton now, in Task 3. Plan 02 can add tests for SQLiteStorage without re-creating the files.
- **Files modified:** `app/storage/sqlite.py`, `app/storage/supabase.py`

### Out-of-Scope Pre-existing Issues

The following test failures in `tests/cv/` and `tests/scoring/` were pre-existing before this plan (missing `instructor` module in the conda environment). NOT caused by this plan — logged for awareness:

- `tests/cv/test_cache.py`, `test_llm_client.py`, `test_parser.py` — `ModuleNotFoundError: No module named 'instructor'`
- `tests/scoring/test_location.py`, `test_ranking.py`, `test_scorer.py`, `test_llm.py` — same

These failures existed before this plan's first commit (verified via `git stash`). Deferred to environment setup.

## Known Stubs

`app/storage/supabase.py` — `SupabaseStorage` methods raise `NotImplementedError`. Intentional: documented as "Fase 5" skeleton. The `FakeStorage` in tests provides zero-network coverage; SQLiteStorage handles all real persistence for v1. No stub affects the plan's goal (GET /health and GET /profile operational).

## Threat Flags

No new threat surface beyond the plan's threat model (T-04-01 through T-04-04). Confirmed mitigations in place:
- T-04-01: `get_cached_cv_profile` reads hash from `_current` (written by `/cv/parse` with `pdf_hash()`), never from user input directly.
- T-04-02: ANTHROPIC_API_KEY never referenced in source — SDK reads from env.
- T-04-03: `get_embedder` deferred import — torch never loads in tests.
- T-04-04: No auth — documented as accepted risk (personal tool, localhost).

## Self-Check: PASSED
