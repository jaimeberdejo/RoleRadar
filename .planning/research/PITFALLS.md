# Pitfalls Research

**Domain:** Standalone Python app — Streamlit UI + APScheduler worker + in-process BGE-M3 + SQLite multi-process + JSearch API client + Telegram/email delivery
**Researched:** 2026-05-24
**Confidence:** HIGH (verified against Context7, official docs, and multiple authoritative sources)

> Scope: pitfalls specific to ADDING these features to the existing v1.x codebase. Generic Python/web issues not included.

---

## Critical Pitfalls

### Pitfall 1: Streamlit runs scoring/search synchronously, blocking the entire UI

**What goes wrong:**
When a user clicks "Run Search" or "Score Jobs", Streamlit executes the handler top-to-bottom in the main thread. BGE-M3 embedding (~2–10 s per batch) and JSearch HTTP calls (1–3 s per page) all block. The browser shows a frozen spinner; the user cannot interact with any other widget; a second browser tab for the same app is also blocked because there is only one Python thread executing the script. If the call raises an exception partway through, Streamlit reruns the entire page with no partial results shown.

**Why it happens:**
Streamlit's execution model is inherently synchronous: the entire script re-executes top-to-bottom on every interaction. There is no built-in async or worker-pool mechanism for long-running operations. Developers accustomed to frameworks with request handlers assume the button callback can just call the scoring pipeline and return when done.

**How to avoid:**
- Offload the pipeline to a `threading.Thread` or `concurrent.futures.ThreadPoolExecutor` started from the button callback. Store progress/results in `st.session_state` and poll with `st.rerun()` or use `st.status()` as a context manager that wraps the thread-join loop.
- The official pattern (verified in Context7 docs) is to start threads in the button handler, keep all `st.write` / `st.dataframe` calls in the main script thread, and poll with a `while` loop + `time.sleep(0.1)` + `st.rerun()`.
- Never call `st.write` or any Streamlit command from inside the worker thread itself — it uses an internal `ScriptRunContext` that is not propagated to non-main threads (the `add_script_run_ctx` workaround exists but is an unsupported internal API).
- Show `st.spinner` or `st.status(state="running")` while the thread is alive; update to `state="complete"` after join.

**Warning signs:**
- The Streamlit tab hangs for > 3 s with no intermediate progress visible.
- A second browser tab is also unresponsive during a search.
- A `StreamlitAPIException: Calling st.X() from a thread` error appears in logs.

**Phase to address:** Phase adding Streamlit UI + JSearch client (first UI phase). Design the "Run Search" handler with threading from day one; retrofitting is painful.

---

### Pitfall 2: BGE-M3 model reloaded on every Streamlit rerun

**What goes wrong:**
BGE-M3 via `sentence-transformers` takes 5–20 s to load from disk and allocates ~2–4 GB of RAM. If the `BgeM3Embedder` or its underlying `SentenceTransformer` is instantiated anywhere in the top-level script flow (not inside a `@st.cache_resource` function), it reloads on every single rerun — which happens on every button click, widget change, or manual page refresh. This makes the app unusably slow and may OOM-kill the container.

**Why it happens:**
The existing `BgeM3Embedder` uses a lazy-load pattern (`_ensure_loaded()`) that correctly avoids loading at import time, but that only prevents the initial import cost. Each time Streamlit reruns the script, a new `BgeM3Embedder()` instance is created (fresh `_model = None`), so the lazy load triggers again on the first `embed()` call.

**How to avoid:**
Wrap the embedder construction in `@st.cache_resource` so the singleton is created once per server process and shared across reruns and sessions:

```python
import streamlit as st
from app.dedup.embedder import BgeM3Embedder

@st.cache_resource
def get_embedder() -> BgeM3Embedder:
    return BgeM3Embedder()  # lazy load fires here on first call
```

Then call `get_embedder()` everywhere instead of `BgeM3Embedder()`. The `@st.cache_resource` cache persists for the lifetime of the Streamlit server process (not the session), which is exactly what you want for a heavyweight singleton.

Do NOT use `@st.cache_data` — it serializes/deserializes the return value using pickle, which fails for PyTorch model objects.

