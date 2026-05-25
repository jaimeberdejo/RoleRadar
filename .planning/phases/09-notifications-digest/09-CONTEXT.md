# Phase 9: Notifications & Digest - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Mode:** --auto (decisions auto-selected from analysis; one critical architectural edge case surfaced and resolved below)

<domain>
## Phase Boundary

After each pipeline run, deliver a digest of **new** strong_fit/good_fit jobs above a
configured score threshold to a **single** chosen channel (Telegram **or** email). If no
channel is configured the run completes **silently** (log only, no error). A job is marked
delivered (`seen=1`) **only after** the channel call succeeds — so a delivery failure leaves
the job for the next run's digest, and a delivered job never appears in a later digest even
across worker restarts.

Deliverables:
- **`app/notifications/` package** — `send_digest()` public entry; `telegram.py` (httpx),
  `email_smtp.py` (stdlib smtplib/email), `digest.py` (filter + format helpers). Imports only
  httpx + stdlib — **NO streamlit, NO apscheduler** (preserves Phase 8 SC5 import-cleanliness).
- **Channel resolution** — driven by `notification_channel` setting + env-var secrets.
- **Storage query** — `get_undelivered_qualifying(min_score, recommendations)` returning
  scored jobs with `seen=0` that meet the bar (the digest source of truth — see D-08).
- **Pipeline wiring** — `run_pipeline()` calls `send_digest(...)` as a final step (deferred
  import), so both the worker and the future UI "Run now" button notify identically.

</domain>

<decisions>
## Implementation Decisions

### Module structure & import-cleanliness
- **D-01:** Notifications live in a new package `app/notifications/` (matches the modular
  layout: `cv/`, `dedup/`, `scoring/`, `sources/`, `storage/`). Public surface:
  `app.notifications.send_digest(storage, settings, *, scored_jobs=None) -> DigestResult`.
- **D-02:** The package imports **only** `httpx` (Telegram HTTP) and stdlib `smtplib`/
  `email.message` (email). It must NOT import `streamlit` or `apscheduler`. Add a test
  asserting `import app.notifications` does not pull those into `sys.modules` (mirrors the
  Phase 8 pipeline import-cleanliness test).

### Channel selection (NOTIF-02)
- **D-03:** Channel is resolved from the `notification_channel` setting (already seeded in
  `init_db` defaults as `"none"`) combined with env-var secret presence:
  - setting == `"telegram"` → require `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`; if missing,
    log a warning and **skip** (do not fall through to email).
  - setting == `"email"` → require `SMTP_HOST` + `SMTP_USER` + `SMTP_PASSWORD` (+ `SMTP_PORT`,
    default 587); if missing, log a warning and skip.
  - setting == `"none"` / unset / `"auto"` → **auto-detect**: Telegram if its two env vars are
    present, else email if the SMTP trio is present, else **silent skip** (log one info line:
    "no notification channel configured"). This satisfies SC1 (telegram env set, default
    setting → telegram) and SC2 (only SMTP set → email; neither → silent, no error).
- **D-04:** All secrets come from **env only** — never from settings, never logged. Settings
  holds only the non-secret `notification_channel` selector and `notification_min_score`.

### Digest content & format (NOTIF-01)
- **D-05:** Each qualifying offer renders: **title, company, score_total, recommendation,
  top 2–3 `reasons_for`, and the apply URL** (exactly the SC1 field list).
- **D-06:** Telegram → a **single combined digest message**, header line
  (`🔔 N nuevas ofertas`) + one block per offer, **chunked into multiple messages only when
  the 4096-char Telegram limit is exceeded** (split on offer boundaries, never mid-offer).
  Plain text (no MarkdownV2 escaping fragility); URLs sent raw so Telegram auto-links them.
  parse_mode left unset for v2.0.
- **D-07:** Email → **plain-text** body (one offer per stanza, blank-line separated), subject
  `BuscadorDeEmpleo: N nuevas ofertas (DD/MM)`. One email per run. HTML email deferred to v2.x.

