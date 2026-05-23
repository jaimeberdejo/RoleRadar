---
phase: 04-api-y-persistencia
plan: "02"
subsystem: database
tags: [sqlite, sqlite3, pydantic, storage, persistence, pytest, upsert, first_seen]

requires:
  - phase: 04-api-y-persistencia/04-01
    provides: Storage Protocol, SQLiteStorage skeleton, SupabaseStorage skeleton, get_storage_backend()

provides:
  - SQLiteStorage with init_db/upsert/was_seen/get_history (stdlib sqlite3, no SQLAlchemy)
  - ON CONFLICT(id) DO UPDATE upsert that preserves first_seen (T-04-07)
  - Path.mkdir(parents=True, exist_ok=True) in init_db for nested DB paths
  - SupabaseStorage skeleton implementing same Protocol (NotImplementedError)
  - tests/storage/test_sqlite.py with 10 tests covering STORE-01/02/03

affects:
  - 04-03 (FastAPI endpoints will wire get_storage_backend())
  - 05-integracion (Supabase implementation will replace skeleton)

tech-stack:
  added: []
  patterns:
    - "stdlib sqlite3 with connection-per-call (_connect) and check_same_thread=False for FastAPI threadpool safety"
    - "ON CONFLICT(id) DO UPDATE SET (not INSERT OR REPLACE) to preserve immutable columns"
    - "Pydantic v2 model_dump_json/model_validate_json for score_json round-trip"
    - "tmp_path fixture for SQLite integration tests (no disk state leaks)"

key-files:
  created:
    - tests/storage/test_sqlite.py
  modified:
    - app/storage/sqlite.py

key-decisions:
  - "Added Path.mkdir(parents=True, exist_ok=True) to init_db() — plan required it but 04-01 omitted it; prevents 'unable to open database file' for nested paths"
  - "10 tests cover all plan requirements: STORE-01 env selection, STORE-02 first_seen preservation and dates, STORE-03 was_seen and pagination, Pydantic round-trip, corrupt-row resilience"

patterns-established:
  - "SQLite upsert pattern: ON CONFLICT(id) DO UPDATE SET (never INSERT OR REPLACE)"
  - "Storage test pattern: SQLiteStorage(str(tmp_path / 'test.db')) + init_db() in fixture"
  - "score_json resilience: try/except per row in get_history, log warning + skip corrupt rows"

requirements-completed: [STORE-01, STORE-02, STORE-03]

duration: 15min
completed: 2026-05-23
---

# Phase 4 Plan 02: Storage Layer Tests Summary

**SQLiteStorage verified complete with 10 pytest tests covering upsert-ON-CONFLICT first_seen preservation, was_seen, paginated history, and Pydantic v2 JobScore round-trip — all STORE-01/02/03 requirements green**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-23T00:00:00Z
- **Completed:** 2026-05-23T00:15:00Z
- **Tasks:** 3 (verified 1-2 as already implemented, wrote Task 3 tests)
- **Files modified:** 2

## Accomplishments

- Verified `app/storage/sqlite.py` already satisfies all plan acceptance criteria from 04-01: stdlib sqlite3, `_connect()` with `check_same_thread=False`, `ON CONFLICT(id) DO UPDATE SET` (preserves first_seen), `model_dump_json`/`model_validate_json`, `was_seen`, `get_history` with corrupt-row resilience
- Added missing `Path(db_path).parent.mkdir(parents=True, exist_ok=True)` in `init_db()` — plan required it but was omitted in 04-01
- Verified `app/storage/supabase.py` and `app/storage/__init__.py` satisfy the plan exactly
- Wrote `tests/storage/test_sqlite.py` with 10 tests covering all STORE-01/02/03 requirements
- Full suite stays green: 145 passed (was 135)

## Task Commits

1. **Task 1-3: Storage verified + tests written** - `1b5f2f0` (feat)

**Plan metadata:** pending

## Files Created/Modified

- `tests/storage/test_sqlite.py` — 10 unit tests: upsert+was_seen, first_seen preservation, get_history dates+score, pagination, edge cases, corrupt-row skip, Pydantic round-trip, env-based backend selection
- `app/storage/sqlite.py` — Added `Path.mkdir(parents=True, exist_ok=True)` in `init_db()` and `from pathlib import Path`

## Decisions Made

- Verified existing storage code rather than recreating it — all plan criteria already met by 04-01 implementation, with one gap (mkdir) fixed
- Used `time.sleep(0.01)` in `test_upsert_preserva_first_seen` to guarantee `last_seen` can differ from `first_seen`; `first_seen` should remain stable regardless

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added Path.mkdir in init_db()**
- **Found during:** Task 1 verification
- **Issue:** `init_db()` called `sqlite3.connect(path)` without creating parent directories, causing `OperationalError: unable to open database file` for nested paths (e.g., `data/jobs.db` in a fresh repo)
- **Fix:** Added `Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)` at the start of `init_db()` and imported `pathlib.Path`
- **Files modified:** `app/storage/sqlite.py`
- **Verification:** Manual test with nested path succeeded after fix
- **Committed in:** `1b5f2f0`

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical functionality)
**Impact on plan:** Essential fix — without it, the service would fail to start with default `data/jobs.db` path in a clean checkout. No scope creep.

## Issues Encountered

None — storage implementation from 04-01 was essentially complete and correct. Tests wrote cleanly on first attempt.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Storage layer fully tested and verified; `get_storage_backend()`, `SQLiteStorage`, `SupabaseStorage` skeleton all ready
- FastAPI endpoints (04-03) can import `get_storage_backend()` and call `upsert_scored_jobs` / `was_seen` / `get_history`
- Supabase implementation remains deferred to 05-integracion (skeleton raises `NotImplementedError`)

---
*Phase: 04-api-y-persistencia*
*Completed: 2026-05-23*
