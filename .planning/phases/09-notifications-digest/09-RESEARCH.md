# Phase 9: Notifications & Digest - Research

**Researched:** 2026-05-25
**Domain:** Notification delivery (Telegram Bot API via raw httpx + SMTP stdlib), storage query extension, pipeline integration
**Confidence:** HIGH

---

## Summary

Phase 9 adds a post-pipeline delivery step that queries the DB for undelivered qualifying
jobs (`seen=0 AND recommendation IN ('strong_fit','good_fit') AND score_total >= min_score`)
and sends a digest to the configured channel (Telegram or email). The architecture is fully
decided in CONTEXT.md (D-01 through D-14). This research confirms technical feasibility,
resolves the PTB-vs-httpx tension with a firm recommendation, documents all API specifics,
and verifies the exact codebase patterns to mirror.

The critical finding is that `python-telegram-bot` v22.7 (already in deps) is **async-first**:
`Bot.send_message` is a coroutine function. Using it from the sync `APScheduler
BlockingScheduler` context requires `asyncio.run()` wrapping — which adds unnecessary
complexity. Raw `httpx.Client` (also already in deps) is purely synchronous, matches the
existing jsearch pattern exactly, and is the correct choice for a one-shot digest send. PTB
should be **removed** from `pyproject.toml` to keep deps honest.

**Primary recommendation:** Implement `app/notifications/` using raw `httpx.Client` for
Telegram and `smtplib.SMTP` (stdlib) for email. Remove `python-telegram-bot` from deps.
Mirror the `app/sources/jsearch.py` patterns for sync HTTP + error isolation throughout.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Package `app/notifications/`. Public surface: `send_digest(storage, settings, *, scored_jobs=None) -> DigestResult`.
- **D-02:** Imports only `httpx` and stdlib `smtplib`/`email.message`. Must NOT import `streamlit` or `apscheduler`.
- **D-03:** Channel resolution — `notification_channel` setting + env-var secret presence. `"telegram"` requires `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`; `"email"` requires `SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD` (+ `SMTP_PORT` default 587); `"none"/"auto"` auto-detects; neither → silent skip.
- **D-04:** All secrets from env only — never from settings, never logged.
- **D-05:** Digest fields per offer: title, company, score_total, recommendation, top 2-3 `reasons_for`, apply URL.
- **D-06:** Telegram — single combined message, chunked only when 4096-char limit exceeded; split on offer boundaries; plain text; parse_mode unset.
- **D-07:** Email — plain-text body, one offer per stanza, subject `BuscadorDeEmpleo: N nuevas ofertas (DD/MM)`. One email per run.
- **D-08:** Digest source is `get_undelivered_qualifying(...)` DB query, NOT `result.scored_jobs`.
- **D-09:** New method `get_undelivered_qualifying(min_score: int, recommendations: list[str]) -> list[ScoredJob]` added to `SQLiteStorage` + `Storage` Protocol.
- **D-10:** send_digest sequence: query → if empty return → resolve channel → if none log+return (no mark_seen) → send → on success mark_seen per job → on failure log+append error, no mark_seen.
- **D-11:** mark_seen granularity: per-job after successful send of the chunk containing it; later chunk failure must not un-deliver earlier chunks.
- **D-12:** `run_pipeline()` calls `send_digest` as final step via deferred import after `record_run`.
- **D-13:** Notification failures must never abort pipeline — wrap in try/except inside `run_pipeline`, collect into `result.errors`.
- **D-14:** Add `channel: str|None` + `notified: int = 0` to `record_run` and the `runs` table (default: add columns; planner decides final form).

### Claude's Discretion

- Exact Telegram chunk-splitting helper signature.
- Email MIME construction details.
- Whether `get_undelivered_qualifying` reuses `get_history` row→ScoredJob pattern or adds a small private helper.
- Retry policy (default: no retry in v2.0).

### Deferred Ideas (OUT OF SCOPE)