### Delivery atomicity & the seen/was_seen distinction (NOTIF-03, SC3, SC4) — CRITICAL
- **D-08:** **The digest source is the DB query `get_undelivered_qualifying(...)`, NOT this
  run's `result.scored_jobs`.** Rationale (the subtle edge case that breaks naïve designs):
  `was_seen(job_id)` checks **row existence** (`SELECT 1 FROM jobs WHERE id=?`), which is correct
  for dedup-against-stored but is a *different* concept from the `seen` delivery flag. The
  pipeline upserts scored jobs into the DB (step 9) **before** delivery, so a job whose delivery
  *fails* still exists in the DB; the next run's `was_seen` filter would exclude it from
  `new_jobs`/`scored_jobs`, and it would **never be re-delivered** — violating SC3. Querying
  `seen=0 AND recommendation IN (strong_fit, good_fit) AND score_total >= min_score` decouples
  "what to deliver" from "what was scored this run" and cleanly satisfies SC3 + SC4.
- **D-09:** New storage method `get_undelivered_qualifying(min_score: int,
  recommendations: list[str]) -> list[ScoredJob]` (add to `SQLiteStorage` + the `Storage`
  Protocol). Returns full `ScoredJob` objects (reconstructed from `score_json`) so the digest
  has reasons_for/url. Parameterized SQL only.