**Warning signs:**
- Streamlit log shows "Cargando modelo BAAI/bge-m3 (primera llamada)..." more than once after server startup.
- Each button click takes 10+ s even for simple operations.
- Memory usage climbs linearly with interactions instead of stabilizing.

**Phase to address:** First phase that wires Streamlit to the dedup/scoring pipeline. Add the `@st.cache_resource` wrapper before any integration test.

---

### Pitfall 3: APScheduler job fires in the Streamlit process, stops when the browser closes

**What goes wrong:**
If APScheduler is instantiated inside the Streamlit script (even with `start_in_background()`), it runs in the same OS process as the Streamlit server. When the Streamlit server is idle (no active browser connections), the process may be killed by Docker or by the OS. More importantly, if the developer restarts the Streamlit process to pick up a code change, the scheduler is lost. In some deployment modes, `streamlit run` forks per session, causing the scheduler to be instantiated once per user session — triggering the job N times.

**Why it happens:**
APScheduler documentation explicitly warns: "Sharing a persistent job store among two or more processes will lead to incorrect scheduler behavior, because APScheduler lacks inter-process synchronization." The same applies in reverse: putting the scheduler inside a web-process that can be restarted independently of the schedule makes it unreliable.

**How to avoid:**
Run the APScheduler worker as a **completely separate Docker service** (a second container entry in `docker-compose.yml`) that imports the core modules directly (`app.dedup`, `app.scoring`, `app.storage`) and never imports Streamlit. The two containers share only the SQLite volume. The Streamlit UI never touches the scheduler; it only reads from SQLite.

```yaml
# docker-compose.yml sketch
services:
  ui:
    command: streamlit run streamlit_app/main.py
  worker:
    command: python -m worker.scheduler  # pure Python, no Streamlit
```

**Warning signs:**
- Jobs fire twice (once from UI process, once from worker process).
- Jobs stop firing after the browser tab is closed.
- After `docker compose restart ui`, scheduled runs are missed.

**Phase to address:** Worker/scheduler phase. This is an architectural decision that must be made before writing a single line of scheduler code.

---

### Pitfall 4: APScheduler double-fires when both containers schedule the same job

**What goes wrong:**
If both the UI container and the worker container each call `scheduler.add_schedule(run_search, ...)` on startup, and both point to the same SQLite data store, the same job will fire in both processes simultaneously. This causes duplicate job runs, duplicate JSearch API calls (wasting quota), duplicate DB writes, and duplicate Telegram messages.

**Why it happens:**
APScheduler's `SQLAlchemyDataStore` (or a file-based store) is not designed for multi-writer coordination. The `conflict_policy=ConflictPolicy.replace` option mitigates it partially but does not prevent simultaneous execution from two independent scheduler instances both believing they own the job.

**How to avoid:**
Only ONE process — the dedicated worker container — ever instantiates `Scheduler` and calls `add_schedule`. The UI container never touches APScheduler at all. Use `conflict_policy=ConflictPolicy.replace` in the worker to handle restarts without creating duplicate schedules:

```python
scheduler.add_schedule(
    run_daily_search,
    CronTrigger(hour=8, minute=0, timezone="Europe/Madrid"),
    id="daily_search",
    conflict_policy=ConflictPolicy.replace,  # safe on worker restart
)
```

**Warning signs:**
- Telegram receives two identical digest messages within seconds of each other.
- JSearch quota drops twice as fast as expected.
- SQLite upsert logs show double the expected inserts per run.

**Phase to address:** Worker/scheduler phase, same as Pitfall 3. The single-owner rule must be enforced in the architecture design, not added as a patch later.

---

### Pitfall 5: Missed runs after container restart — misfire_grace_time and timezone bugs

**What goes wrong:**
APScheduler 4.x changed from pytz to `zoneinfo` for timezone handling. If `pytz` timezone objects (e.g., `pytz.timezone("Europe/Madrid")`) are passed to triggers, they are silently misinterpreted. Additionally, if the worker container restarts while the scheduled time passes, and `misfire_grace_time` is not set or set too low, the job is silently skipped until the next schedule window.