- HTML email template / rich formatting → v2.x.
- Multiple simultaneous channels → out of scope; single channel only.
- Retry/backoff on transient failures → v2.x.
- Per-offer action buttons / inline keyboard in Telegram → v2.x.
- UI status panel consuming `runs.notified` count → Phase 10 (UI-09).
- Salary in digest → tied to deferred SCORE-16.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NOTIF-01 | Deliver digest of new strong_fit/good_fit jobs (title, company, score, recommendation, top reasons, URL) after each run | D-05/D-06/D-07 confirmed feasible; `reasons_for` lives in `score_json` reconstructed via `JobScore.model_validate_json` |
| NOTIF-02 | Telegram OR email; silent skip if neither configured; secrets from env only | D-03/D-04 confirmed; channel resolution via `notification_channel` setting already seeded in DB |
| NOTIF-03 | Min-score threshold; only new (unseen) jobs; mark seen AFTER delivery success | D-08/D-09/D-10/D-11 confirmed; `seen=0` filter + `score_total >= int(notification_min_score)` (string-to-int coercion needed); `mark_seen` already implemented at `sqlite.py:285` |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Digest query (undelivered qualifying jobs) | Storage layer | — | Belongs in `SQLiteStorage`; SQL filter is storage logic, not business logic |
| Channel resolution + secret reading | `app/notifications/digest.py` | — | Orchestration concern; reads env + settings; no DB or HTTP |
| Telegram HTTP POST | `app/notifications/telegram.py` | — | Thin httpx wrapper; one responsibility: call Bot API sendMessage |
| Email MIME + SMTP | `app/notifications/email_smtp.py` | — | Thin smtplib wrapper; one responsibility: send EmailMessage |
| Digest formatting (text rendering) | `app/notifications/digest.py` | — | Pure string operations; no I/O; separately testable |
| Delivery orchestration (call channel, mark seen) | `app/notifications/__init__.py` (send_digest) | — | Wires storage query + channel selection + per-job mark_seen |
| Pipeline wiring | `app/pipeline.py` step 11 | — | Deferred import keeps pipeline import-clean |
| Run accounting (channel/notified counts) | `app/storage/sqlite.py` record_run | — | D-14: new optional columns on `runs` table |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | 0.28.1 | Telegram Bot API HTTP POST | [VERIFIED: uv run] Already in deps; sync `httpx.Client` matches APScheduler BlockingScheduler sync context exactly; mirrors jsearch.py pattern |
| `smtplib` | stdlib | SMTP connection + STARTTLS | [VERIFIED: stdlib] Zero new deps; supports `with` statement context manager; Python 3.11+ stdlib |
| `email.message.EmailMessage` | stdlib | Email MIME construction | [VERIFIED: stdlib] Modern Python email API; `smtp.send_message(msg)` handles headers correctly |

### No New Dependencies Needed

The entire Phase 9 implementation requires **zero new package installations**. All required
libraries are already present: `httpx` (Telegram), stdlib `smtplib`/`email.message` (email),
stdlib `sqlite3` (storage query).

### Removal Recommended

| Package | Current Version | Recommendation | Reason |
|---------|----------------|----------------|--------|
| `python-telegram-bot` | 22.7 | **REMOVE from pyproject.toml** | [VERIFIED: uv run] `Bot.send_message` is `async` (confirmed coroutine). Unused in implementation — raw httpx is cleaner and sync. Keeping it is a misleading dependency that implies async Telegram usage. |

**Removal action:** Delete `"python-telegram-bot>=22.7"` from `pyproject.toml` `[project] dependencies` and run `uv sync`.

---

## Architecture Patterns

### System Architecture Diagram

```
run_pipeline() [app/pipeline.py]
       │
       │ step 10: record_run()
       │
       │ step 11: deferred import send_digest()
       ▼
send_digest(storage, settings) [app/notifications/__init__.py]
       │
       ├── storage.get_undelivered_qualifying(min_score, ["strong_fit","good_fit"])
       │           [app/storage/sqlite.py]
       │           └── SELECT * FROM jobs
       │               WHERE seen=0
       │               AND recommendation IN (?,?)
       │               AND score_total >= ?
       │               → list[ScoredJob]
       │
       ├── if empty → return DigestResult(delivered=0)
       │
       ├── resolve_channel(settings)  [app/notifications/digest.py]
       │           └── reads notification_channel + env vars
       │           → "telegram" | "email" | None
       │
       ├── if None → log info, return DigestResult(delivered=0) [no mark_seen]
       │
       ├── format_digest(jobs)  [app/notifications/digest.py]
       │           └── renders per-offer blocks → list[str] offer_blocks
       │
       ├── channel == "telegram":
       │       send_telegram_digest(offer_blocks, token, chat_id)
       │       [app/notifications/telegram.py]
       │       └── chunk_offers(offer_blocks, max_chars=4096)
       │           → for each chunk:
       │               POST https://api.telegram.org/bot{token}/sendMessage
       │               JSON {chat_id, text}   [httpx.Client, sync]
       │               if 200 → mark_seen(job_id) for each job in chunk
       │               if error → log, append to errors, DO NOT mark_seen
       │
       └── channel == "email":
               send_email_digest(offer_blocks, n_jobs, smtp_cfg)
               [app/notifications/email_smtp.py]
               └── build EmailMessage (plain text body, subject with N + DD/MM)
                   with smtplib.SMTP(host, port) as smtp:
                       smtp.ehlo(); smtp.starttls()
                       smtp.login(user, password)
                       smtp.send_message(msg)
                   if success → mark_seen(job_id) for all jobs
                   if SMTPException → log, append to errors, DO NOT mark_seen
```

### Recommended Project Structure

