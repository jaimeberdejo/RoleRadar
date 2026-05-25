# Phase 9: Notifications & Digest - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 9-notifications-digest
**Mode:** --auto (Claude auto-selected the recommended option for each gray area)
**Areas discussed:** Module structure, Channel selection, Digest format, Delivery atomicity, Pipeline integration

---

## Module structure

| Option | Description | Selected |
|--------|-------------|----------|
| `app/notifications/` package | telegram.py + email_smtp.py + digest.py, matches modular layout | ✓ |
| Flat `app/notify.py` | Single module | |

**Auto-selection:** Package — consistent with cv/, dedup/, scoring/, sources/, storage/. Must stay import-clean (httpx + stdlib only).

---

## Channel selection

| Option | Description | Selected |
|--------|-------------|----------|
| Setting + env hybrid | `notification_channel` setting selects; secrets from env; "none"/auto falls back to env auto-detect | ✓ |
| Pure env auto-detect | Telegram if its env set, else SMTP, else silent | |
| Pure setting | Setting decides, ignore env presence | |

**Auto-selection:** Hybrid — satisfies SC1 (telegram env → telegram) and SC2 (only SMTP → email; neither → silent) while letting the Phase 10 UI override explicitly. Secrets env-only, never logged.

---

## Digest format

| Option | Description | Selected |
|--------|-------------|----------|
| Telegram: single combined message, chunk at 4096 | One notification; split on offer boundaries only when needed | ✓ |
| Telegram: one message per offer | Simpler but spammy on backfill runs (20+ pings) | |
| Email: plain text | Robust, no templating deps | ✓ |
| Email: HTML | Prettier but deferred to v2.x | |

**Auto-selection:** Combined Telegram digest (chunked) + plain-text email. Each offer: title, company, score, recommendation, top 2–3 reasons_for, URL.

---

## Delivery atomicity (the critical edge case)

| Option | Description | Selected |
|--------|-------------|----------|
| Digest source = DB query `get_undelivered_qualifying` (seen=0) | Decouples deliver-set from this-run scored-set; survives delivery failures + restarts | ✓ |
| Digest source = this run's `result.scored_jobs` | Breaks SC3: a failed-delivery job is already in DB, so next run's was_seen excludes it → never re-delivered | |
| Change `was_seen` to check seen=1 | Breaks dedup-against-stored; re-scores every undelivered job (wastes LLM) | |

**Auto-selection:** DB-query source. `was_seen` (existence) and the `seen` delivery flag are distinct concepts. mark_seen only after a successful channel call; silent skip does NOT mark seen (preserves backlog for when a channel is later configured).

---

## Pipeline integration

| Option | Description | Selected |
|--------|-------------|----------|
| `send_digest` called inside `run_pipeline()` (deferred import) | Worker + UI "Run now" both notify identically; pipeline stays import-clean | ✓ |
| Notify only in worker.py | UI "Run now" path wouldn't notify | |

**Auto-selection:** Inside run_pipeline as a final step, wrapped in try/except so a notification failure never aborts the run or crashes the worker.

---

## Claude's Discretion

- Telegram chunk-splitter signature; email MIME construction details.
- Whether `get_undelivered_qualifying` reuses existing row→ScoredJob deserialization.
- Retry policy on transient send errors (default: no retry in v2.0).
- Whether to extend `record_run` with `channel`/`notified` columns (default: yes, for UI-09).

## Deferred Ideas

- HTML email, multi-channel simultaneous delivery, send retry/backoff, Telegram inline action
  buttons, runs.notified surfaced in UI (Phase 10), salary in digest line (tied to SCORE-16).
