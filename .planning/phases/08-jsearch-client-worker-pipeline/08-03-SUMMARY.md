---
phase: 08-jsearch-client-worker-pipeline
plan: "03"
subsystem: storage
tags: [sqlite, runs-table, mark-seen, STORE-05, STORE-07, wave-2]
dependency_graph:
  requires:
    - "08-01 (RED guard tests scaffolded)"
  provides:
    - "runs table in SQLite DB (STORE-05)"
    - "record_run / get_recent_runs for pipeline metrics"
    - "mark_seen for Phase 9 delivery tracking (STORE-07)"
  affects:
    - "app/pipeline.py (Wave 3, Plan 08-04) — will call record_run after each run"
    - "Phase 10 UI status panel — reads get_recent_runs"
    - "Phase 9 notifications — calls mark_seen after delivery"
tech_stack:
  added: []
  patterns:
    - "stdlib json for errors serialization in runs table"
    - "parameterized SQL for mark_seen (T-08-07 mitigation)"
    - "ORDER BY id DESC LIMIT ? pattern for get_recent_runs"
key_files:
  created: []
  modified:
    - app/storage/sqlite.py
    - app/storage/protocol.py
decisions:
  - "errors stored as JSON string in runs table; deserialized on read for caller convenience"
  - "mark_seen uses parameterized SQL ? — job_id is SHA-256 hash but param binding enforced per threat model T-08-07"
  - "get_recent_runs orders by id DESC (autoincrement = insertion order = chronological)"
  - "json import added at module level (stdlib, zero-cost)"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-25"
  tasks_completed: 2
  files_modified: 2
---

# Phase 8 Plan 03: Storage Extensions (runs table + mark_seen) Summary

**One-liner:** SQLite runs table with record_run/get_recent_runs/mark_seen via parameterized SQL and JSON-serialized errors, turning RED guard tests GREEN (5/5).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add runs table DDL to init_db() | 9016e64 | app/storage/sqlite.py |
| 2 | Add record_run, get_recent_runs, mark_seen to sqlite.py and protocol.py | 9016e64 | app/storage/sqlite.py, app/storage/protocol.py |

Note: Both tasks were committed together in a single atomic commit since Task 2 depended directly on the table created in Task 1.

## What Was Built

### runs table (STORE-05)

`init_db()` now creates a `runs` table alongside `jobs` and `settings`:

```sql
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    fetched     INTEGER DEFAULT 0,
    deduped     INTEGER DEFAULT 0,
    scored      INTEGER DEFAULT 0,
    new_seen    INTEGER DEFAULT 0,
    errors      TEXT
)
```

The `errors` column stores a JSON-serialized list of error strings (NULL when no errors). This keeps the schema simple (TEXT column, no separate errors table) while allowing the caller to receive a proper Python list.

### record_run / get_recent_runs (STORE-05)

`record_run(*, started_at, finished_at, fetched, deduped, scored, new_seen, errors=None)` inserts one row per pipeline run. `get_recent_runs(limit=10)` returns dicts ordered by `id DESC` — autoincrement id gives chronological order without relying on timestamp string comparison.

### mark_seen (STORE-07)

`mark_seen(job_id)` issues `UPDATE jobs SET seen = 1 WHERE id = ?` with a parameterized binding. The jobs table already had a `seen INTEGER DEFAULT 0` column (added in Phase 5). The method is a no-op for non-existent ids (UPDATE affects 0 rows, no exception).

### Protocol extended

`app/storage/protocol.py` now declares all three method signatures so type checkers and future alternative backends must implement them.

## Test Results

```
tests/storage/test_runs.py  5/5 PASSED
tests/storage/test_sqlite.py  14/14 PASSED
Total storage: 19/19 PASSED
```

Guards covered:
- `test_record_run_creates_row` — counts correctly stored and retrieved
- `test_record_run_with_errors` — errors stored as JSON, returned as list or str
- `test_get_recent_runs_ordering` — limit=2 returns 2 rows; most-recent first
- `test_mark_seen_sets_flag` — seen column transitions from 0 to 1
- `test_mark_seen_persists_across_restart` — seen=1 survives new SQLiteStorage instance on same file

## Deviations from Plan

None — plan executed exactly as written. Both tasks were batched into one commit (Task 2 directly builds on Task 1's DDL; splitting would create an intermediate broken state).

## Threat Surface Scan

No new network endpoints or auth paths introduced. Threat T-08-07 (SQL injection via mark_seen) is mitigated: `job_id` passed as parameterized `?` — no string interpolation into SQL. Documented in method docstring.

## Known Stubs

None — all methods fully implemented and verified by tests.

## Self-Check: PASSED

- app/storage/sqlite.py: FOUND (modified)
- app/storage/protocol.py: FOUND (modified)
- Commit 9016e64: FOUND in git log
- tests/storage/test_runs.py: 5/5 GREEN
- tests/storage/test_sqlite.py: 14/14 GREEN (no regressions)