```
app/
└── notifications/
    ├── __init__.py      # send_digest() public entry point + DigestResult dataclass
    ├── digest.py        # resolve_channel(), format_offer(), chunk_offers(), build_subject()
    ├── telegram.py      # send_telegram_digest() — httpx POST to Bot API
    └── email_smtp.py    # send_email_digest() — smtplib SMTP + EmailMessage

tests/
└── notifications/
    ├── __init__.py
    └── test_notifications.py   # all 7 scenarios from CONTEXT.md §Specific Ideas
```

### Pattern 1: Raw httpx Sync POST for Telegram (mirrors jsearch.py)

```python
# Source: [VERIFIED: app/sources/jsearch.py existing pattern]
import os
import httpx

TELEGRAM_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT = 10.0

def _send_message(client: httpx.Client, token: str, chat_id: str, text: str) -> bool:
    """POST sendMessage. Returns True on 200, False on any error. Never raises."""
    url = f"{TELEGRAM_BASE}/bot{token}/sendMessage"
    try:
        resp = client.post(url, json={"chat_id": chat_id, "text": text}, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            return True
        # Non-200: log the Telegram error description
        try:
            body = resp.json()
            logger.warning("Telegram API error %d: %s", resp.status_code, body.get("description"))
        except Exception:
            logger.warning("Telegram API error %d (non-JSON body)", resp.status_code)
        return False
    except httpx.HTTPError as exc:
        logger.warning("Telegram HTTP error: %s", exc)
        return False
```

**Key difference from jsearch.py:** Uses `client.post(..., json=...)` (Telegram expects
JSON body via POST), not `client.get(...)` (JSearch uses GET with query params).

### Pattern 2: SMTP STARTTLS (Gmail port 587)

```python
# Source: [VERIFIED: stdlib smtplib; Gmail app-password pattern]
import smtplib
from email.message import EmailMessage

def send_email_digest(body: str, subject: str, smtp_host: str, smtp_port: int,
                      smtp_user: str, smtp_password: str) -> None:
    """Send plain-text digest email. Raises SMTPException on failure."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = smtp_user          # self-send (personal tool)
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(smtp_user, smtp_password)
        smtp.send_message(msg)
```

**Gmail specifics:** `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`. The password must be a
**Gmail App Password** (not the account password) — account password fails if 2FA is enabled.
This is documented in `.env.example` already. [ASSUMED: standard Gmail App Password requirement]

### Pattern 3: get_undelivered_qualifying (mirrors get_history row→ScoredJob)

```python
# Source: [VERIFIED: app/storage/sqlite.py get_history pattern]
def get_undelivered_qualifying(self, min_score: int,
                               recommendations: list[str]) -> list[ScoredJob]:
    placeholders = ",".join("?" * len(recommendations))
    with closing(self._connect()) as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs WHERE seen=0 AND recommendation IN ({placeholders})"
            " AND score_total >= ? ORDER BY score_total DESC",
            (*recommendations, min_score),
        ).fetchall()
    result = []
    for row in rows:
        try:
            score = JobScore.model_validate_json(row["score_json"])
            job = Job(
                id=row["id"], title=row["title"], company=row["company"],
                location=row["location"],
                remote=RemoteJob(row["remote"]) if row["remote"] else RemoteJob.unknown,
                url=row["url"], source=row["source"] or "unknown",
            )
            result.append(ScoredJob(job=job, score=score))
        except Exception as exc:
            logger.warning("get_undelivered_qualifying: skipping row %s: %s", row["id"], exc)
    return result
```

**Note:** `description` is not stored in the DB (not in the jobs table schema). The
reconstructed `ScoredJob.job.description` will be `""` (default). This is fine — the digest
only needs `title`, `company`, `score`, `reasons_for`, and `url`. [VERIFIED: sqlite.py schema]

### Pattern 4: Chunking at offer boundaries

```python
# Source: [ASSUMED based on D-06 spec]
TELEGRAM_MAX_CHARS = 4096

def chunk_offers(header: str, offer_blocks: list[str]) -> list[str]:
    """Split offer_blocks into messages <=4096 chars, never mid-offer."""
    chunks: list[str] = []
    current = header
    for block in offer_blocks:
        candidate = current + "\n\n" + block
        if len(candidate) > TELEGRAM_MAX_CHARS and current != header:
            chunks.append(current)
            current = block
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
```

**Invariant:** Every offer block appears in exactly one chunk, intact. The per-chunk
`mark_seen` logic (D-11) relies on this guarantee.

### Pattern 5: record_run schema migration (ALTER TABLE idempotent)

```python
# Source: [VERIFIED: SQLite ALTER TABLE behavior]
# In SQLiteStorage.init_db(), inside the 'with conn:' block:
cursor = conn.execute("PRAGMA table_info(runs)")
col_names = [row[1] for row in cursor.fetchall()]
if "channel" not in col_names:
    conn.execute("ALTER TABLE runs ADD COLUMN channel TEXT")
if "notified" not in col_names:
    conn.execute("ALTER TABLE runs ADD COLUMN notified INTEGER DEFAULT 0")
```

