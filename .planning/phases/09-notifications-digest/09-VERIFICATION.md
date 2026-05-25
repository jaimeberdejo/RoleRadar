---
phase: 09-notifications-digest
verified: 2026-05-25T00:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 9: Notifications / Digest Verification Report

**Phase Goal:** After each pipeline run, new strong_fit/good_fit jobs above the configured threshold are delivered to a single chosen channel (Telegram or email) without duplicates; if no channel is configured, the run completes silently.
**Verified:** 2026-05-25
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: TELEGRAM env set → Telegram message sent per new qualifying offer with title, company, score, recommendation, top reasons, URL | VERIFIED | `test_sc1_telegram_message_contains_required_fields` captures `call_args.kwargs["json"]["text"]` and asserts all 6 fields present; passes in live suite (286 passed) |
| 2 | SC2: only SMTP set → email digest; neither set → silent completion, no error, log notes no channel | VERIFIED | `test_sc2_email_path_when_only_smtp` + `test_sc2_neither_channel_silent_no_mark`; `resolve_channel()` in digest.py returns "email" or None with info-level log; `send_digest` returns `DigestResult(channel=None, delivered=0)` with no exception |
| 3 | SC3: seen=1 set only after delivery succeeds; failed send leaves job seen=0 and reappears in next run | VERIFIED | `_send_telegram` calls `storage.mark_seen(jid)` only after `_post_chunk` returns True (200); `_send_email` calls `storage.mark_seen` only after `send_email_digest` returns without exception; `test_delivery_failure_leaves_seen_0` + `test_sc3_failure_keeps_job_for_next_run` both pass |
| 4 | SC4: a job delivered in a previous run never appears in a later digest, even after worker restart | VERIFIED | `get_undelivered_qualifying` filters `seen=0`; `test_delivery_success_marks_seen_1` and `test_sc4_success_absent_after_restart` construct a new `SQLiteStorage(same_path).init_db()` and assert `get_undelivered_qualifying` returns `[]`; both pass |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/notifications/__init__.py` | send_digest, DigestResult, _send_telegram, _send_email | VERIFIED | 145 lines; send_digest uses deferred imports for channel transports; mark_seen called only after successful delivery |
| `app/notifications/digest.py` | resolve_channel, format_offer_block, chunk_offers_with_indices, chunk_offers, build_subject, build_telegram_header | VERIFIED | 176 lines; chunk_offers_with_indices records block indices at construction time (CR-01 fix); all helpers pure string transforms |
| `app/notifications/telegram.py` | send_telegram_digest with per-chunk atomicity | VERIFIED | 95 lines; per-chunk mark_seen via delivered_ids list; httpx.Client (not python-telegram-bot); token never logged |
| `app/notifications/email_smtp.py` | send_email_digest via smtplib STARTTLS | VERIFIED | 66 lines; catches OSError + ssl.SSLError in addition to SMTPException (WR-01 fix applied in __init__.py) |
| `app/storage/sqlite.py` (get_undelivered_qualifying) | seen=0 query filtered by recommendation + min_score, ordered by score desc | VERIFIED | Lines 214-267; coerces min_score via int() defensively (WR-03 fix); SQL binds seen=0 AND recommendation IN (?) AND score_total >= ? |
| `app/pipeline.py` (send_digest wiring) | Deferred import in try/except; record_run AFTER digest | VERIFIED | Lines 246-274; `from app.notifications import send_digest  # noqa: PLC0415` inside try/except Exception at step 10; record_run is step 11 |
| `tests/notifications/test_notifications.py` | 19 tests covering all SC1-SC4 + D-02 + D-06 + D-11 + D-14 + CR-01 | VERIFIED | 19 tests collected and all pass |
| `tests/storage/test_undelivered.py` | 5 tests for get_undelivered_qualifying contracts | VERIFIED | 5 tests pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `app/pipeline.py:run_pipeline` | `app/notifications.send_digest` | Deferred import inside try/except Exception | WIRED | Line 249: `from app.notifications import send_digest  # noqa: PLC0415` |
| `send_digest` | `storage.get_undelivered_qualifying` | Direct method call | WIRED | Line 56: digest source is DB query (seen=0), NOT run's scored_jobs |
| `_send_telegram` | `chunk_offers_with_indices` | Import from digest.py | WIRED | Lines 96-99: index-based pairing eliminates substring re-pairing (CR-01) |
| `_send_telegram` | `storage.mark_seen` | Called per chunk_id after 200 | WIRED | Line 114: mark_seen called only for delivered_ids returned by send_telegram_digest |
| `_send_email` | `storage.mark_seen` | Called per job after send_email_digest returns | WIRED | Line 143: mark_seen called only after try/except succeeds |
| `run_pipeline` | `storage.record_run(channel=, notified=)` | After send_digest completes | WIRED | Lines 263-274: record_run called after digest; channel+notified default to None/0 if send_digest raised |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `send_digest` | `jobs` | `storage.get_undelivered_qualifying(min_score, ["strong_fit","good_fit"])` | YES — SQL query on jobs table, seen=0 filter | FLOWING |
| `format_offer_block` | `sjob.score.score_total`, `sjob.job.title`, etc. | ScoredJob deserialized from DB `score_json` column | YES — `JobScore.model_validate_json(row["score_json"])` | FLOWING |
| `send_telegram_digest` | `chunks` | `chunk_offers_with_indices(header, blocks)` with index pairing | YES — real block construction from job data | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green | `python -m pytest --tb=no 2>&1 \| tail -1` | `286 passed, 5 warnings in 4.47s` | PASS |
| app.notifications import-clean | `python -c "import app.notifications; assert 'streamlit' not in __import__('sys').modules"` | No assertion error | PASS |
| app.pipeline import-clean | `python -c "import app.pipeline; assert 'streamlit' not in __import__('sys').modules"` | No assertion error | PASS |
| python-telegram-bot absent from deps | `grep "python-telegram-bot" pyproject.toml` | No match (only `httpx>=0.28.1`) | PASS |
| CR-01 regression test passes | `python -m pytest tests/notifications/test_notifications.py::test_telegram_identical_blocks_partial_failure_pairs_by_index` | `1 passed` | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| NOTIF-01 | 09-01 through 09-05 | Digest of strong_fit/good_fit jobs per run (title, company, score, recommendation, top reasons, URL) | SATISFIED | format_offer_block renders all 6 fields; test_sc1_telegram_message_contains_required_fields verifies payload |
| NOTIF-02 | 09-01 through 09-05 | Telegram OR email per config; skip silently if neither; secrets only from env | SATISFIED | resolve_channel() in digest.py; tests 4/5/6 + SC2a/SC2b all pass; no hardcoded credentials anywhere |
| NOTIF-03 | 09-01 through 09-05 | Configurable min_score threshold; new jobs only (seen=0); mark seen only after delivery succeeds | SATISFIED | get_undelivered_qualifying filters seen=0 AND score >= threshold; mark_seen called post-delivery only; SC3/SC4 tests pass |

