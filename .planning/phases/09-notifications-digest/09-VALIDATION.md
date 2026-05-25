---
phase: 9
slug: notifications-digest
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-25
updated: 2026-05-25
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml ([tool.pytest.ini_options]) |
| **Quick run command** | `python -m pytest tests/notifications/ tests/storage/ -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~7 seconds (287 tests after Phase 9) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/notifications/ tests/storage/ -q`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-T1 | 09-01 | 0 | NOTIF-01/02/03, D-05, D-06, D-10, D-11, D-14 | T-09-04, T-09-06, T-09-07, T-09-08 | Digest renders title/company/score/rec/reasons/URL; mark_seen only on success; multi-chunk partial failure marks only delivered (D-11) | unit | `python -m pytest tests/notifications/ -q` | ✅ | ✅ green |
| 09-01-T2 | 09-01 | 0 | NOTIF-03, D-08 | T-09-08 | get_undelivered_qualifying returns only seen=0, above threshold, qualifying recommendations | unit | `python -m pytest tests/storage/test_undelivered.py -q` | ✅ | ✅ green |
| 09-02-T1 | 09-02 | 1 | D-08 | — | get_undelivered_qualifying: seen=0 filter, score threshold, recommendation filter | unit | `python -m pytest tests/storage/ -q` | ✅ | ✅ green |
| 09-02-T2 | 09-02 | 1 | D-14 | — | runs table has channel + notified columns; record_run accepts channel/notified kwargs | unit | `python -m pytest tests/storage/test_runs.py -q` | ✅ | ✅ green |
| 09-03-T1 | 09-03 | 2 | NOTIF-01, D-05 | T-09-04 | format_offer_block renders all required fields (title/company/score/rec/reason/URL) | unit | `python -m pytest tests/notifications/test_notifications.py::test_format_offer_block -q` | ✅ | ✅ green |
| 09-03-T2 | 09-03 | 2 | NOTIF-02, D-03 | — | resolve_channel: telegram if TELEGRAM env; email if SMTP env; None if neither | unit | `python -m pytest tests/notifications/ -k "channel_resolution" -q` | ✅ | ✅ green |
| 09-03-T3 | 09-03 | 2 | NOTIF-01, NOTIF-03, D-10 | T-09-06, T-09-07 | send_digest delivers via telegram; delivery failure leaves seen=0; success marks seen=1 | unit | `python -m pytest tests/notifications/ -q` | ✅ | ✅ green |
| 09-03-T4-D11 | 09-03 | 2 | D-11 | T-09-07 | Multi-chunk partial failure: later chunk 500 does NOT un-deliver first chunk's jobs | unit | `python -m pytest tests/notifications/test_notifications.py::test_telegram_partial_chunk_failure_marks_only_delivered -q` | ✅ | ✅ green |
| 09-04-T1 | 09-04 | 1 | D-02 | — | python-telegram-bot removed from pyproject.toml; PTB never imported at module level | unit | `python -m pytest tests/test_no_ptb.py -q` | ✅ | ✅ green |
| 09-05-T1 | 09-05 | 3 | D-12, D-13, D-14 | T-09-11 | run_pipeline wires send_digest as deferred-import step; notify failure caught → errors; record_run after digest with channel+notified | unit | `python -m pytest tests/test_pipeline.py -q` | ✅ | ✅ green |
| 09-05-T2 | 09-05 | 3 | D-12, D-13, D-14 | T-09-11, T-09-12 | notify failure does not abort pipeline; run row written; channel+notified in runs row; import clean (SC5 regression) | unit | `python -m pytest tests/test_pipeline.py -q` | ✅ | ✅ green |
| 09-05-T3-SC1 | 09-05 | 3 | NOTIF-01, SC1 | T-09-04 | Telegram message contains title/company/score/rec/reason/URL for each qualifying offer | e2e | `python -m pytest tests/notifications/test_notifications.py::test_sc1_telegram_message_contains_required_fields -q` | ✅ | ✅ green |
| 09-05-T3-SC2a | 09-05 | 3 | NOTIF-02, SC2 | — | smtp-only env → email channel selected and send_message called | e2e | `python -m pytest tests/notifications/test_notifications.py::test_sc2_email_path_when_only_smtp -q` | ✅ | ✅ green |
| 09-05-T3-SC2b | 09-05 | 3 | NOTIF-02, SC2 | — | neither channel → silent, no exception, job stays seen=0 | e2e | `python -m pytest tests/notifications/test_notifications.py::test_sc2_neither_channel_silent_no_mark -q` | ✅ | ✅ green |
| 09-05-T3-SC3 | 09-05 | 3 | NOTIF-03, SC3, D-10 | T-09-07 | failure leaves seen=0; job reappears next run; retryable (second send delivers) | e2e | `python -m pytest tests/notifications/test_notifications.py::test_sc3_failure_keeps_job_for_next_run -q` | ✅ | ✅ green |
| 09-05-T3-SC4 | 09-05 | 3 | NOTIF-03, SC4 | T-09-07 | success marks seen=1; absent from next digest after simulated restart (new SQLiteStorage instance) | e2e | `python -m pytest tests/notifications/test_notifications.py::test_sc4_success_absent_after_restart -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/notifications/` — package + RED guard stubs for NOTIF-01/02/03 (digest filter, channel resolution, mark-seen-after-delivery)
- [x] `tests/storage/test_undelivered.py` — guard for `get_undelivered_qualifying`
- [x] Existing pytest infrastructure covers the rest (no framework install needed)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Telegram message renders correctly in the Telegram app | NOTIF-01 | Requires a live bot token + chat; auto-tests mock the HTTP layer | Set TELEGRAM_BOT_TOKEN/CHAT_ID, trigger a run with ≥1 qualifying job, confirm the message arrives with title/company/score/reasons/URL |
| Real SMTP email arrives + renders | NOTIF-02 | Requires live SMTP creds; auto-tests mock smtplib | Set SMTP_* (no Telegram), trigger a run, confirm the digest email arrives |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete (2026-05-25, all 287 tests green)