- **D-10:** Delivery/mark-seen sequence in `send_digest`:
  1. `jobs = storage.get_undelivered_qualifying(min_score, ["strong_fit","good_fit"])`.
  2. If `jobs` empty → return (nothing to send).
  3. Resolve channel (D-03). If none → log info, return **without** marking seen (backlog is
     preserved for when a channel is later configured).
  4. Format + send. **On send success** → `storage.mark_seen(job_id)` for **each delivered job**.
     **On send failure** → log error, append to result errors, **do NOT mark_seen** (jobs stay
     `seen=0` → included in the next run's digest per SC3).
- **D-11:** `mark_seen` granularity: mark per-job after a successful send of the message that
  contains it. For Telegram multi-chunk, mark the offers in a chunk only after that chunk's
  send returns 200 (a later chunk failing must not un-deliver earlier chunks, and must not
  mark its own offers). Keeps "marked == actually delivered" exact.

### Pipeline integration (SC5 preservation)
- **D-12:** Add a final step to `run_pipeline()`: after `record_run`, call
  `send_digest(storage, settings)` via a **deferred import** (`from app.notifications import
  send_digest`). Because the notifications package is import-clean (D-02), this keeps
  `import app.pipeline` free of streamlit/apscheduler. Both the worker and the Phase 10 UI
  "Run now" button get notifications for free by calling `run_pipeline()`.
- **D-13:** Notification failures must **never** abort the pipeline or crash the worker — wrap
  `send_digest` in try/except inside `run_pipeline`, log + collect into `result.errors`. The
  run is still recorded as successful (the fetch/score/persist already happened).

### Run/digest accounting (STORE-05 alignment)
- **D-14:** Record the digest outcome on the run. The `runs` table already has an `errors`
  column; capture delivery channel + count either by extending `record_run` (preferred: add
  optional `channel: str|None`, `notified: int = 0` params + columns) or by logging only if a
  schema change is judged too heavy by the planner. Planner decides; default = add the two
  columns since the UI status panel (Phase 10, UI-09) will want "new offers found / notified".

### Claude's Discretion
- Exact Telegram chunk-splitting helper signature and the email MIME construction details.
- Whether `get_undelivered_qualifying` reuses the existing `get_history` row→ScoredJob
  deserialization helper or adds a small private one.
- Retry policy on transient Telegram/SMTP errors (default: no retry in v2.0 — a failed send
  simply leaves jobs for the next scheduled run; keep it simple).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` §"Notificaciones / digest (NOTIF)" — NOTIF-01/02/03 exact wording.
- `.planning/ROADMAP.md` §"Phase 9: Notifications & Digest" — the 4 success criteria (the
  acceptance gates).
- `CLAUDE.md` — overall project spec; digest entry/exit JSON philosophy, "honesty" principle.

### Prior phase context (semantics this phase depends on)
- `.planning/phases/08-jsearch-client-worker-pipeline/08-CONTEXT.md` — pipeline shape,
  import-cleanliness rule (SC5), mark_seen-after-delivery note explicitly deferred to Phase 9.

### Code touchpoints
- `app/pipeline.py` — `run_pipeline()` (wire `send_digest` as final step, D-12/D-13).
- `app/storage/sqlite.py` — `was_seen` (existence check, line 164), `mark_seen` (line 285),
  `init_db` settings defaults (`notification_min_score`=70, `notification_channel`=none,
  lines 111–112), `runs` table (lines 90–101), `record_run`. Add `get_undelivered_qualifying`.
- `app/storage/protocol.py` — extend the `Storage` Protocol with the new query method.
- `app/models/schemas.py` — `ScoredJob`, `JobScore` (recommendation enum values:
  strong_fit/good_fit/maybe/skip), `Job` (title/company/url).
- `.env.example` — already documents `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `SMTP_HOST`,
  `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` (commented; Phase 9 activates them).
- `worker.py` — already calls `run_pipeline()`; no change needed if D-12 puts notify inside the
  pipeline (verify).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SQLiteStorage.mark_seen(job_id)` (sqlite.py:285) — already sets `seen=1`; Phase 9 is its
  first real caller.
- `SQLiteStorage.get_history` row→dict + `JobScore.model_validate_json` pattern — reuse for
  reconstructing `ScoredJob` in `get_undelivered_qualifying`.
- `notification_min_score` (default "70") + `notification_channel` (default "none") settings —
  already seeded; Phase 9 reads them.
- `httpx` is already a dependency (used by `app/sources/jsearch.py`) — Telegram client reuses it.
- `result.scored_jobs: list[ScoredJob]` from `PipelineResult` — available if the planner wants
  to pass it to send_digest as a fast-path, but D-08 makes the DB query authoritative.

### Established Patterns
- Per-item error isolation (jsearch per-query, pipeline per-job) — apply the same to per-job
  delivery: one offer's send failure must not lose the others.
- Deferred imports inside functions to keep modules import-clean (pipeline.py pattern).
- Parameterized SQL everywhere (no string interpolation) — keep for the new query.
- Settings are all stored as strings — `notification_min_score` needs `int()` coercion.

### Integration Points
- `run_pipeline()` final step (after `record_run`) — the single wiring point so worker + UI
  both notify.
- `Storage` Protocol — must stay in sync with `SQLiteStorage` (runtime_checkable).

</code_context>

<specifics>
## Specific Ideas

- Tests (QA-06, "notificaciones (envío mockeado)"): mock the Telegram httpx POST and the SMTP
  send. Cover: (1) only TELEGRAM env set → Telegram path, no email; (2) only SMTP env set →
  email path; (3) neither set → silent skip, no error, nothing marked seen; (4) send **fails**
  → job stays `seen=0` and reappears in the next `get_undelivered_qualifying` call; (5) send
  succeeds → job marked `seen=1`, absent from next digest (SC4) — assert across a simulated
  restart (new storage instance, same db file); (6) only strong_fit/good_fit above threshold
  are selected (a maybe / a low-score strong_fit is excluded); (7) `import app.notifications`
  does not load streamlit/apscheduler.
- Telegram 4096-char chunking: add a test with enough offers to force ≥2 chunks and assert no
  offer is split across chunks and each delivered offer is marked seen.

</specifics>

<deferred>
## Deferred Ideas

- HTML email template / rich formatting → v2.x (plain text for v2.0).
- Multiple simultaneous channels (Telegram AND email) → out of scope; NOTIF-02 is "Telegram O
  email" (single channel).
- Retry/backoff on transient send failures → v2.x (v2.0 relies on the next scheduled run).
- Per-offer "apply" action buttons / inline keyboard in Telegram → v2.x.
- UI status panel consuming runs.notified count → Phase 10 (UI-09).
- Salary in the digest line → tied to deferred SCORE-16 (salary extraction), v2.x.

</deferred>

---

*Phase: 9-notifications-digest*
*Context gathered: 2026-05-25*