In Docker, the default container timezone is UTC. A cron trigger for `hour=8` with no explicit timezone fires at 08:00 UTC (09:00 Madrid in winter, 10:00 in summer) — not at 08:00 local time.

**Why it happens:**
APScheduler 4.x migration guide explicitly states: "pytz zones are no longer supported; use `zoneinfo.ZoneInfo`." The timezone default when no timezone is specified is the process local time (set by `TZ` env var in Docker) or UTC if `TZ` is unset.

**How to avoid:**
- Always pass `timezone=ZoneInfo("Europe/Madrid")` explicitly to `CronTrigger`.
- Set `TZ=Europe/Madrid` in the worker container's environment as a belt-and-suspenders measure.
- Set `misfire_grace_time=3600` (1 hour) so that a job scheduled for 08:00 that fires at 08:45 after a restart is still executed rather than skipped.
- Set `coalesce=CoalescePolicy.latest` so accumulated missed runs fire once, not N times.

```python
from zoneinfo import ZoneInfo
CronTrigger(hour=8, minute=0, timezone=ZoneInfo("Europe/Madrid"))
```

**Warning signs:**
- Scheduled searches run at unexpected clock times.
- After `docker compose restart worker`, the next run is skipped entirely.
- Multiple runs fire back-to-back on restart.

**Phase to address:** Worker/scheduler phase. Add timezone + misfire config to the very first scheduler setup; do not leave defaults.

---

### Pitfall 6: SQLite "database is locked" when Streamlit reads while worker writes

**What goes wrong:**
The worker writes a batch of scored jobs to SQLite in a transaction. Simultaneously, the Streamlit UI queries the history table. Without WAL mode, SQLite uses a file-level lock: the reader blocks until the writer finishes, and if the writer holds the lock longer than the default timeout (0 ms), the reader gets an immediate `sqlite3.OperationalError: database is locked`. With the existing `connection-per-call` pattern, the timeout is never configured, so the error fires reliably under concurrent access.

**Why it happens:**
The existing `SQLiteStorage._connect()` does not set `PRAGMA journal_mode=WAL` or `PRAGMA busy_timeout`. The default journal mode (DELETE/rollback) allows only one connection at a time. A worker writing 50+ rows in a single transaction can hold the lock for 100–500 ms — long enough for the UI to fail.

**How to avoid:**
Enable WAL mode and set a busy_timeout in `_connect()`:

```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")  # wait up to 5 s before giving up
    return conn
```

WAL allows concurrent readers while a single writer is active. The `busy_timeout` makes readers retry for up to 5 s instead of failing instantly. Keep worker write transactions short (the existing batch-insert design is correct; do not add reads inside the write transaction). For write-after-read patterns (read then write in one transaction), use `BEGIN IMMEDIATE` to avoid the read-to-write upgrade failure that bypasses `busy_timeout`.

**Warning signs:**
- `sqlite3.OperationalError: database is locked` in Streamlit logs during a scheduled run.
- The history page in the UI shows a Python traceback exactly when the worker is active.
- The issue disappears when the worker is stopped.

**Phase to address:** SQLite/storage phase, or as a targeted fix at the start of v2.0 before any multi-process work. Must be in place before the worker and UI run concurrently.

---

### Pitfall 7: RapidAPI key already leaked inline in docker-compose.yml — must rotate before shipping v2.0

**What goes wrong:**
The current `docker-compose.yml` contains a hardcoded RapidAPI key inline:
```
RAPIDAPI_KEY: <REAL-KEY-REDACTED>
```
**CORRECTION (verified 2026-05-24):** this inline value is present ONLY in the working
tree — `docker-compose.yml` shows as modified (`M`) and the hardcoded value is **NOT in
any committed history** (`git log --all -p -- docker-compose.yml` finds no key; the file
was committed at v1.1 with the line left out on purpose). So **no history rewrite is
needed** — a simple edit + key rotation is sufficient. The key still leaked in chat
multiple times, so it must be rotated regardless.

**Why it happens:**
The key was used by n8n for JSearch calls and was edited inline during v1.x development,
but deliberately kept out of the v1.1 commit. n8n is being removed in v2.0; the inline
value just needs to be replaced before it ever gets committed.