**Why PRAGMA check:** SQLite does not support `ADD COLUMN IF NOT EXISTS`. Existing rows
get `NULL` for `channel` and `0` for `notified` automatically. [VERIFIED: sqlite3 test]

### Anti-Patterns to Avoid

- **Using `python-telegram-bot` Bot.send_message directly:** It is a coroutine. Calling it
  from APScheduler's sync thread requires `asyncio.run()` which is unnecessary overhead and
  creates an event loop inside a scheduler thread. Use raw httpx instead.
- **asyncio.run() wrapping PTB:** Works but is fragile in nested-loop scenarios (e.g., if
  the scheduler ever runs inside an async context). Avoid entirely.
- **Marking seen before send:** The send may fail. Mark seen ONLY after `status_code == 200`
  (Telegram) or after `smtp.send_message(msg)` returns without exception (email).
- **Using `result.scored_jobs` as digest source:** D-08 explains the subtle bug: a job
  whose delivery fails still exists in the DB (was_seen=True) so it would never be queued
  for re-delivery. The DB query with `seen=0` is the authoritative source.
- **`INSERT OR REPLACE` on runs:** Already avoided in the codebase — noted here because
  adding new columns must NOT use `INSERT OR REPLACE` (would reset existing row data).
- **Interpolating env secrets into SQL strings:** The `notification_min_score` value from
  settings must be cast with `int()` before use as a SQL parameter. Settings values are
  all strings. [VERIFIED: sqlite.py comment "Los valores numéricos se devuelven como strings"]
- **Logging secret values:** Never log `TELEGRAM_BOT_TOKEN`, `SMTP_PASSWORD`. Log channel
  name and delivered count only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Telegram HTTP transport | Custom async PTB wrapper | `httpx.Client` (sync POST) | Already in deps; zero async complexity |
| Email MIME construction | Manual RFC 822 headers | `email.message.EmailMessage` | Handles encoding, multipart, headers correctly |
| SMTP TLS handshake | Manual SSL wrapping | `smtplib.SMTP.starttls()` | stdlib handles certificate verification |
| JSON serialization of score | Custom to-dict | `JobScore.model_validate_json(row["score_json"])` | Already established pattern in `get_history` |
| Parameterized SQL placeholders | String interpolation | `"IN ({",".join("?" * n)})"` | Injection prevention; matches all existing storage queries |

---

## Critical Tension: PTB vs Raw httpx — RESOLVED

### Finding

`python-telegram-bot` v22.7 (installed at 22.7 exactly per `uv run python -c "import telegram; print(telegram.__version__)"`):

- `Bot.send_message` IS a coroutine function: `asyncio.iscoroutinefunction(Bot.send_message) == True` [VERIFIED: uv run]
- PTB uses `httpx` internally (via its own `HTTPXRequest` async client) [VERIFIED: importlib.metadata]
- PTB pulls in 486 new modules on import (includes asyncio, click, etc.) [VERIFIED: sys.modules diff]
- PTB `HTTPXRequest.do_request` is also a coroutine [VERIFIED: uv run]

`httpx.Client.post` is NOT a coroutine: [VERIFIED: uv run inspect.iscoroutinefunction]
- Completely synchronous
- Matches the existing `jsearch.py` pattern exactly
- No event loop required
- Already in deps at 0.28.1

### Recommendation: Raw httpx, REMOVE PTB

For a one-shot "send digest messages after a sync pipeline run" use case, raw `httpx.Client`
POST to `https://api.telegram.org/bot{token}/sendMessage` is:

1. **Correct for the sync context**: APScheduler `BlockingScheduler` is synchronous. No
   `asyncio.run()` needed — no event loop complexity.
2. **Already used in the project**: `app/sources/jsearch.py` uses the identical pattern.
   Tests mock `httpx.Client` the same way.
3. **Simpler**: ~15 lines vs wrapping PTB's async API.
4. **Honest deps**: PTB is not used anywhere. Remove it to keep `pyproject.toml` accurate.

`python-telegram-bot` should be **removed** from `pyproject.toml`. This is a one-line
change (`uv sync` afterwards). No functionality is lost.

---

## Telegram Bot API Specifics

**Endpoint:** `POST https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage`

**Request body (JSON):**
```json
{
  "chat_id": "123456789",
  "text": "message text (max 4096 chars)"
}
```
`chat_id` can be a numeric user/group ID or `@channel_username`.
`parse_mode` is omitted (D-06: plain text, no Markdown escaping).
`disable_web_page_preview` is deprecated in Bot API v7.0+ (replaced by
`link_preview_options`); omitting it is the safest approach for v2.0. [ASSUMED: Bot API v7.0 docs]

