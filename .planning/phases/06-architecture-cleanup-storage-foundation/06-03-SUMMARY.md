---
phase: "06-architecture-cleanup-storage-foundation"
plan: "03"
subsystem: "infra/deps"
tags: ["fastapi-removal", "dependency-swap", "n8n-archive", "streamlit", "apscheduler"]
dependency_graph:
  requires: ["06-01"]
  provides: ["06-04", "06-05"]
  affects: ["pyproject.toml", "uv.lock", "docker-compose.yml"]
tech_stack:
  added: ["streamlit>=1.57.0", "apscheduler>=3.11.2,<4.0", "python-telegram-bot>=22.7"]
  removed: ["fastapi", "uvicorn", "python-multipart"]
  patterns: ["dependency-cap (apscheduler<4.0)", "two-service docker-compose (ui+worker)"]
key_files:
  deleted:
    - "app/api/__init__.py"
    - "app/api/auth.py"
    - "app/api/deps.py"
    - "app/api/main.py"
    - "app/api/routes/__init__.py"
    - "app/api/routes/cv.py"
    - "app/api/routes/jobs.py"
    - "app/api/routes/profile.py"
    - "tests/api/__init__.py"
    - "tests/api/conftest.py"
    - "tests/api/test_auth.py"
    - "tests/api/test_cv.py"
    - "tests/api/test_examples.py"
    - "tests/api/test_exception_handlers.py"
    - "tests/api/test_health.py"
    - "tests/api/test_jobs.py"
    - "tests/api/test_process.py"
    - "tests/api/test_profile.py"
  archived:
    - "n8n/workflow.json → docs/archive/n8n/n8n/workflow.json"
    - "docs/N8N-WORKFLOW.md → docs/archive/n8n/N8N-WORKFLOW.md"
  modified:
    - "pyproject.toml"
    - "uv.lock"
    - "docker-compose.yml"
decisions:
  - "APScheduler version capped at <4.0 — v4 is an incompatible async-only rewrite with no BlockingScheduler"
  - "docker-compose.yml restructured to two services (ui+worker) sharing one image; n8n service removed"
  - "RAPIDAPI_KEY literal removed from docker-compose.yml (was exposed in n8n service block); now injected via env_file only"
metrics:
  duration: "~15 min"
  completed: "2026-05-25"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
  files_deleted: 18
  files_archived: 2
---

# Phase 06 Plan 03: FastAPI Layer Removal & Dependency Swap Summary

**One-liner:** Decommission FastAPI/uvicorn/n8n architecture — deleted 18 files (app/api + tests/api), archived n8n artifacts, swapped pyproject.toml to streamlit + apscheduler + python-telegram-bot, fixed exposed RAPIDAPI_KEY in docker-compose.yml.

## What Was Done

### Task 1: Delete app/api/, tests/api/, archive n8n artifacts (commit: 782e463)

- Deleted `app/api/` entirely (8 files: main.py, auth.py, deps.py, routes/*.py)
- Deleted `tests/api/` entirely (10 files: conftest.py + 9 test files that imported fastapi.testclient)
- Created `docs/archive/n8n/` and moved n8n artifacts:
  - `n8n/workflow.json` → `docs/archive/n8n/n8n/workflow.json`
  - `docs/N8N-WORKFLOW.md` → `docs/archive/n8n/N8N-WORKFLOW.md`
- Updated `docker-compose.yml`: removed n8n service block (which contained exposed RAPIDAPI_KEY), removed n8n_data volume, restructured to v2.0 two-service pattern (ui + worker sharing one image)

### Task 2: Swap pyproject.toml deps and run uv sync (commit: 71e4ae9)

- Removed: `fastapi>=0.128.0`, `uvicorn[standard]>=0.31.1`, `python-multipart>=0.0.22`
- Added: `apscheduler>=3.11.2,<4.0`, `streamlit>=1.57.0`, `python-telegram-bot>=22.7`
- Ran `uv sync` — resolved 118 packages, installed 24 new, uninstalled 3 old
- APScheduler resolved at 3.11.2 (v3.x confirmed, cap `<4.0` enforced by resolver)

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| APScheduler version cap `<4.0` | v4 is an incompatible async-only rewrite — no BlockingScheduler, completely different API |
| docker-compose.yml two-service pattern | ui (Streamlit) and worker (APScheduler) share the same image but run as separate processes |
| RAPIDAPI_KEY removed from docker-compose.yml entirely | Was hardcoded in n8n service block; now injected via `env_file: .env` on both services |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Security] Removed exposed RAPIDAPI_KEY from docker-compose.yml**
- **Found during:** Task 1 (while removing the n8n service block)
- **Issue:** The n8n service block contained `RAPIDAPI_KEY: dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148` as a literal inline value, which caused `test_no_secrets.py` to fail
- **Fix:** Removed the entire n8n service block (it was the carrier of the exposed key), restructured docker-compose.yml to v2.0 two-service pattern (ui + worker) without any hardcoded secrets — all variables injected via `env_file: .env`
- **Files modified:** `docker-compose.yml`
- **Commit:** 782e463

## Known Stubs

None — this plan is a pure deletion/dependency swap. No new code was written with placeholder implementations.

## Pre-existing Test Failures (Out of Scope)

The full test suite has 3 pre-existing failures in `tests/storage/test_sqlite.py` (STORE-04, STORE-06 guards created in 06-01):

- `test_get_settings_defaults` — `SQLiteStorage` lacks `get_settings()` (implemented in 06-02)
- `test_set_setting_roundtrip` — `SQLiteStorage` lacks `set_setting()` (implemented in 06-02)
- `test_wal_mode_activo` — SQLite journal not in WAL mode yet (WAL pragma added in 06-02)

These failures existed before this plan and are intentionally failing Wave 0 guards (TDD-style) that drive 06-02's implementation. They are not introduced by 06-03.

## Threat Surface Scan

No new network endpoints or auth paths were introduced. The plan REMOVED surfaces:
- `app/api/auth.py` (X-API-Key authentication) — removed; no HTTP listener in v2.0 Streamlit
- n8n service (port 5678) — removed from docker-compose.yml

## Self-Check

### Files exist:
- `docs/archive/n8n/N8N-WORKFLOW.md` — FOUND
- `docs/archive/n8n/n8n/workflow.json` — FOUND
- `app/errors.py` (must NOT be deleted) — FOUND
- `pyproject.toml` has `apscheduler>=3.11.2,<4.0` — FOUND

### Directories deleted:
- `app/api/` — DELETED (does not exist)
- `tests/api/` — DELETED (does not exist)

### Commits exist:
- 782e463 — Task 1 (delete + archive)
- 71e4ae9 — Task 2 (dep swap)

## Self-Check: PASSED