---

### Code Review Resolution

The 09-REVIEW.md reports status `resolved` with all 9 findings fixed. The critical finding (CR-01) was verified directly:

- **CR-01 (CRITICAL — D-11 violation):** Fixed. `_send_telegram` now calls `chunk_offers_with_indices` which returns `(text, list[int])` pairs captured at construction time. Pairing is done by index (`jobs[i].job.id for i in idxs`), not by substring matching. Regression test `test_telegram_identical_blocks_partial_failure_pairs_by_index` creates two byte-identical blocks in separate chunks, POSTs 200 then 500, and asserts first-chunk job is seen=1 and second-chunk job stays seen=0. Test passes.
- **WR-01:** Fixed. `_send_email` catches `(smtplib.SMTPException, OSError, ssl.SSLError)`.
- **WR-02:** Fixed. Post-condition guard logs if `assigned != len(jobs)`.
- **WR-03:** Fixed. `get_undelivered_qualifying` coerces `min_score` via `int()` at the storage boundary.
- **WR-04:** Fixed. `_post_chunk` guards `isinstance(body, dict)` before calling `.get()`.
- **IN-01 through IN-04:** Fixed (docstring corrections, smtplib import cleanup, control char stripping in format_offer_block, O(n) pairing via CR-01 fix).

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TODO/FIXME/placeholder/return null patterns found in notification modules | — | — |

Scanned: `app/notifications/__init__.py`, `app/notifications/digest.py`, `app/notifications/telegram.py`, `app/notifications/email_smtp.py`, `app/pipeline.py` (steps 10-11), `app/storage/sqlite.py` (get_undelivered_qualifying, mark_seen).

---

### Human Verification Required

None. All four success criteria are covered by automated tests that pass. The full test suite (286) is green with no failures. No visual or real-time behaviors require manual inspection for this phase.

---

## Gaps Summary

No gaps. All four roadmap success criteria are implemented, wired, and verified by passing tests.

---

_Verified: 2026-05-25_
_Verifier: Claude (gsd-verifier)_
