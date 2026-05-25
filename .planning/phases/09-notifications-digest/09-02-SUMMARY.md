---
phase: 09-notifications-digest
plan: "02"
subsystem: storage
tags: [storage, sqlite, digest, notifications, migration]
dependency_graph:
  requires: [09-01]
  provides: [get_undelivered_qualifying, runs-channel-notified-migration]
  affects: [09-03, 09-04]
tech_stack:
  added: []
  patterns:
    - "PRAGMA table_info + ALTER TABLE for idempotent SQLite column migration"
    - "Parameterized IN clause via ','.join('?' * len(recs)) to prevent SQL injection"
    - "ScoredJob reconstruction from stored columns + score_json (description defaults to '')"
key_files:
  modified:
    - app/storage/sqlite.py
    - app/storage/protocol.py
decisions:
  - "f-string used only for the `({placeholders})` token (contains only `?`s), never for value interpolation — satisfies T-09-04"
  - "description defaults to '' in reconstructed Job (column not stored in jobs table; irrelevant for digest)"
  - "channel logged as non-secret enum string (T-09-03); never a token or password"
  - "PRAGMA check on runs_cols inside the same `with conn:` transaction block for atomicity"
metrics:
  duration_seconds: 155
  completed_date: "2026-05-25"
  tasks_completed: 2
  files_modified: 2
---

# Phase 9 Plan 02: Storage Extensions — Undelivered Query + Runs Schema Summary

SQLite storage extended with `get_undelivered_qualifying` (digest source per D-08/D-09)
and an idempotent PRAGMA-checked migration adding `channel` + `notified` to the runs table (D-14),
with `record_run` extended to persist both new columns.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add get_undelivered_qualifying to SQLiteStorage + Storage Protocol | b276eae | app/storage/sqlite.py, app/storage/protocol.py |
| 2 | Add runs channel/notified migration in init_db + extend record_run | 3fc7e98 | app/storage/sqlite.py, app/storage/protocol.py |

## What Was Built

### Task 1: get_undelivered_qualifying

New method on `SQLiteStorage` that returns `list[ScoredJob]` for jobs matching:
- `seen=0` (not yet delivered — D-08 seen/was_seen distinction)
- `recommendation IN (...)` (parameterized IN clause — T-09-04 SQL injection prevention)
- `score_total >= min_score`
- Ordered by `score_total DESC`

Each `ScoredJob` is fully reconstructed: `JobScore.model_validate_json(row["score_json"])` + `Job` from stored columns (description defaults to `""`). Corrupt `score_json` rows are skipped with `logger.warning` (T-09 isolation).

The method is also declared in the `Storage` Protocol with a matching one-line `...` stub and the docstring contract list updated.

### Task 2: runs table migration + record_run extension

In `init_db`, after `CREATE TABLE IF NOT EXISTS runs`, a PRAGMA-checked migration adds:
- `channel TEXT` — the notification channel name ("telegram"/"email"/None)
- `notified INTEGER DEFAULT 0` — count of jobs delivered in the run

The migration is fully idempotent: PRAGMA `table_info(runs)` is checked first; columns are only added if absent. Works on fresh DBs and on pre-existing DBs created before Phase 9.

`record_run` signature extended with two keyword-only params (`channel: str | None = None`, `notified: int = 0`) and the INSERT updated to include them. Logger updated to include both fields (safe: channel is a non-secret enum string, never a token).

`Storage` Protocol `record_run` stub updated with matching params.

## Tests Results

| Suite | Before | After |
|-------|--------|-------|
| tests/storage/test_undelivered.py | 5 FAILED (RED) | 5 PASSED |
| tests/notifications/test_notifications.py::test_runs_table_has_channel_notified | FAILED (RED) | PASSED |
| tests/storage/ (all) | 20 passed | 25 passed |
| Full suite (excl. app.notifications-dependent tests) | 259 passed | 264 passed |

Notification tests that require `app.notifications` remain RED — correct per wave plan (built in 09-03).

## Deviations from Plan

None — plan executed exactly as written.

## Threat Model Coverage

| Threat ID | Status |
|-----------|--------|
| T-09-04 (SQL injection via IN clause) | Mitigated: `",".join("?" * len(recommendations))` + bound params tuple |
| T-09-05 (min_score parameter) | Mitigated: typed `int`; passed as bound parameter |
| T-09-03 (record_run logging disclosure) | Mitigated: only channel name + counts logged, never tokens |

## Known Stubs

None — both methods are fully implemented with real behavior.

## Self-Check: PASSED

Files exist:
- FOUND: app/storage/sqlite.py
- FOUND: app/storage/protocol.py

Commits exist:
- FOUND: b276eae (feat(09-02): add get_undelivered_qualifying)
- FOUND: 3fc7e98 (feat(09-02): add runs channel/notified migration)
