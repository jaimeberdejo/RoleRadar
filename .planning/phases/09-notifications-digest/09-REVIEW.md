---
phase: 09-notifications-digest
reviewed: 2026-05-25T00:00:00Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - app/notifications/__init__.py
  - app/notifications/digest.py
  - app/notifications/telegram.py
  - app/notifications/email_smtp.py
  - app/storage/sqlite.py
  - app/storage/protocol.py
  - app/pipeline.py
findings:
  critical: 1
  warning: 4
  info: 4
  total: 9
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-05-25
**Depth:** deep (cross-file call-chain analysis)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 9 adds an `app/notifications/` package (digest formatting, Telegram via raw
httpx, email via stdlib smtplib STARTTLS), a new `get_undelivered_qualifying` storage
query, and wiring into `run_pipeline()`. I verified each of the seven stated invariants
by tracing the call chain `run_pipeline → send_digest → _send_telegram/_send_email →
storage.mark_seen` and by executing the chunking/re-pairing logic against adversarial
inputs.

**The good news (invariants that hold):**
- **Secret handling (#1):** Verified empirically — the bot token only ever lives in the
  local `url` variable, which is never logged nor placed in an error string. All
  `logger.*` / `errors.append` sites carry only `str(exc)`, status codes, API
  `description`, or the (non-secret) `to_addr`. Confirmed `httpx.HTTPError` and
  `smtplib.SMTPException` string representations do not embed the token or password.
- **SSRF / URL injection (#2):** The Telegram POST target is a fixed
  `f"{TELEGRAM_BASE}/bot{token}/sendMessage"`; job URLs flow only into the JSON `text`
  body. No attacker data reaches the request target.
- **Email header injection (#3):** Subject is `build_subject(n)` (count + date only);
  To/From are env-derived; job data reaches only `msg.set_content(body)`. Clean.
- **SQL correctness (#5):** `get_undelivered_qualifying` uses parameter binding for
  both the dynamic `IN (...)` clause and `score_total >= ?`; filters `seen=0` correctly.
- **Pipeline resilience (#6):** `send_digest` is wrapped in `try/except Exception` in
  `run_pipeline`, and `record_run` still fires afterward — the worker cannot crash from
  a notify failure.

**The blocker:** the per-chunk `mark_seen` re-pairing in `_send_telegram` reconstructs
which job IDs belong to which Telegram chunk using fragile substring matching
(`blocks[job_idx] in text`). With identical or substring-related offer blocks — which
real cross-run data can produce — this misassigns job IDs across chunks, breaking the
D-11 delivery guarantee (jobs marked seen on a chunk that failed, or never marked seen
after a successful send). The existing tests only use unique block text and never hit it.

## Critical Issues

### CR-01: Telegram chunk→job-id re-pairing breaks on identical/substring offer blocks (D-11 violation)

**File:** `app/notifications/__init__.py:94-106`

**Issue:** `_send_telegram` does not know which job IDs landed in which chunk, so it
reconstructs the mapping after the fact:

```python
job_idx = 0
for text in chunk_texts:
    ids_here: list[str] = []
    while job_idx < len(jobs) and blocks[job_idx] in text:   # substring match
        ids_here.append(jobs[job_idx].job.id)
        job_idx += 1
    chunks.append((text, ids_here))
```

The `blocks[job_idx] in text` substring test is not a sound way to recover chunk
membership. Two failure modes, both reproduced by executing the real `chunk_offers`
logic:

1. **Identical blocks across chunks.** Two qualifying jobs with the same display fields
   (title, company, score, recommendation, top-3 reasons, URL) produce byte-identical
   blocks. This is realistic: `get_undelivered_qualifying` pulls jobs across runs, and a
   re-listed posting can have a different `id` hash (e.g. location differs) yet identical
   digest text. When block N (which actually lives in chunk 1) is also a substring of
   chunk 0, the `while` loop over-consumes: chunk 0 receives ALL the IDs and chunk 1
   receives `[]`. Verified output for 3 identical blocks spanning 2 chunks:
   `chunk0 → ['a','b','c']`, `chunk1 → []`.

2. **Substring-related blocks.** A short block (e.g. `"AI Engineer @ Corp"`) is a
   substring of a longer block (`"Senior AI Engineer @ Corp ..."`). Same over-consume
   result: `[['a','b','c'], []]`.

**Concrete consequences (both break the phase's core delivery guarantee):**
- If chunk 0 returns 200 but chunk 1 returns 500, the over-assigned IDs are added to
  `delivered_ids` and `storage.mark_seen()` is called on them — **jobs whose delivery
  actually failed are marked seen and silently dropped from all future digests** (the
  exact data-loss scenario D-11/SC3 exist to prevent).
- Conversely, if the loop fails to advance `job_idx` for a block that is not found in any
  chunk, later jobs are never assigned to any chunk, so after a fully successful send they
  stay `seen=0` and get re-notified every run.

**Fix:** Track block→chunk membership at chunk-construction time instead of reverse-
engineering it. Have `chunk_offers` (or a parallel helper) return the index ranges, then
pair IDs by position:

```python
# digest.py — return which block indices each chunk contains
def chunk_offers_with_indices(
    header: str, offer_blocks: list[str]
) -> list[tuple[str, list[int]]]:
    chunks: list[tuple[str, list[int]]] = []
    current, idxs = header, []
    for i, block in enumerate(offer_blocks):
        candidate = current + "\n\n" + block
        if len(candidate) > TELEGRAM_MAX_CHARS and current != header and current:
            chunks.append((current, idxs))
            current, idxs = block, [i]
        else:
            current, idxs = candidate, idxs + [i]
    if current:
        chunks.append((current, idxs))
    return chunks

# __init__.py — pair by index, never by substring
paired = chunk_offers_with_indices(header, blocks)
chunks = [(text, [jobs[i].job.id for i in idxs]) for text, idxs in paired]
```

Add a regression test using two byte-identical blocks (or a block that is a substring of
another) split across ≥2 chunks where the second chunk returns 500, asserting the
second-chunk job stays `seen=0` and the first-chunk job is `seen=1`.

## Warnings

### WR-01: `_send_email` only catches `smtplib.SMTPException`; connection/TLS errors escape `send_digest`

**File:** `app/notifications/__init__.py:119-124`, `app/notifications/email_smtp.py:52-56`

**Issue:** `send_email_digest` connects via `smtplib.SMTP(host, port)`, then
`starttls()`, then `login()`. Connection failures raise `socket.gaierror` / `OSError` /
`TimeoutError`, and `starttls()` can raise `ssl.SSLError` — **none of these subclass
`smtplib.SMTPException`** (verified: `gaierror`, `OSError`, `ssl.SSLError`,
`TimeoutError` all return `False` for `issubclass(..., SMTPException)`). The handler in
`_send_email` catches only `smtplib.SMTPException`, so a DNS/connection/TLS failure
propagates out of `_send_email` → out of `send_digest`, directly contradicting the
module contract "Never raises (callable from run_pipeline's try/except — D-13)".

The worker still survives because `run_pipeline` wraps `send_digest` in
`try/except Exception`, but the structured `DigestResult.errors` reporting is bypassed
(the failure surfaces as a generic `notify: {exc}` instead), and the invariant the file
documents is false. A bad `SMTP_HOST` (a likely user misconfiguration) triggers this.

**Fix:** Broaden the catch in `_send_email` to also cover transport-level errors:

```python
import socket, ssl  # noqa: PLC0415
try:
    send_email_digest(body, subject)
except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
    logger.error("Email delivery failed: %s", exc)
    result.errors.append(f"email: {exc}")
    return
```

(`socket.gaierror` and `TimeoutError` are both subclasses of `OSError`, so `OSError`
covers them.) Update `send_email_digest`'s docstring accordingly — it currently claims it
"Raises smtplib.SMTPException on failure", which understates the real failure surface.

### WR-02: `_send_telegram` re-pairing is silent on assignment loss

**File:** `app/notifications/__init__.py:94-101`

**Issue:** Independent of CR-01's root cause, the re-pairing loop has no post-condition
check. If `job_idx` does not reach `len(jobs)` after walking all chunks (because a block
was not found in its expected chunk), the leftover jobs are silently never associated
with any chunk — they will never be marked seen even on a fully successful send, causing
permanent re-notification with no log trace. Even once CR-01 is fixed via index-based
pairing, a defensive assertion guards against future regressions.

**Fix:** After building `chunks`, assert/log if not all jobs were assigned:

```python
assigned = sum(len(ids) for _, ids in chunks)
if assigned != len(jobs):
    logger.error(
        "telegram re-pairing lost jobs: assigned=%d expected=%d", assigned, len(jobs)
    )
```

### WR-03: `min_score` is not coerced/validated inside `get_undelivered_qualifying`

**File:** `app/storage/sqlite.py:214-237`

**Issue:** The storage method binds `min_score` straight into `score_total >= ?`. The
sole production caller (`send_digest`) coerces with `int(...)` first, but the Protocol
and method signature advertise this as a public storage API. If any future caller passes
a non-numeric string (e.g. a raw setting value), SQLite's dynamic-typing comparison
silently produces wrong/empty results rather than erroring — a quiet correctness trap.
The phase invariant (#5) explicitly calls for `int()` coercion on
`notification_min_score`; that coercion currently lives only at the call site.

**Fix:** Coerce defensively at the storage boundary so the contract holds regardless of
caller:

```python
try:
    min_score_i = int(min_score)
except (TypeError, ValueError):
    logger.warning("get_undelivered_qualifying: min_score=%r invalid → 0", min_score)
    min_score_i = 0
# ... bind min_score_i in the query
```

### WR-04: `desc = resp.json().get("description")` can raise `AttributeError` past the bare `except`

**File:** `app/notifications/telegram.py:84-87`

**Issue:** On a non-200 response the code does `desc = resp.json().get("description")`.
If the Telegram error body is valid JSON but not a JSON object (e.g. a bare list or
string — `resp.json()` returns `[]` or `"..."`), `.get` raises `AttributeError`. This is
caught by the `except Exception` immediately below, so it does not crash, but it is
incidental rather than intentional and masks the real shape mismatch. The broad
`except Exception` also swallows genuinely unexpected errors.

**Fix:** Guard the type explicitly so the fallback is intentional:

```python
try:
    body = resp.json()
    desc = body.get("description") if isinstance(body, dict) else "(non-dict body)"
except ValueError:
    desc = "(non-JSON body)"
```

## Info

### IN-01: `send_digest` docstring references attribute access that does not match the code

**File:** `app/notifications/__init__.py:41-42`

**Issue:** The docstring describes step 1 as `int(settings.notification_min_score, ...)`
and step 2 as `storage.get_undelivered_qualifying(min_score, [...])` — but `settings` is
a plain `dict` (from `storage.get_settings()`), and the code correctly uses
`settings.get("notification_min_score", "70")`. The attribute-access form in the
docstring is misleading; a maintainer copying it would hit `AttributeError`.

**Fix:** Update the docstring to `settings.get("notification_min_score", "70")`.

### IN-02: `_send_email` re-imports `smtplib` solely to reference the exception type

**File:** `app/notifications/__init__.py:112`

**Issue:** `import smtplib` inside `_send_email` exists only so the `except
smtplib.SMTPException` clause can name the type. This works, but couples `__init__.py` to
smtplib internals that properly belong to `email_smtp.py`. Cleaner: have
`send_email_digest` translate transport failures into a single domain exception (or
return a success/error tuple like `send_telegram_digest` does), so `__init__.py` need not
import smtplib at all. (Folds naturally into the WR-01 fix.)

**Fix:** Mirror the Telegram transport's `(delivered, errors)` return contract for email,
or raise a package-local `DigestDeliveryError`, removing the smtplib import from
`__init__.py`.

### IN-03: `format_offer_block` does not guard against attacker-supplied control characters

**File:** `app/notifications/digest.py:96-103`

**Issue:** `job.title`, `job.company`, and `reasons_for` (LLM-influenced) are
concatenated into the plain-text block verbatim. There is no SSRF/header-injection risk
(confirmed under #2/#3), and Telegram's `text` field with no `parse_mode` treats the body
literally, so this is not a security blocker. However, embedded newlines in a title could
cosmetically distort the digest layout / `format_offer_block`'s `"\n".join` structure.
Low impact for a personal tool; noting for completeness.

**Fix (optional):** Strip control chars when rendering, e.g.
`job.title.replace("\n", " ").strip()`.

### IN-04: Re-pairing loop is O(blocks × chunks × blocklen) substring scans

**File:** `app/notifications/__init__.py:96-101`

**Issue:** Each chunk re-scans remaining blocks via Python `in` substring search over the
full (≤4096-char) chunk text. Performance is out of v1 review scope and digests are
small, but the index-based fix proposed in CR-01 eliminates this entirely as a free
side-benefit. Noted only because the fix resolves both at once.

**Fix:** Subsumed by CR-01 (index-based pairing is O(n)).

---

_Reviewed: 2026-05-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
