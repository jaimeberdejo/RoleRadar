---
phase: 09-notifications-digest
plan: "03"
subsystem: notifications
tags: [tdd, notifications, telegram, email, digest, wave-2, green]
dependency_graph:
  requires:
    - "09-01: RED test guard (tests/notifications/test_notifications.py)"
    - "09-02: storage.get_undelivered_qualifying + mark_seen + runs table extensions"
    - "09-04: python-telegram-bot removed from pyproject.toml"
  provides:
    - "app/notifications/__init__.py — send_digest + DigestResult public surface"
    - "app/notifications/digest.py — resolve_channel, format_offer_block, chunk_offers, build_subject, build_telegram_header"
    - "app/notifications/telegram.py — send_telegram_digest via raw httpx.Client POST"
    - "app/notifications/email_smtp.py — send_email_digest via smtplib STARTTLS"
    - ".env.example — SMTP_TO optional override documented"
  affects:
    - "app/pipeline.py — consumes send_digest in plan 09-05 (Wave 3)"
    - "app/storage/sqlite.py — consumed via storage.get_undelivered_qualifying + mark_seen"
tech_stack:
  added:
    - "httpx.Client (sync POST to Telegram Bot API) — already in deps, no new install"
    - "smtplib.SMTP + email.message.EmailMessage — stdlib, no new deps"
  patterns:
    - "app/sources/jsearch.py analog: httpx.Client context manager, env-read inside function, non-2xx isolation"
    - "app/pipeline.py analog: DigestResult dataclass (mirrors PipelineResult), deferred imports with # noqa: PLC0415"
    - "Per-chunk mark_seen: D-11 partial-failure atomicity — failed chunks leave jobs seen=0"
    - "Secret discipline: TELEGRAM_BOT_TOKEN/SMTP_PASSWORD read from env only, never logged"
key_files:
  created:
    - app/notifications/__init__.py
    - app/notifications/digest.py
    - app/notifications/telegram.py
    - app/notifications/email_smtp.py
  modified:
    - .env.example
decisions:
  - "Chunk→job_id re-pairing via `blocks[job_idx] in text` substring walk (chunk_offers preserves insertion order + never splits blocks — deterministic mapping)"
  - "Email body includes build_telegram_header + offer blocks; Subject is build_subject(n) count+date only (no attacker data in headers — T-09-08)"
  - "send_digest returns immediately with DigestResult(delivered=0) when no qualifying jobs or no channel — never raises (D-13 pipeline safety)"
  - "SMTP_TO commented in .env.example as optional self-send override (CLAUDE.md .env.example stays current)"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-25"
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 1
  tests_added: 0
  tests_green: 13
---

# Phase 09 Plan 03: Notifications Package (app/notifications/) Summary

**One-liner:** Digest delivery subsystem — raw httpx Telegram + smtplib email, per-chunk mark-seen atomicity (D-11), import-clean with deferred transports.

## What Was Built

The `app/notifications/` package is the post-pipeline delivery engine for Phase 9.
It queries the DB for undelivered qualifying jobs, resolves a channel from settings + env,
formats a plain-text digest, sends it, and marks each job `seen=1` only after its delivery
succeeds. The package imports only `httpx` + stdlib (D-02) — no streamlit, no apscheduler.

### Task 1 — digest.py (channel resolution + pure formatting helpers)

- `resolve_channel(settings)`: D-03 explicit/auto-detect logic; logs channel name only (never secrets)
- `format_offer_block(sjob)`: title @ company, score/100 (recommendation), top-3 reasons, URL as body text (SSRF guard comment — url never used as HTTP target)
- `chunk_offers(header, blocks)`: ≤4096-char chunks, header on first only, no offer split (D-06)
- `build_subject(n)`: BuscadorDeEmpleo email subject with count + DD/MM date
- `build_telegram_header(n)`: emoji header line for Telegram and email body

### Task 2 — telegram.py + email_smtp.py + .env.example

- `telegram.py`: `send_telegram_digest(chunks)` — `httpx.Client` POST to fixed `api.telegram.org` target; per-chunk delivered/errors return (D-11); token/chat_id from env inside function, never logged
- `email_smtp.py`: `send_email_digest(body, subject)` — `smtplib.SMTP` + ehlo/starttls/login/send_message; SMTP_TO optional override; attacker data in body only (T-09-08 header injection guard)
- `.env.example`: commented `SMTP_TO=` line added under the SMTP block

### Task 3 — __init__.py (send_digest orchestrator + DigestResult)

- `DigestResult` dataclass: `channel | None`, `delivered: int`, `errors: list[str]`
- `send_digest(storage, settings)`: D-10 sequence — query → empty check → resolve channel → send → mark_seen on success only; silent return (no mark_seen) when no channel
- `_send_telegram`: builds chunks with job_id pairing → `send_telegram_digest` → `mark_seen` only for returned `delivered_ids` (D-11 partial failure guaranteed)
- `_send_email`: formats body → `send_email_digest` in `try/except SMTPException` → `mark_seen` all on success
- Deferred imports (`# noqa: PLC0415`) keep module-level import clean

## Test Results

| Scope | Before | After |
|-------|--------|-------|
| tests/notifications/ | 13 FAILED (RED) | 13 PASSED (GREEN) |
| Full suite | 264 passed | 277 passed |

All 13 tests green including the two hardest:
- `test_notifications_no_streamlit_apscheduler`: import-cleanliness (D-02)
- `test_telegram_partial_chunk_failure_marks_only_delivered`: D-11 multi-chunk atomicity

## Deviations from Plan

None — plan executed exactly as written.

## Security Summary

| Threat | Mitigation | Status |
|--------|-----------|--------|
| T-09-06: secrets in logs | Token/password never referenced in log calls; verified via grep | MITIGATED |
| T-09-07: SSRF (Telegram URL) | POST target is fixed `TELEGRAM_BASE/bot{token}/sendMessage`; job.url is body text only; comment in code | MITIGATED |
| T-09-08: Email header injection | job data flows only through `msg.set_content(body)`; Subject is count+date only; EmailMessage rejects newline headers | MITIGATED |
| T-09-09: DoS via repeated failures | No retry in v2.0; failed jobs stay seen=0 for next run (low impact) | ACCEPTED |

## Self-Check

### Files exist
- [x] app/notifications/__init__.py
- [x] app/notifications/digest.py
- [x] app/notifications/telegram.py
- [x] app/notifications/email_smtp.py
- [x] .env.example contains SMTP_TO

### Commits exist
- [x] 67727ee — feat(09-03): create app/notifications/digest.py
- [x] 1202c03 — feat(09-03): add telegram.py + email_smtp.py + SMTP_TO
- [x] 777c0d5 — feat(09-03): implement send_digest orchestrator + DigestResult

## Self-Check: PASSED