**How to avoid:**
1. Rotate the key immediately at RapidAPI (generate a new key; invalidate the old one) — it leaked in chat.
2. Replace the inline value with `${RAPIDAPI_KEY:-}` (already the pattern elsewhere in the same file for other vars) so the working-tree value never gets committed.
3. Add `RAPIDAPI_KEY=` to `.env.example` with a placeholder.
4. (History rewrite NOT required — the value was never committed. Only relevant if that ever changes.)
5. In the new JSearch client module, read the key exclusively via `os.environ` / python-dotenv — never as a default value in function signatures or as a module-level constant.

**Warning signs:**
- `git log -S "<key-prefix>"` returns results (currently it does NOT — the value is uncommitted).
- The `.env` file is not listed in `.dockerignore` or `.gitignore`.
- The JSearch client has a `rapidapi_key: str = "..."` default in its constructor.

**Phase to address:** Cleanup/architecture phase at the very beginning of v2.0, before the JSearch client is written. Do not let v2.0 ship with the old key in history if the repo will be public.

---

### Pitfall 8: JSearch client not handling 429 / quota exhaustion, killing the entire batch

**What goes wrong:**
RapidAPI free/basic tiers for JSearch have per-minute and per-month limits (typically 10 req/min, 200–500 req/month on free plans). If the JSearch client calls the API in a tight loop for multiple query terms (e.g., "AI Engineer Barcelona", "ML Engineer remote Spain") without rate limiting, it gets HTTP 429 immediately. If the client raises an unhandled exception, the entire scheduler run fails, no jobs are processed, and the error may go unnoticed until the next morning.

Paging is equally dangerous: fetching `num_pages=10` per query with 3 queries = 30 API calls per run. At 200 calls/month, this exhausts the quota in less than a week.

**Why it happens:**
A naive implementation fetches all pages synchronously in a loop. Without explicit retry/backoff, a single transient 429 aborts everything. Without quota tracking, the developer doesn't notice until jobs stop appearing in the UI.

**How to avoid:**
- Wrap every JSearch HTTP call in a retry loop with exponential backoff: catch HTTP 429, read the `Retry-After` header if present, otherwise wait 60 s, then retry up to 3 times before giving up on that query (not the whole run).
- Return partial results when a query fails — do not raise from the batch loop; log and continue.
- Make `num_pages` configurable and default to 1 (the v1.x n8n workflow already changed from 10 to 1 for this reason — keep that default).
- Log the `X-RateLimit-Requests-Remaining` header (if present) so quota is visible in structured logs.
- Isolate each query term's fetch in a try/except so one failing query does not abort the others.

**Warning signs:**
- Streamlit history page shows 0 new jobs after a scheduled run.
- Worker logs contain `httpx.HTTPStatusError: 429` with no retry evidence.
- RapidAPI dashboard shows quota near 0 mid-month.

**Phase to address:** JSearch client phase. The retry/partial-result pattern must be built into the client from the start, not added as a follow-up.

---

### Pitfall 9: Embeddings-based scoring silently imports or requires OpenAI

**What goes wrong:**
The v1.x `scorer.py` always calls `build_instructor_client()` which immediately fails if `OPENAI_API_KEY` is not set (raises `openai.AuthenticationError` or similar at client construction time). In v2.0, OpenAI is optional — the app must score fully offline. If the embeddings-first scorer still calls `build_instructor_client()` unconditionally at the top of `score_job()`, the entire scoring pipeline fails for users without an API key, and the "optional enrichment" goal is broken.

**Why it happens:**
The existing `scorer.py` step 1 reads: "Paso 1: cliente lazy — construye el cliente instructor si no se inyecta." The lazy build defers the failure to first call, but still fails. Developers retrofitting "optional" behavior tend to add `if OPENAI_API_KEY: enrich(...)` at the end, but forget to guard the client construction earlier.

**How to avoid:**
Restructure `score_job()` so all numerical scores (encaje_puesto, encaje_skills via embeddings, encaje_ubicacion, encaje_seniority) are computed first without any LLM client. Only after the deterministic score is complete, check `if openai_available(): assessment = assess_job(...)` and populate `reasons_for`, `reasons_against`, `matched_skills`, `missing_requirements` from the LLM. If `OPENAI_API_KEY` is absent, populate those fields with empty lists and a note like `"LLM enrichment disabled (no OPENAI_API_KEY)"`.