**Success response:** `{"ok": true, "result": {...}}` with HTTP 200.
**Error response:** `{"ok": false, "error_code": N, "description": "..."}` with HTTP 4xx.

**Text limit:** 4096 characters per message. [ASSUMED: official Bot API docs, stable]

**Rate limits (informal, not officially documented):**
- ~30 messages/second globally per bot
- ~1 message/second per chat
For a digest (2-5 chunks typical), no sleep needed. [ASSUMED: widely reported, not official]

**Non-200 surface:** Check `resp.status_code == 200` directly (same pattern as jsearch
429/401/403 checks). Do NOT use `resp.raise_for_status()` as the only check — Telegram
errors always return a JSON body with `description` which is useful for logging.

---

## SMTP Specifics

**Gmail App Password flow:**
1. Google Account → Security → App passwords → generate a 16-char password
2. Use as `SMTP_PASSWORD` in `.env`
3. `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587` (already in `.env.example`)

**Exception hierarchy for catch-all error handling:**
```python
except smtplib.SMTPException as exc:
    logger.error("Email delivery failed: %s", exc)
    # SMTPAuthenticationError, SMTPConnectError, SMTPRecipientsRefused,
    # SMTPSenderRefused, SMTPDataError, SMTPServerDisconnected all covered
```
[VERIFIED: stdlib inspect — all SMTP errors subclass `smtplib.SMTPException`]

**send_message vs sendmail:** `smtp.send_message(msg)` is preferred over `smtp.sendmail()`
when using `EmailMessage` objects — it handles encoding automatically. [VERIFIED: stdlib]

---

## The seen/was_seen Distinction (D-08, CRITICAL)

Confirmed by code reading of `sqlite.py`:

| Method | SQL | Meaning |
|--------|-----|---------|
| `was_seen(job_id)` | `SELECT 1 FROM jobs WHERE id=?` | Row EXISTS (job was ever stored) |
| `mark_seen(job_id)` | `UPDATE jobs SET seen=1 WHERE id=?` | Delivery confirmed |
| `get_undelivered_qualifying(...)` | `WHERE seen=0 AND recommendation IN (?) AND score_total >= ?` | To-deliver query |

`was_seen` checks row **existence** only — it returns `True` for both `seen=0` AND `seen=1`
rows. The pipeline uses `was_seen` to skip re-scoring already-stored jobs (step 7). This is
correct for dedup but wrong for "should we notify?" — a `seen=0` job IS stored but NOT yet
delivered. The new `get_undelivered_qualifying` query is the authoritative filter.

**Recommendation enum values in DB** (confirmed by inspection of `upsert_scored_jobs` which
uses `score.recommendation.value`): stored as strings `"strong_fit"`, `"good_fit"`, `"maybe"`,
`"skip"`. [VERIFIED: app/models/schemas.py Recommendation enum + sqlite.py upsert logic]

**`notification_min_score` coercion:** Settings are stored as strings. Must call
`int(settings.get("notification_min_score", "70"))` before using as SQL parameter.
[VERIFIED: sqlite.py comment + get_settings returns dict[str, str]]

---

## Common Pitfalls

### Pitfall 1: Using result.scored_jobs as digest source instead of DB query

**What goes wrong:** A job scored and stored in this run (step 9 of pipeline) is immediately
available in `result.scored_jobs`. If delivery fails, the job is still in the DB with `seen=0`.
The NEXT run's `was_seen` check returns `True` (row exists) → the job is excluded from
`new_jobs` → it is never re-scored → it never appears in `result.scored_jobs` again →
never re-notified. The backlog is silently lost.
**Why it happens:** Confusing "new this run" with "not yet delivered".
**How to avoid:** Always query `WHERE seen=0` from the DB (D-08). `get_undelivered_qualifying`
is the single source of truth.

### Pitfall 2: Marking seen before confirming delivery

**What goes wrong:** Calling `mark_seen(job_id)` before the HTTP 200 or SMTP response means
a delivery failure silently loses the job from future digests.
**Why it happens:** Easier code flow to mark upfront and cancel if needed — but cancellation
logic is complex and fragile.
**How to avoid:** Mark seen ONLY in the success path. In Telegram: after `status_code == 200`.
In email: after `smtp.send_message()` returns without exception.

### Pitfall 3: Chunking mid-offer

**What goes wrong:** If the 4096-char limit is checked on the accumulated text only (not on
individual offer boundaries), a long offer description could be split across two messages,
making the second message start mid-paragraph.
**Why it happens:** Naive character-count split.
**How to avoid:** The `chunk_offers` helper accumulates whole offer blocks. When adding a new
block would exceed 4096, the current chunk is closed and the new block starts a fresh chunk.
The invariant: no offer ever spans two chunks. [VERIFIED: chunk logic reviewed above]

### Pitfall 4: PTB async in sync context

