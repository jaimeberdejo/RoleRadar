---
phase: 09-notifications-digest
plan: "01"
subsystem: tests
tags: [tdd, red-guard, notifications, storage, wave-0]
dependency_graph:
  requires: []
  provides:
    - "tests/notifications/__init__.py — package init"
    - "tests/notifications/test_notifications.py — 13 RED guard tests (NOTIF-01/02/03, D-02, D-06, D-11, D-14)"
    - "tests/storage/test_undelivered.py — 5 RED guard tests (D-08, D-09)"
  affects:
    - "app/notifications (does not exist yet — Wave 1-2 must implement to pass these)"
    - "app/storage/sqlite.py (must add get_undelivered_qualifying in Wave 1)"
tech_stack:
  added: []
  patterns:
    - "RED-first TDD: all imports of app.notifications inside test functions to prevent collection errors"
    - "monkeypatch.setenv for all secrets — no real credentials committed"
    - "MagicMock context-manager pattern: patch httpx.Client and smtplib.SMTP via their module import path"
    - "tmp_path isolation: all storage tests use ephemeral SQLite DB, never data/jobs.db"
    - "Failure reason verification: AttributeError (storage) + ModuleNotFoundError (notifications)"
key_files:
  created:
    - tests/notifications/__init__.py
    - tests/notifications/test_notifications.py
    - tests/storage/test_undelivered.py
  modified: []
decisions:
  - "D-11 guard uses format_offer_block + chunk_offers in test body to replicate impl's block-to-chunk mapping, making the test self-consistent regardless of impl's internal ordering"
  - "40 jobs with padded reasons chosen for partial-chunk test to guarantee >=2 chunks at 4096 chars reliably"
  - "test_get_undelivered_qualifying* tests trigger AttributeError (not ImportError) — method absent on existing class is the correct RED mechanism for storage tests"
metrics:
  duration: "~4 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 0
---

# Phase 9 Plan 01: Wave 0 RED Guard Test Scaffolding Summary

Wave 0 RED guard test scaffolding for Phase 9 Notifications & Digest — 18 collectible failing tests locking the digest-source, channel-resolution, mark-seen-after-delivery, chunking, and partial-failure atomicity contracts before any implementation exists.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | tests/notifications package + 13 RED guard tests | 48875b9 | tests/notifications/__init__.py, tests/notifications/test_notifications.py |
| 2 | tests/storage/test_undelivered.py + 5 RED guard tests | 3607a9f | tests/storage/test_undelivered.py |

## What Was Built

### tests/notifications/test_notifications.py (13 tests)

Locks the following contracts:

| Test | Contract Locked | Req IDs |
|------|----------------|---------|
| test_format_offer_block | format_offer_block renders title/company/score/recommendation/reason/URL | NOTIF-01, D-05 |
| test_telegram_channel_sends_digest | send_digest(telegram) delivers all qualifying jobs, returns DigestResult | NOTIF-01 |
| test_email_channel_sends_digest | send_digest(email) delivers via SMTP, returns DigestResult | NOTIF-01 |
| test_channel_resolution_telegram_only | resolve_channel("auto") returns "telegram" when only TELEGRAM env set | NOTIF-02, D-03 |
| test_channel_resolution_email_only | resolve_channel("auto") returns "email" when only SMTP env set | NOTIF-02 |
| test_channel_resolution_none_silent | No channel → seen stays 0, no exception raised | NOTIF-02, D-10 |
| test_delivery_failure_leaves_seen_0 | HTTP error → seen=0, job reappears in next digest | NOTIF-03, D-10 |
| test_delivery_success_marks_seen_1 | HTTP 200 → seen=1, absent from next digest (restart isolation) | NOTIF-03, SC4 |
| test_qualifying_filter_excludes_maybe_low_score | maybe and below-threshold jobs excluded | NOTIF-03 |
| test_notifications_no_streamlit_apscheduler | import app.notifications loads no streamlit/apscheduler | D-02 |
| test_telegram_chunking_large_digest | chunk_offers: >=2 chunks, <=4096 each, no offer split | D-06 |
| test_runs_table_has_channel_notified | runs table has channel + notified columns after init_db | D-14 |
| test_telegram_partial_chunk_failure_marks_only_delivered | Later chunk 500 does NOT un-deliver earlier chunk's jobs (D-11 atomicity) | D-11, D-06 |

### tests/storage/test_undelivered.py (5 tests)

Locks the `SQLiteStorage.get_undelivered_qualifying(min_score, recommendations)` contract:

| Test | Contract Locked |
|------|----------------|
| test_get_undelivered_qualifying_returns_scoredjob_objects | Returns list[ScoredJob] with deserialized score_json (reasons_for populated) |
| test_get_undelivered_qualifying_filters_threshold | score_total < min_score excluded |
| test_get_undelivered_qualifying_filters_recommendation | recommendation not in list excluded |
| test_get_undelivered_qualifying_excludes_seen | seen=1 rows excluded (D-08: seen vs was_seen distinction) |
| test_get_undelivered_qualifying_orders_by_score_desc | Results ordered score_total DESC |

## Verification Results

```
python -m pytest tests/notifications/ tests/storage/test_undelivered.py --collect-only
# 18 tests collected — no collection errors

python -m pytest tests/notifications/ tests/storage/test_undelivered.py
# 18 failed — all RED for the right reasons:
#   notifications: ModuleNotFoundError: No module named 'app.notifications'
#   storage:       AttributeError: 'SQLiteStorage' object has no attribute 'get_undelivered_qualifying'

python -m pytest --tb=short
# 18 failed, 259 passed — pre-existing suite fully intact
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan creates test files only. No implementation stubs.

## Threat Flags

None — test files only. All env secrets set via `monkeypatch.setenv` with obviously-fake placeholder values (`test-token-fake`, `app-password-fake`). The T-09-01 threat mitigation verified: `grep -Ei '[0-9]{8,}:[A-Za-z0-9_-]{30,}' tests/notifications/test_notifications.py` returns nothing.

## Self-Check: PASSED

- [x] tests/notifications/__init__.py exists
- [x] tests/notifications/test_notifications.py exists with 13 tests
- [x] tests/storage/test_undelivered.py exists with 5 tests
- [x] Commit 48875b9 exists (Task 1)
- [x] Commit 3607a9f exists (Task 2)
- [x] 18 new tests collect without errors
- [x] 18 new tests fail RED (missing implementation, not collection failures)
- [x] 259 pre-existing tests still pass