Add a startup check: `if not os.getenv("OPENAI_API_KEY"): logger.warning("OpenAI not configured — LLM enrichment disabled; scores are embeddings-only")`. This makes the degraded mode visible without breaking the pipeline.

**Warning signs:**
- Starting the app without `OPENAI_API_KEY` raises an exception during import or first scoring call.
- The scoring test suite requires mocking `openai` even for purely-deterministic scoring tests.
- `app/scoring/scorer.py` imports `instructor` at the module level (rather than inside `build_instructor_client()`).

**Phase to address:** Scoring reposition phase (embeddings-first). The guard must be added before the scoring module is wired into the UI or worker.

---

### Pitfall 10: Scoring weights/thresholds drift silently when tuned from the UI

**What goes wrong:**
The UI allows Jaime to adjust scoring weights (puesto %, skills %, ubicacion %, seniority %) and the dedup cosine threshold. If these are written back to `profile.yaml` on every UI change (or written to a separate config file), and the worker also reads `profile.yaml` at each run, there is a race condition: the worker reads a partially-written YAML file while the UI is saving it. The result is either a corrupt config (YAML parse error) or silently incorrect weights (e.g., weights that do not sum to 1.0 after partial save).

Additionally, if weights are stored only in `st.session_state` (not persisted), they reset on every Streamlit restart and the worker never sees them.

**Why it happens:**
Streamlit's `session_state` is per-session in-memory. Developers assume "I wrote to session_state" means "the config is saved", but the worker process has no access to Streamlit's session memory.

**How to avoid:**
- Use a dedicated `config.json` or append a `[scoring_overrides]` section to `profile.yaml` that is written atomically (write to a temp file, then `os.replace(temp, target)` — atomic on POSIX).
- The worker reads the same file at the start of each run (not once at startup) so UI changes take effect on the next scheduled run.
- Validate weights after loading: assert they sum to ~1.0 (± 0.01); log a warning and fall back to defaults if not.
- Write a unit test that verifies `sum(pesos.values()) == 1.0` for the default `profile.yaml`.

**Warning signs:**
- Weight changes in the UI have no effect on the next scheduled run.
- Worker logs show `yaml.YAMLError` after a UI save.
- `profile.yaml` contains fractional weights that do not sum to 1.0.

**Phase to address:** UI configuration phase + scoring reposition phase. The persistence strategy for user-adjusted weights must be defined before the UI sliders are wired up.

---

### Pitfall 11: Telegram/email delivery fails silently, seen-tracking breaks, duplicates sent

**What goes wrong:**
Three distinct failure modes:
1. **Silent send failure:** The delivery function raises `TelegramError` or `smtplib.SMTPException`; the worker catches it with a bare `except Exception: pass` to avoid crashing the run; no retry; the user never gets the digest and does not know why.
2. **Duplicates on retry:** A delivery attempt sends 3 jobs, then fails mid-batch. On retry (next run or manual), the `seen` flag was already set to 1 for those 3 jobs (because `upsert_scored_jobs` runs before delivery). The user sees those 3 jobs duplicated in the next digest. Or the inverse: `seen` is set only after successful delivery, but the worker crashes between delivery and the DB update, causing infinite re-delivery.
3. **Message too long:** A Telegram `sendMessage` call with a full digest of 20+ jobs exceeds the 4096-character limit. The API returns error 400 `MESSAGE_TOO_LONG`; the entire digest is lost.

**Why it happens:**
The `seen` column in the existing `jobs` table is never updated to 1 after notification (looking at `sqlite.py`, `upsert_scored_jobs` sets `seen=0` on insert and never flips it). There is no delivery step in v1.x. The seen-tracking and delivery flow must be designed together.

