---
phase: 09-notifications-digest
plan: "05"
subsystem: pipeline-wiring-and-e2e-tests
tags: [pipeline, notifications, digest, telegram, smtp, e2e, record_run, send_digest]
dependency_graph:
  requires: [09-01, 09-02, 09-03]
  provides: [D-12, D-13, D-14, SC1, SC2, SC3, SC4, SC5]
  affects: [app/pipeline.py, tests/test_pipeline.py, tests/notifications/test_notifications.py]
tech_stack:
  added: []
  patterns:
    - "Deferred import inside try/except for notify failure isolation (D-13)"
    - "record_run after send_digest to capture channel+notified in single INSERT (D-14)"
    - "patch('app.notifications.send_digest') at package attribute for deferred-import testing"
key_files:
  modified:
    - app/pipeline.py
    - tests/test_pipeline.py
    - tests/notifications/test_notifications.py
    - .planning/phases/09-notifications-digest/09-VALIDATION.md
decisions:
  - "patch app.notifications.send_digest (not app.pipeline.send_digest) — deferred import resolves at the package level; patching the package attribute works correctly"
  - "SC4 simulates worker restart with a new SQLiteStorage(same db path) + init_db() — verifies persistence layer correctly marks seen=1"
  - "VALIDATION map covers corrected wave order (09-01=0, 09-02=1, 09-04=1, 09-03=2, 09-05=3) per plan frontmatter"
metrics:
  duration: "~10 min"
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_modified: 4
  tests_added: 8
  full_suite_count: 285
---

# Phase 9 Plan 05: Pipeline Wiring + SC1-SC4 End-to-End Tests Summary

**One-liner:** Wire send_digest as a deferred-import try/except step in run_pipeline with failure isolation, move record_run after digest to capture channel+notified, and prove all four success criteria (SC1-SC4) end-to-end.

---

## What Was Built

### Task 1 — `app/pipeline.py` wiring

Added step 10 (send_digest) and renumbered record_run to step 11 (after digest):

- **Step 10:** `from app.notifications import send_digest  # noqa: PLC0415` inside a `try/except Exception` block. On failure: logged, appended to `result.errors` as `"notify: {exc}"`. Pipeline still continues to record_run and returns normally (D-13).
- **Step 11:** `storage.record_run(...)` now accepts `channel=digest_channel, notified=digest_notified`. Both default to `None`/`0` if send_digest raised before producing a DigestResult (D-14).
- Import cleanliness preserved: `import app.pipeline` still pulls in no streamlit and no apscheduler.

### Task 2 — `tests/test_pipeline.py` pipeline-level tests

Three new tests added (total: 10 pipeline tests):

- `test_run_pipeline_notify_failure_does_not_abort` — D-13: RuntimeError from send_digest is caught; result returned; `any("notify:" in e ...)` true; runs row still written.
- `test_run_pipeline_records_channel_and_notified` — D-14: pre-seed one qualifying job + mock telegram 200 → runs row has `channel="telegram"` and `notified=1`.
- `test_run_pipeline_still_import_clean` — SC5 regression guard for the deferred send_digest wiring.

### Task 3 — `tests/notifications/test_notifications.py` SC1-SC4 e2e tests

Five new tests added (total: 18 notification tests):

- **SC1** `test_sc1_telegram_message_contains_required_fields` — captures `call_args.kwargs["json"]["text"]` from the mocked httpx POST; asserts title, company, score, recommendation, reason, and URL all present in the payload.
- **SC2a** `test_sc2_email_path_when_only_smtp` — only SMTP env set, `auto` channel → `channel="email"`, `send_message` called.
- **SC2b** `test_sc2_neither_channel_silent_no_mark` — no env set → `channel=None`, `delivered=0`, no exception, job stays `seen=0`.
- **SC3** `test_sc3_failure_keeps_job_for_next_run` — 400 response → `delivered=0`, job reappears; second call with 200 → delivered, absent from next query.
- **SC4** `test_sc4_success_absent_after_restart` — 200 response → `seen=1`; new `SQLiteStorage(same_path).init_db()` → `get_undelivered_qualifying` returns `[]`.

### `09-VALIDATION.md` — Per-Task Verification Map

Populated all 16 rows (09-01-T1 through 09-05-T3-SC4) with corrected wave assignments, requirement IDs, threat refs, secure behavior descriptions, and test type. Frontmatter set to `nyquist_compliant: true`, `wave_0_complete: true`. All validation sign-off checkboxes checked.

---

## Verification Results

```
python -m pytest -q
285 passed, 5 warnings in 5.77s
```

- Baseline was 277 tests; +8 new tests.
- `grep -c 'storage.record_run' app/pipeline.py` → 1 (single call, after digest).
- `import app.pipeline` → no streamlit, no apscheduler in sys.modules.
- All four SC tests green; D-11 multi-chunk guard (09-01 test) still present and green.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced by this plan. The `channel` value written to the runs table is a non-secret enum string (D-12 pattern: "telegram"/"email"/None + integer count). Inherits T-09-11 and T-09-12 mitigations as designed.

---

## Self-Check: PASSED

- `app/pipeline.py` modified and contains deferred send_digest import: FOUND
- `tests/test_pipeline.py` contains test_run_pipeline_notify_failure_does_not_abort: FOUND
- `tests/test_pipeline.py` contains test_run_pipeline_records_channel_and_notified: FOUND
- `tests/notifications/test_notifications.py` contains 5 SC tests (SC1/SC2a/SC2b/SC3/SC4): FOUND
- `09-VALIDATION.md` nyquist_compliant: true: FOUND
- Commits 1841d84, c8c42b8, 47e9a5c: FOUND
- Full suite: 285 passed
