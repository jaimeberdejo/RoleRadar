---
phase: 06-architecture-cleanup-storage-foundation
plan: "04"
subsystem: database
tags: [sqlite, wal, busy_timeout, settings, concurrency, protocol]

requires:
  - phase: 06-01
    provides: "4 RED guard tests for WAL+busy_timeout and settings table (STORE-04, STORE-06)"

provides:
  - "WAL+busy_timeout on every SQLiteStorage connection via _connect()"
  - "settings table with 10 default config keys seeded idempotently in init_db()"
  - "get_settings() returning all settings as dict[str, str]"
  - "set_setting() upsert using ON CONFLICT DO UPDATE"
  - "Storage Protocol updated with get_settings and set_setting signatures"

affects:
  - phase7-scoring-refactor
  - phase8-worker-pipeline
  - phase10-streamlit-ui

tech-stack:
  added: []
  patterns:
    - "WAL+busy_timeout per-connection in _connect(): busy_timeout is connection-level, resets to 0 on each new connection — must be applied in _connect(), not init_db()"
    - "INSERT OR IGNORE for idempotent seeding of defaults; ON CONFLICT DO UPDATE for user-driven upserts"
    - "settings table as cross-process config bus: UI reads, worker reads+writes; values are opaque strings, callers convert types"

key-files:
  created: []
  modified:
    - app/storage/sqlite.py
    - app/storage/protocol.py

key-decisions:
  - "busy_timeout=5000 in _connect() (not init_db()): connection-level pragma resets to 0 on each new connection — placing it only in init_db() would leave all subsequent connections unprotected"
  - "INSERT OR IGNORE for init_db() seeding (never overwrites user-set values); ON CONFLICT DO UPDATE for set_setting() (always upserts)"
  - "Settings values stored as opaque strings; callers (phases 7-10) handle type conversion after retrieval"
  - "10 default keys cover search params, scoring weights, dedup threshold, and notification config"

patterns-established:
  - "WAL pattern: conn.execute('PRAGMA journal_mode=WAL;') + conn.execute('PRAGMA busy_timeout=5000;') in _connect() before returning connection"
  - "Settings upsert: INSERT INTO ... ON CONFLICT(key) DO UPDATE SET value = excluded.value (never INSERT OR REPLACE which destroys rowid)"

requirements-completed:
  - STORE-04
  - STORE-06

duration: 8min
completed: "2026-05-25"
---

# Phase 6 Plan 04: WAL+busy_timeout and Settings Table Summary

**SQLiteStorage gains WAL mode with per-connection busy_timeout=5000, a 10-key settings table, and get_settings/set_setting methods backed by parameterized upserts — all 14 storage tests GREEN.**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-05-25T13:00:00Z
- **Completed:** 2026-05-25T13:08:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Replaced `_connect()` with WAL+busy_timeout version (journal_mode=WAL + busy_timeout=5000, both applied per-connection)
- Extended `init_db()` to create settings table and seed 10 default config keys with INSERT OR IGNORE
- Added `get_settings()` and `set_setting()` methods following project read/write connection idioms
- Updated Storage Protocol class with `get_settings()` and `set_setting()` method signatures
- All 4 previously-RED guard tests (STORE-04, STORE-06) now GREEN; all 14 storage tests pass; 163 total tests GREEN

## Task Commits

Each task was committed atomically:

1. **Task 1: Update SQLiteStorage — WAL+busy_timeout, settings table, get_settings/set_setting** - `cfd2b2c` (feat)
2. **Task 2: Add get_settings and set_setting to Storage Protocol** - `c69038b` (feat)

**Plan metadata:** (final commit, see below)

## Files Created/Modified

- `app/storage/sqlite.py` - _connect() with WAL+busy_timeout; init_db() with settings table + seeding; get_settings() and set_setting() methods; updated docstring
- `app/storage/protocol.py` - get_settings() and set_setting() method signatures; updated class docstring

## Decisions Made

- busy_timeout=5000 placed in `_connect()` not `init_db()`: SQLite busy_timeout is a connection-level pragma that resets to 0 on every new connection. Placing it only in init_db() leaves all connections after the first one unprotected — the exact pitfall documented in RESEARCH.md.
- ON CONFLICT DO UPDATE in `set_setting()`: uses upsert semantics that never deletes/reinserts (preserves rowid integrity), while INSERT OR IGNORE is reserved only for idempotent seeding of defaults in `init_db()`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries introduced.

The plan's threat model mitigations were all applied:
- T-6-04-01 (SQL injection): set_setting() uses parameterized query `conn.execute("... VALUES (?, ?)", (key, value))` — no string formatting in SQL.
- T-6-04-03 (busy_timeout placement): PRAGMA busy_timeout=5000 is in _connect(), verified by grep count = 1.

## Next Phase Readiness

- WAL+busy_timeout foundation is in place — concurrent UI+worker DB access is safe
- settings table provides the cross-process config bus for phases 7-10
- get_settings() / set_setting() are ready for Streamlit UI (phase 10) to expose as config panel
- No blockers

---
*Phase: 06-architecture-cleanup-storage-foundation*
*Completed: 2026-05-25*