**What goes wrong:** `Bot.send_message(...)` returns a coroutine object, not a response.
Awaiting it outside an event loop raises `RuntimeError: no current event loop`.
Wrapping in `asyncio.run()` inside APScheduler's thread can raise `RuntimeError: This
event loop is already running` if the scheduler ever runs inside an async context.
**Why it happens:** PTB v20+ is async-first.
**How to avoid:** Do not use PTB. Use raw `httpx.Client` POST (D-01 already decides this;
this pitfall documents WHY).

### Pitfall 5: notification_min_score type mismatch in SQL

**What goes wrong:** `settings["notification_min_score"]` is `"70"` (a string). Passing a
string to the SQL `score_total >= ?` comparison silently compares correctly in SQLite (due
to type affinity), but is confusing and fragile. A setting like `"70.5"` would fail silently.
**How to avoid:** Always coerce: `min_score = int(settings.get("notification_min_score", "70"))`.

### Pitfall 6: Losing the 'channel' column on old DBs

**What goes wrong:** An existing `data/jobs.db` has a `runs` table without `channel`/`notified`
columns. `init_db()` uses `CREATE TABLE IF NOT EXISTS` — it does NOT add missing columns.
The INSERT in `record_run` would fail with `OperationalError: table has no column named channel`.
**How to avoid:** Use the PRAGMA-check ALTER TABLE migration pattern in `init_db()` (documented
in Pattern 5 above). [VERIFIED: SQLite ALTER TABLE test]

---

## Code Examples

### Offer block formatting (digest.py)

```python
# Source: [ASSUMED from D-05 spec — field list confirmed from schemas.py]
def format_offer_block(sjob: ScoredJob) -> str:
    """Render a single offer as a plain-text block for the digest."""
    score = sjob.score
    job = sjob.job
    reasons = score.reasons_for[:3]                     # top 2-3 per D-05
    reasons_text = "\n".join(f"  + {r}" for r in reasons) if reasons else ""
    url_line = f"  {job.url}" if job.url else ""
    return (
        f"{job.title} @ {job.company}\n"
        f"  Score: {score.score_total}/100 ({score.recommendation.value})\n"
        + (reasons_text + "\n" if reasons_text else "")
        + url_line
    ).rstrip()
```

### DigestResult dataclass (notifications/__init__.py)

```python
# Source: [ASSUMED — mirrors PipelineResult pattern from pipeline.py]
from dataclasses import dataclass, field

@dataclass
class DigestResult:
    channel: str | None = None      # "telegram" / "email" / None
    delivered: int = 0               # number of jobs marked seen
    errors: list[str] = field(default_factory=list)
```

### send_digest deferred import in pipeline.py (D-12)

```python
# Source: [VERIFIED: pipeline.py deferred import pattern already used]
# After record_run call (step 10), add step 11:
try:
    from app.notifications import send_digest  # noqa: PLC0415
    digest_result = send_digest(storage, settings)
    if digest_result.errors:
        result.errors.extend(digest_result.errors)
except Exception as exc:          # noqa: BLE001
    logger.error("send_digest failed: %s", exc)
    result.errors.append(f"notify: {exc}")
```

### Test mock for Telegram httpx POST (mirrors jsearch tests exactly)

```python
# Source: [VERIFIED: tests/sources/test_jsearch.py mock pattern]
from unittest.mock import MagicMock, patch

def _make_200_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"ok": True, "result": {}}
    return resp