**How to avoid:**
- Mark jobs as `seen=1` in the DB **only after** the delivery call succeeds. Use a two-step transaction: deliver → on success, `UPDATE jobs SET seen=1 WHERE id IN (...)`.
- Wrap delivery in a retry loop with exponential backoff (3 attempts, wait 30s/60s/120s). Log each failure with full error details. If all retries fail, log a `CRITICAL` and leave `seen=0` so the next run retries.
- For Telegram: chunk the digest into batches of N jobs where each batch fits under 3500 characters (leaving margin). The python-telegram-bot v20 `AIORateLimiter` handles 429 rate limiting automatically.
- For email: use `SMTP.sendmail()` inside a try/except; catch `SMTPRecipientsRefused`, `SMTPAuthenticationError` separately and log actionable messages.
- Add an integration test with a mock sender that records calls and verifies `seen=1` is set only after successful mock delivery.

**Warning signs:**
- `jobs.seen` stays 0 for all rows despite runs completing.
- Duplicate job titles appear in consecutive digests.
- Worker logs show a Telegram 400 error with no retry.

**Phase to address:** Delivery phase (Telegram/email). The seen-tracking DB update and delivery retry must be designed together, not added independently.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Running APScheduler inside the Streamlit process | One container instead of two | Jobs stop firing when UI restarts; double-fire risk | Never — defeats the "always-on worker" requirement |
| Using `st.cache_data` instead of `st.cache_resource` for BGE-M3 | Simpler decorator | Model pickled/unpickled on every cache hit; fails for PyTorch objects | Never for ML models |
| Hardcoding `num_pages=10` for JSearch | More results per run | Quota exhausted in days on free tier | Never — make it configurable, default 1 |
| Synchronous embedding in the Streamlit button handler | Simpler code | UI frozen for 5–20 s per click | Acceptable only for a proof-of-concept that will not be demo'd |
| Writing `PRAGMA journal_mode=WAL` only once at `init_db()` | Avoid repeated pragma | WAL mode is per-database-file but must be set per-connection in some SQLite versions | Set it in `_connect()` for safety |
| Storing scoring weights only in `st.session_state` | Fast to implement | Worker never sees them; resets on restart | Never if the worker must use the same weights |
| Bare `except Exception: pass` around delivery | Doesn't crash the worker run | Silent delivery failures; user misses digests with no indication | Never — at minimum log at CRITICAL level |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| JSearch / RapidAPI | Calling all pages in a tight loop without rate limiting | Retry on 429 with backoff; isolate per-query errors; default num_pages=1 |
| JSearch / RapidAPI | Reading RAPIDAPI_KEY from docker-compose literal | Read exclusively from `.env` via `os.environ`; rotate the currently leaked key |
| APScheduler 4.x | Passing `pytz.timezone(...)` to `CronTrigger` | Use `zoneinfo.ZoneInfo("Europe/Madrid")` — pytz removed in v4 |
| APScheduler 4.x | Using `add_job()` for recurring work | Use `add_schedule()` for recurring; `add_job()` is one-off in v4 |
| Telegram Bot API | Sending a full multi-job digest as one message | Chunk into ≤ 3500-char messages; handle 400 `MESSAGE_TOO_LONG` explicitly |
| Telegram Bot API | No retry on transient 5xx | Use python-telegram-bot v20 built-in `AIORateLimiter` or manual retry |
| SQLite multi-process | Default journal mode with multi-process access | `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000` in `_connect()` |
| BGE-M3 via sentence-transformers | Instantiating `BgeM3Embedder()` at script top-level | Wrap in `@st.cache_resource` factory function |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| BGE-M3 loaded per Streamlit rerun | 10–20 s lag on every button click | `@st.cache_resource` wrapper | Immediately on first button click |
| JSearch fetching 10 pages × N queries | Quota exhausted in < 1 week on free tier | Default num_pages=1; make configurable | Day 3–5 of real usage |
| Embedding all historical jobs for dedup every run | Run time grows linearly with DB size | Only embed new-since-last-run jobs; cache existing embeddings | After ~500 stored jobs |
| SQLite WAL checkpoint on a 1+ GB WAL file | Read performance degrades; checkpoint locks all readers | Set `PRAGMA wal_autocheckpoint=1000` (already SQLite default); monitor WAL file size | After sustained high-write periods |
| Scoring all fetched jobs with LLM before dedup | Costs LLM tokens on duplicates | Run dedup first, then score only unique jobs (existing architecture is correct — verify it's preserved) | From the first LLM-enabled run |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| RapidAPI key inline in `docker-compose.yml` working tree (uncommitted — NOT in git history) | Quota theft if committed; key already leaked in chat | Rotate key immediately; replace inline value with `${RAPIDAPI_KEY:-}` before any commit; add to `.env.example` |
| `OPENAI_API_KEY` in `.env` committed to git | API cost abuse | Verify `.env` is in `.gitignore` and `.dockerignore` (already correct in v1.x) |
| Telegram bot token readable in docker-compose env section | Bot hijack; spam to Jaime's account | Store in `.env` only; never log the token value; use python-dotenv |
| SMTP password visible in logs | Credential exposure | Never log `EMAIL_PASSWORD`; use `logging.Filter` to scrub secrets from log records |
| SQLite file world-readable in Docker volume | Local data exposure | Set volume permissions; this is low risk for a single-user local tool but worth noting |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress feedback during "Run Search" (30+ s operation) | User clicks the button multiple times thinking it hung | `st.status("Searching...", expanded=True)` with live log lines via `st.write` inside the status |
| Weight sliders reset on page refresh | Frustrating to re-tune after restart | Persist weight overrides to a file; load from file on startup |
| History page loads all rows at once (no pagination) | Slow render when DB has 500+ rows | Use `LIMIT / OFFSET` in `get_history()`; add a "Load more" button |
| Scheduling config (time of day) not editable in UI | Requires editing docker-compose to change run time | Expose `cron_hour` / `cron_minute` in profile.yaml UI section |
| No indication that the worker is running / last ran | User doesn't know if the scheduler is alive | Show "Last run: 2026-05-24 08:00" and "Next run: 2026-05-25 08:00" from DB metadata |

---

## "Looks Done But Isn't" Checklist

- [ ] **BGE-M3 caching:** Verify `@st.cache_resource` is applied — run the app, click a button, click it again, confirm "Cargando modelo BAAI/bge-m3" appears only once in logs.
- [ ] **Worker isolation:** Verify the worker container has no `import streamlit` anywhere in its dependency chain.
- [ ] **Seen-tracking:** After a scheduled run + delivery, query `SELECT seen, count(*) FROM jobs GROUP BY seen` — `seen=1` should cover the delivered batch.
- [ ] **WAL mode active:** After starting both containers, run `PRAGMA journal_mode;` against `jobs.db` — should return `wal`, not `delete`.
- [ ] **No hardcoded key:** `git log -S "<key-prefix>"` returns zero results (it already does — value is uncommitted), AND the working-tree `docker-compose.yml` uses `${RAPIDAPI_KEY:-}` not the literal.
- [ ] **Offline scoring works:** Start the app with no `OPENAI_API_KEY` set, run a search, confirm scores appear (even if `reasons_for` is empty) without any exception.
- [ ] **Timezone correct:** Trigger a test job at a known time; confirm it fires at 08:00 Madrid time, not 08:00 UTC.
- [ ] **Partial JSearch failure handled:** Simulate a 429 from JSearch (mock or via test); confirm other query terms still return results and the run does not abort entirely.
- [ ] **Telegram message fits:** Generate a digest with 30 mock jobs; confirm it is chunked into multiple messages rather than one oversized call.
- [ ] **Weights persist across restarts:** Change a weight slider, restart the Streamlit container, confirm the slider reflects the saved value.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| BGE-M3 reloaded per rerun | LOW | Add `@st.cache_resource` wrapper; no data loss |
| APScheduler in wrong process | MEDIUM | Refactor into separate Docker service; update docker-compose; no data loss |
| SQLite locked errors | LOW | Add WAL + busy_timeout to `_connect()`; existing data unaffected |
| RapidAPI key leaked | MEDIUM | Rotate key at RapidAPI dashboard immediately; replace inline working-tree value with `${RAPIDAPI_KEY:-}`; new key in `.env`. (No history rewrite — value was never committed.) |
| Delivery duplicates | MEDIUM | Write migration to reset `seen=0` for jobs incorrectly marked; fix delivery+seen-update ordering |
| Timezone misconfiguration | LOW | Fix `ZoneInfo` argument in `CronTrigger`; manually trigger next run |
| OpenAI not optional | MEDIUM | Refactor `score_job()` to gate LLM call; existing test mocks still valid |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Streamlit blocking UI on long operations | UI phase (Streamlit + JSearch client) | Click "Run Search" in UI; confirm other widgets remain interactive |
| BGE-M3 reloaded per rerun | UI phase, when wiring dedup/scoring to Streamlit | Check logs for single model-load event per server start |
| APScheduler in wrong process | Worker/scheduler phase (architecture) | `docker ps` shows two separate containers; stop UI → jobs still fire |
| APScheduler double-fire | Worker/scheduler phase | Only one process in compose has `Scheduler` import; grep confirms |
| Misfire/timezone bugs | Worker/scheduler phase | Test cron fires at correct local time; restart test |
| SQLite locked multi-process | Storage/SQLite hardening (early v2.0) | Run simultaneous UI read + worker write; no OperationalError |
| RapidAPI key leaked | Cleanup phase (first task of v2.0) | `git log -S <key>` returns nothing |
| JSearch 429 / batch failure | JSearch client phase | Mock 429; assert partial results returned |
| OpenAI not optional | Scoring reposition phase | Run scoring with no API key; assert no exception |
| Weight drift / no persistence | UI configuration phase | Change weights; restart Streamlit; confirm values persisted |
| Delivery failures / duplicates | Delivery phase (Telegram/email) | Mock failed send; confirm seen=0 retained; retry succeeds |

---

## Sources

- [APScheduler FAQ — multiple workers / web app process issues](https://apscheduler.readthedocs.io/en/3.x/faq.html) — HIGH confidence (official docs)
- [APScheduler migration guide v3→v4 — pytz→zoneinfo, add_job→add_schedule](https://apscheduler.readthedocs.io/en/master/migration.html) — HIGH confidence (official docs)
- [APScheduler coalesce + misfire_grace_time examples](https://context7.com/agronholm/apscheduler/llms.txt) — HIGH confidence (Context7)
- [Streamlit cache_resource official docs — ML model caching, mutation pitfalls](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource) — HIGH confidence (official docs)
- [Streamlit multithreading docs — thread + main-thread st.write pattern](https://github.com/streamlit/docs/blob/main/content/develop/concepts/app-design/multithreading.md) — HIGH confidence (Context7)
- [Streamlit issue #3290 — transformers infinite reload without cache_resource](https://github.com/streamlit/streamlit/issues/3290) — MEDIUM confidence (community issue)
- [SQLite concurrent writes and "database is locked" errors](https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/) — HIGH confidence (verified against SQLite WAL docs)
- [SQLite WAL official documentation](https://sqlite.org/wal.html) — HIGH confidence (official docs)
- [SQLITE_BUSY despite timeout — write-after-read upgrade pattern](https://berthug.eu/articles/posts/a-brief-post-on-sqlite3-database-locked-despite-timeout/) — MEDIUM confidence (engineering blog, consistent with official docs)
- [Common APScheduler mistakes — double scheduling in multi-process apps](https://sepgh.medium.com/common-mistakes-with-using-apscheduler-in-your-python-and-django-applications-100b289b812c) — MEDIUM confidence (community blog, consistent with official FAQ)
- [Telegram message length 4096 char limit](https://github.com/yagop/node-telegram-bot-api/issues/165) — HIGH confidence (verified against Telegram Bot API docs)
- [python-telegram-bot v20 rate limiting / retry](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Avoiding-flood-limits) — HIGH confidence (official wiki)
- [Handling leaked secrets in git history](https://medium.com/@mgaurang123/handling-leaked-secrets-and-credentials-in-version-control-repositories-e11149b8a8b9) — MEDIUM confidence (standard practice, consistent with GitHub docs)
- Existing codebase analysis: `app/storage/sqlite.py`, `app/dedup/embedder.py`, `app/scoring/scorer.py`, `docker-compose.yml` — HIGH confidence (direct inspection)

---
*Pitfalls research for: BuscadorDeEmpleo v2.0 — Streamlit + APScheduler + SQLite multi-process + JSearch + delivery*
*Researched: 2026-05-24*