def test_telegram_send_success(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")

    with patch("app.notifications.telegram.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.post.return_value = _make_200_response()

        from app.notifications.telegram import send_telegram_digest
        # ... call and assert
```

### Test mock for SMTP email send

```python
# Source: [VERIFIED: unittest.mock pattern; smtplib.SMTP supports __enter__/__exit__]
from unittest.mock import patch, MagicMock

def test_email_send_success(tmp_path, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USER", "test@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")

    with patch("app.notifications.email_smtp.smtplib.SMTP") as MockSMTP:
        mock_smtp = MockSMTP.return_value.__enter__.return_value
        mock_smtp.send_message.return_value = None

        from app.notifications.email_smtp import send_email_digest
        # ... call and assert
        assert mock_smtp.starttls.called
        assert mock_smtp.login.called
        assert mock_smtp.send_message.called
```

### Import cleanliness test (mirrors test_pipeline_no_streamlit_apscheduler)

```python
# Source: [VERIFIED: tests/test_pipeline.py test_pipeline_no_streamlit_apscheduler pattern]
def test_notifications_no_streamlit_apscheduler():
    for mod in list(sys.modules.keys()):
        if "streamlit" in mod or "apscheduler" in mod:
            del sys.modules[mod]
    import app.notifications  # noqa: F401
    assert "streamlit" not in sys.modules
    assert "apscheduler" not in sys.modules
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `python-telegram-bot` for Telegram messaging | Raw httpx POST to Bot API | D-01 decided before this research | PTB async overhead eliminated; sync client fits BlockingScheduler |
| `disable_web_page_preview` Telegram param | `link_preview_options: {is_disabled: true}` | Telegram Bot API v7.0 (2024) | Old param still works; omit entirely for v2.0 simplicity |
| `smtp.sendmail()` | `smtp.send_message(msg)` with `EmailMessage` | Python 3.6+ | Better encoding handling; no manual header assembly |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Gmail App Password required when 2FA enabled | SMTP Specifics | Low — standard Gmail requirement; `.env.example` already notes this |
| A2 | Telegram rate limit ~1 msg/s per chat; no sleep needed for 2-5 chunks | Telegram API Specifics | Low — digest volume is tiny; Telegram won't throttle |
| A3 | `disable_web_page_preview` still accepted by Telegram Bot API v7+ (backward compat) | Telegram API Specifics | Low — omitting it entirely is the safer path; no impact |
| A4 | `chunk_offers` signature (header + list[str] of blocks) | Code Examples | Zero — Claude's Discretion per CONTEXT.md; planner adjusts |
| A5 | `DigestResult` dataclass shape (channel, delivered, errors) | Code Examples | Low — only used internally by pipeline.py; easy to adjust |
| A6 | Bot API v7.0 deprecated `disable_web_page_preview` in favor of `link_preview_options` | State of the Art | Low — either works; omitting is safest |

---

## Open Questions (RESOLVED)

1. **PTB removal confirmation**
   - What we know: PTB is unused after Phase 9; `Bot.send_message` is async; raw httpx is the right tool.
   - What's unclear: Whether the user wants to keep PTB for a potential future interactive bot (not in scope per REQUIREMENTS.md "Bot de Telegram interactivo → out of scope").
   - **RESOLVED:** Remove PTB — implemented as plan 09-04 (pyproject.toml + uv.lock).

2. **Gmail self-send vs separate recipient**
   - What we know: D-07 says "one email per run"; `.env.example` documents `SMTP_USER` and `SMTP_PASSWORD` but no `SMTP_TO`.
   - What's unclear: Should `To:` equal `SMTP_USER` (self-send) or require a separate `SMTP_TO` env var?
   - **RESOLVED:** Default to self-send (`To: SMTP_USER`); optional `SMTP_TO` override documented in `.env.example` — implemented in plan 09-03 Task 2.

3. **D-14 record_run update — pipeline.py call site**
   - What we know: `pipeline.py` currently calls `record_run(...)` at step 10 WITHOUT `channel`/`notified`. The digest result is only known AFTER step 11.
   - What's unclear: Should `record_run` be called twice (step 10 + update in step 11), or deferred to after `send_digest`?
   - **RESOLVED:** Call `record_run` once, AFTER `send_digest`, passing `channel`/`notified` from `DigestResult`; `started_at` local still captures run-start time — implemented in plan 09-05 Task 1.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `httpx` | Telegram HTTP POST | ✓ | 0.28.1 | — |
| `smtplib` | Email delivery | ✓ | stdlib | — |
| `email.message` | Email MIME | ✓ | stdlib | — |
| `sqlite3` | `get_undelivered_qualifying` query | ✓ | stdlib | — |

No missing dependencies. Phase 9 is deployable with current `pyproject.toml` minus PTB.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/notifications/ -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOTIF-01 | Offer digest renders title/company/score/reasons/URL | unit | `uv run pytest tests/notifications/test_notifications.py::test_format_offer_block -x` | ❌ Wave 0 |
| NOTIF-01 | Telegram digest sends all qualifying jobs | unit | `uv run pytest tests/notifications/test_notifications.py::test_telegram_channel_sends_digest -x` | ❌ Wave 0 |
| NOTIF-01 | Email digest sends all qualifying jobs | unit | `uv run pytest tests/notifications/test_notifications.py::test_email_channel_sends_digest -x` | ❌ Wave 0 |
| NOTIF-02 | Only TELEGRAM env set → Telegram path, no email | unit | `uv run pytest tests/notifications/test_notifications.py::test_channel_resolution_telegram_only -x` | ❌ Wave 0 |
| NOTIF-02 | Only SMTP env set → email path | unit | `uv run pytest tests/notifications/test_notifications.py::test_channel_resolution_email_only -x` | ❌ Wave 0 |
| NOTIF-02 | Neither env set → silent skip, nothing marked seen | unit | `uv run pytest tests/notifications/test_notifications.py::test_channel_resolution_none_silent -x` | ❌ Wave 0 |
| NOTIF-03 | Send failure → job stays seen=0, reappears in next digest | unit | `uv run pytest tests/notifications/test_notifications.py::test_delivery_failure_leaves_seen_0 -x` | ❌ Wave 0 |
| NOTIF-03 | Send success → job marked seen=1, absent from next digest | unit | `uv run pytest tests/notifications/test_notifications.py::test_delivery_success_marks_seen_1 -x` | ❌ Wave 0 |
| NOTIF-03 | Only strong_fit/good_fit above threshold selected | unit | `uv run pytest tests/notifications/test_notifications.py::test_qualifying_filter_excludes_maybe_low_score -x` | ❌ Wave 0 |
| D-02 | import app.notifications does not load streamlit/apscheduler | unit | `uv run pytest tests/notifications/test_notifications.py::test_notifications_no_streamlit_apscheduler -x` | ❌ Wave 0 |
| D-06 | 4096-char chunking: ≥2 chunks, no offer split, each delivered offer marked seen | unit | `uv run pytest tests/notifications/test_notifications.py::test_telegram_chunking_large_digest -x` | ❌ Wave 0 |
| D-14 | runs table gets channel + notified columns after Phase 9 init_db | unit | `uv run pytest tests/notifications/test_notifications.py::test_runs_table_has_channel_notified -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/notifications/ -q`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/notifications/__init__.py` — package init
- [ ] `tests/notifications/test_notifications.py` — all 12 test cases above
- [ ] `app/notifications/__init__.py` — package init with `send_digest`
- [ ] `app/notifications/digest.py` — channel resolution + formatting
- [ ] `app/notifications/telegram.py` — httpx POST wrapper
- [ ] `app/notifications/email_smtp.py` — SMTP wrapper

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — no user auth; personal tool |
| V3 Session Management | No | N/A — stateless notification send |
| V4 Access Control | No | N/A — single user |
| V5 Input Validation | Yes | Parameterized SQL in `get_undelivered_qualifying`; `int()` coercion of `notification_min_score` |
| V6 Cryptography | No | STARTTLS handled by stdlib smtplib; no custom crypto |

### Known Threat Patterns for Telegram/SMTP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Token/password exposure in logs | Information Disclosure | Never log `TELEGRAM_BOT_TOKEN`, `SMTP_PASSWORD`; log channel name only |
| SQL injection in undelivered query | Tampering | Parameterized `IN (?,?)` placeholder construction [VERIFIED: existing pattern] |
| settings.notification_min_score injection | Tampering | `int()` coercion; ValueError caught → fallback to default 70 |
| SMTP credential exposure via env | Information Disclosure | `.env` in `.gitignore`; `.env.example` has placeholder comments only |

---

## Sources

### Primary (HIGH confidence)

- [VERIFIED: app/storage/sqlite.py] — `was_seen` implementation (line 164), `mark_seen` (line 285), settings defaults `notification_min_score`/`notification_channel` (lines 111-112), `runs` table schema (lines 90-101), `get_history` row→dict pattern, `record_run` signature
- [VERIFIED: app/models/schemas.py] — `Recommendation` enum values (`strong_fit`, `good_fit`, `maybe`, `skip`), `ScoredJob` fields, `Job` stored fields
- [VERIFIED: app/sources/jsearch.py] — `httpx.Client` sync pattern, context-manager usage, per-query error isolation
- [VERIFIED: tests/sources/test_jsearch.py] — `patch("app.sources.jsearch.httpx.Client")` mock pattern
- [VERIFIED: tests/test_pipeline.py] — import cleanliness test pattern for streamlit/apscheduler
- [VERIFIED: uv run python] — `asyncio.iscoroutinefunction(Bot.send_message) == True`, `asyncio.iscoroutinefunction(httpx.Client.post) == False`, PTB version 22.7, httpx version 0.28.1
- [VERIFIED: uv run python sqlite3] — `ALTER TABLE runs ADD COLUMN` idempotent via PRAGMA check; existing rows get NULL/default

### Secondary (MEDIUM confidence)

- [CITED: stdlib docs smtplib] — `SMTPException` hierarchy, `SMTP.starttls()`, `SMTP.send_message()`, context manager support
- [CITED: stdlib docs email.message] — `EmailMessage`, `set_content()`, header fields

### Tertiary (LOW confidence / ASSUMED)

- [ASSUMED] Telegram Bot API 4096-char limit per message
- [ASSUMED] Telegram rate limit ~1 msg/s per chat (widely documented but not in official Telegram Bot API docs)
- [ASSUMED] Bot API v7.0 deprecated `disable_web_page_preview` (based on training knowledge)
- [ASSUMED] Gmail App Password requirement for 2FA accounts

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified via uv run; all deps confirmed present
- Architecture: HIGH — CONTEXT.md decisions confirmed technically feasible
- PTB-vs-httpx resolution: HIGH — verified async/sync nature via inspect
- Pitfalls: HIGH — derived from direct code inspection + verified patterns
- Telegram API specifics: MEDIUM — message limit and rate limits are ASSUMED

**Research date:** 2026-05-25
**Valid until:** 2026-06-25 (Telegram Bot API stable; stdlib does not change)
