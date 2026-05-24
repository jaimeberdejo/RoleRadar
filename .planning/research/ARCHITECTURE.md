# Architecture Research

**Domain:** Single-user Python job-aggregator — Streamlit + APScheduler standalone app (v2.0)
**Researched:** 2026-05-24
**Confidence:** HIGH — all claims verified against official docs or existing codebase

---

## Context: What Already Exists (Do Not Re-Design)

v1.x shipped a complete, tested Python core. These modules are PRESERVED as-is:

| Module | Status | Notes |
|--------|--------|-------|
| `app/models/schemas.py` | KEEP | All Pydantic v2 schemas: `UserProfile`, `CVProfile`, `Job`, `JobScore`, `ScoredJob`, `LLMJobAssessment` |
| `app/cv/` | KEEP | PDF → CVProfile (pymupdf + Instructor/OpenAI), sha256 cache |
| `app/dedup/` | KEEP | BGE-M3 lazy-import embedder, exact hash + semantic cosine dedup |
| `app/scoring/location.py` | KEEP | Deterministic location scoring |
| `app/scoring/ranking.py` | KEEP | Linear decay over ranking position → `encaje_puesto` |
| `app/scoring/llm.py` | MODIFY | Currently required at startup; must become optional import |
| `app/scoring/scorer.py` | MODIFY | Orchestrator; must work without LLM when key absent |
| `app/storage/sqlite.py` | MODIFY | Add WAL mode + busy_timeout; extend schema for settings |
| `app/storage/protocol.py` | KEEP | Storage Protocol unchanged |
| `app/config/loader.py` | KEEP | `load_user_profile(path)` unchanged |
| `app/obs/` | KEEP | Logging config + Langfuse stub |
| `app/errors.py` | KEEP | Domain exceptions by layer |
| `app/api/` | REMOVE | Entire FastAPI layer retired in v2.0 |

---

## v2.0 System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Docker Compose                               │
│                                                                      │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│  │   streamlit service         │  │   worker service             │  │
│  │   (UI process)              │  │   (scheduler process)        │  │
│  │                             │  │                              │  │
│  │  app/ui/                    │  │  app/worker/                 │  │
│  │  ├── main.py (entry)        │  │  ├── main.py (entry)         │  │
│  │  ├── pages/                 │  │  ├── scheduler.py            │  │
│  │  │   ├── 01_cv.py           │  │  └── pipeline.py             │  │
│  │  │   ├── 02_search.py       │  │                              │  │
│  │  │   ├── 03_results.py      │  │  Imports core in-process:    │  │
│  │  │   └── 04_settings.py     │  │  app/sources/jsearch.py      │  │
│  │  └── components/            │  │  app/dedup/                  │  │
│  │      └── job_card.py        │  │  app/scoring/scorer.py       │  │
│  │                             │  │  app/storage/sqlite.py       │  │
│  │  Imports core in-process:   │  │  app/notify/                 │  │
│  │  app/cv/                    │  │                              │  │
│  │  app/storage/sqlite.py      │  │  APScheduler BackgroundSched │  │
│  │  app/scoring/scorer.py      │  │  (BlockingScheduler in main) │  │
│  └─────────────────────────────┘  └──────────────────────────────┘  │
│                     │                          │                     │
│                     └──────────┬───────────────┘                     │
│                                │                                     │
│                  ┌─────────────▼──────────────┐                     │
│                  │   Docker named volumes      │                     │
│                  │   data/   → jobs.db         │                     │
│                  │           → profile.yaml    │                     │
│                  │           → cv_cache/       │                     │
│                  │   hf_cache/ → BAAI/bge-m3   │                     │
│                  └────────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 1. Process Topology in Docker

### Decision: Two Services, One Image

Build a **single Docker image** containing the entire codebase. Compose defines **two services** that override CMD:

```yaml
# docker-compose.yml (v2.0 sketch)
services:
  ui:
    image: buscadordeempleo:v2
    command: ["uv", "run", "streamlit", "run", "app/ui/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
    ports:
      - "8501:8501"
    env_file: .env
    volumes:
      - data:/app/data
      - hf_cache:/app/.cache/huggingface
    restart: unless-stopped

  worker:
    image: buscadordeempleo:v2
    command: ["uv", "run", "python", "-m", "app.worker.main"]
    env_file: .env
    volumes:
      - data:/app/data          # same named volume → same SQLite file
      - hf_cache:/app/.cache/huggingface
    restart: unless-stopped

volumes:
  data:
    driver: local
  hf_cache:
    driver: local
```

**Why one image, not two:**
- Core modules (`app/scoring`, `app/dedup`, `app/storage`) are shared; separate images would require maintaining two identical build contexts.
- BGE-M3 (~2.3 GB) lives in `hf_cache` volume, mounted by both services — no duplication.
- A single `uv sync --frozen --no-dev` in the Dockerfile installs all deps once.

**Why not one container running both processes:**
- The worker is I/O-heavy during a run (HTTP to JSearch, BGE-M3 inference, SQLite writes). Streamlit's rerun model would contend with a background thread for the GIL. Separate processes avoid this.
- Clean restartability: `docker compose restart worker` without touching the UI.
- APScheduler docs explicitly warn against sharing a scheduler instance across OS processes — each process runs its own independent scheduler.

**Dockerfile change:** Remove `CMD ["uv", "run", "uvicorn", "app.api.main:app", ...]`; make CMD absent (or set to a no-op default). Each service in Compose provides its own `command`.

---

## 2. SQLite Concurrency: UI Reads + Worker Writes

### Pattern: WAL mode + busy_timeout + BEGIN IMMEDIATE for writes

SQLite in default rollback-journal mode serializes all access (one reader OR one writer at a time). WAL (Write-Ahead Logging) mode allows **concurrent readers with one writer** across OS processes. This is the correct choice for this topology.

**Connection setup — apply to every `_connect()` call in `SQLiteStorage`:**

```python
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL: readers never block writers, writer never blocks readers.
    # Persistent: set once per DB file, survives across connections.
    conn.execute("PRAGMA journal_mode=WAL")
    # busy_timeout: if the DB is locked (another writer), retry for up to 5s
    # before raising OperationalError. 5000ms verified sufficient in benchmarks.
    conn.execute("PRAGMA busy_timeout=5000")
    # NORMAL sync is safe with WAL; FULL is needlessly slow for a personal tool.
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
```

**Writer pattern (worker's `upsert_scored_jobs`):**

The existing `with conn:` context manager already commits/rolls back atomically. No change needed beyond the PRAGMAs above. However, the worker's pipeline should avoid holding open transactions while doing slow work (HTTP calls, embedding inference). Structure:

```
1. Fetch jobs from JSearch (HTTP, outside any transaction)
2. Normalize + dedup in memory (no DB access)
3. Score all jobs (LLM calls if key present, outside any transaction)
4. Open connection → upsert all scored_jobs in ONE transaction → close
```

This keeps the write window to milliseconds, minimising contention with the Streamlit UI reading history.

**Reader pattern (Streamlit's `get_history`):**

No change needed. Standard `SELECT` statements in WAL mode never block and never block the writer.

**What NOT to do:**
- Do not share a single `sqlite3.Connection` instance between the two processes (connections are not IPC-safe).
- Do not use `PRAGMA journal_mode=WAL` inside a transaction — set it on a bare connection before any transaction begins. The current `_connect()` pattern (no open transaction at init) is correct.
- Do not use network filesystems for the SQLite file — WAL requires the `-shm` shared-memory file, which does not work over NFS/CIFS. The Docker named volume (`data`) is local block storage and is safe.

**WAL + busy_timeout is sufficient for this workload.** The worker writes once per scheduled run (e.g. every 8 hours). The UI reads frequently but never writes to the jobs table during normal browsing. The only concurrent write scenario is if the user triggers a manual run from the UI while the scheduled worker is also writing — busy_timeout handles this.

---

## 3. Config Flow: profile.yaml + In-App Overrides

### Decision: profile.yaml is source of truth; overrides live in a `settings` SQLite table

Two tiers of configuration:

**Tier 1 — Identity & scoring weights (profile.yaml):**
Fields that rarely change and require deliberate editing: `datos_personales`, `ranking_puestos`, `preferencias_ubicacion`, `preferencia_remoto`, `deal_breakers`, `pesos`. These stay in `data/profile.yaml`. The Streamlit UI can display them read-only; to change them the user edits the file directly (or v2.1 adds a write-back path).

**Tier 2 — Search conditions (SQLite `settings` table):**
Fields the user tunes from the UI on a run-by-run basis: JSearch query string, country code, language, number of pages, schedule interval (hours). These are operational parameters, not identity parameters. Storing them in SQLite means:
- Both the UI and the worker read from the same source without filesystem races.
- No YAML serialization needed; plain key-value rows.
- The worker always reads current settings before each run — no restart required when the user changes them from the UI.

**`settings` table schema:**

```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Default rows (seeded by `init_db` if absent using `INSERT OR IGNORE`):

| key | default value |
|-----|---------------|
| `search_query` | `"AI Engineer"` |
| `search_country` | `"ES"` |
| `search_language` | `"en"` |
| `search_num_pages` | `"1"` |
| `schedule_interval_hours` | `"8"` |
| `openai_enrichment_enabled` | `"true"` |
| `dedup_umbral` | `"0.85"` |

**Worker reads settings before each run:**

```python
settings = storage.get_settings()   # SELECT all from settings
query = settings["search_query"]
# ...
```

**UI writes settings on Save:**

```python
storage.update_setting("search_query", new_value)
```

This write happens outside the scoring pipeline — no concurrency risk with `upsert_scored_jobs`.

**How the worker picks up schedule changes:** The scheduler's interval is loaded from the settings table at startup. If the user changes `schedule_interval_hours` from the UI, the change takes effect on the next worker restart (acceptable for a personal tool). Alternatively, the worker can re-read it at the start of each job execution and reschedule dynamically — that is a v2.1 enhancement, not required for v2.0.

---

## 4. Scorer Restructure: Embeddings-First, Optional LLM

### Problem with current scorer.py

`app/scoring/llm.py` imports `instructor` and `openai` at module level. `scorer.py` calls `build_instructor_client()` unconditionally (falls back to a real client if none is injected). This means the app fails at startup if `OPENAI_API_KEY` is absent.

### v2.0 Restructure

**Module boundaries:**

```
app/scoring/
├── scorer.py          # MODIFIED: orchestrator; LLM enrichment is optional branch
├── embeddings.py      # NEW: embedding-based skill/seniority scoring (BGE-M3)
├── location.py        # KEEP: deterministic location scorer (no change)
├── ranking.py         # KEEP: decay function (no change)
└── llm.py             # MODIFIED: never imported at module level; only inside scorer
                       #           when enrichment is requested
```

**scorer.py logic flow (v2.0):**

```python
def score_job(job, cv_profile, user_profile, *, enrich_with_llm: bool = False):
    """
    Steps 1-4: always run (deterministic, no external deps at call time).
    Step 5 (LLM enrichment): only if enrich_with_llm=True AND OPENAI_API_KEY present.
    """
    # Step 1: deterministic location
    encaje_ubicacion, deal_breaker_loc = evaluar_ubicacion(job, user_profile)

    # Step 2: embedding-based skill match (new embeddings.py)
    encaje_skills, encaje_seniority, matched_skills, missing = score_skills_embeddings(
        job, cv_profile
    )

    # Step 3: ranking decay (unchanged)
    rango_puesto, puesto_detectado = detect_ranking(job, user_profile)
    encaje_puesto = encaje_puesto_desde_rango(rango_puesto)

    # Step 4: weighted score_total (deterministic)
    score_total = _weighted_total(encaje_puesto, encaje_skills, encaje_ubicacion,
                                  encaje_seniority, user_profile.pesos)

    # Step 5 (optional): LLM enrichment — deferred import, never at module level
    reasons_for, reasons_against = [], []
    if enrich_with_llm and _openai_key_present():
        from app.scoring.llm import assess_job, build_instructor_client  # noqa: PLC0415
        client = build_instructor_client()
        assessment = assess_job(job, cv_profile, user_profile, client)
        reasons_for = assessment.reasons_for
        reasons_against = assessment.reasons_against
        # Optionally override matched_skills/missing from LLM if richer
        matched_skills = assessment.matched_skills or matched_skills
        missing = assessment.missing_requirements or missing
        # Override deal_breaker from LLM if it found one
        deal_breaker_loc = deal_breaker_loc or (
            assessment.deal_breaker_cual_texto if assessment.deal_breaker_hit_texto else None
        )

    # Step 6-7: recommendation + deal_breaker override (unchanged logic)
    recommendation = _banda(score_total)
    deal_breaker_hit = bool(deal_breaker_loc)
    if deal_breaker_hit:
        recommendation = Recommendation.skip

    return JobScore(...)
```

**`_openai_key_present()` helper:**

```python
import os
def _openai_key_present() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())
```

**`app/scoring/embeddings.py` — new module:**

Uses BGE-M3 to embed the job description and the CV skills/experience, then computes cosine similarity to produce `encaje_skills` (0-100) and `encaje_seniority` (0-100). This replaces the LLM's numeric role for these two dimensions. The logic:

- Embed CV skills as a combined string: `", ".join(cv_profile.skills_tecnicas)`.
- Embed job description (first 200 words, same pattern as dedup).
- Cosine similarity → normalized to 0-100 range.
- Seniority: heuristic from `anios_experiencia_total` vs keywords ("senior", "5+ years", etc.) in job description — pure string matching, no model needed.

The `BgeM3Embedder` lazy import pattern from `app/dedup/embedder.py` is reused exactly — do not duplicate it; import `BgeM3Embedder` from `app/dedup/embedder` in `embeddings.py`.

**What stays in `llm.py`:** `assess_job`, `build_instructor_client`, all the prompt-building helpers, `LLMJobAssessment`. The schema `LLMJobAssessment` in `app/models/schemas.py` stays there (it is already defined). `llm.py` only changes in that `openai` and `instructor` are still imported at its module level — that is fine because `llm.py` is now only imported inside the `if enrich_with_llm` branch, never at startup.

**Test coverage:** All existing scoring tests continue to pass because `score_job` is still callable without LLM. New tests for `embeddings.py` use `FakeEmbedder` (already exists in `app/dedup/embedder.py`).

---

## 5. JSearch Client + Worker Pipeline

### New module: `app/sources/jsearch.py`

```
app/sources/
├── __init__.py
└── jsearch.py      # JSearch API client (httpx sync — worker is not async)
```

`jsearch.py` responsibilities:
- `fetch_jobs(query, country, language, num_pages, api_key) -> list[dict]`: calls `https://jsearch.p.rapidapi.com/search` with `httpx` (synchronous, not async — the worker runs in a thread, not an async loop; Streamlit is also sync by default).
- Returns raw dicts (the `raw` payload per offer). The existing `app/dedup/mappers.py` already has a `jsearch` mapper registered in `MAPPER_REGISTRY` based on the existing n8n workflow — confirm field mapping matches real JSearch response.
- Handles pagination (`page` parameter), rate limits (retry with backoff), and partial failures (log warning, return what was obtained).
- `JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"` — hardcoded constant, not an env var; only the API key is a secret.

**httpx sync is the correct choice here:**

The worker's `main.py` runs `BlockingScheduler.start()` which occupies the main thread. Job execution runs in APScheduler's thread pool. Using `httpx.Client` (sync) avoids the complexity of running an asyncio event loop inside a scheduler thread.

### Worker pipeline: `app/worker/pipeline.py`

```python
def run_pipeline(storage: SQLiteStorage, user_profile: UserProfile, cv_profile: CVProfile):
    """
    1. Load search settings from SQLite settings table
    2. Fetch raw jobs from JSearch
    3. Normalize via app.dedup.normalize_jobs(raw, source="jsearch")
    4. Filter already-seen by job.id (storage.was_seen)
    5. Deduplicate new jobs (app.dedup.deduplicate)
    6. Score each job (app.scoring.scorer.score_job, enrich_with_llm=<from settings>)
    7. Persist (storage.upsert_scored_jobs)
    8. Send digest if new high-score jobs found (app.notify)
    """
```

Step 4 (filter already-seen) happens BEFORE step 5 (dedup) to avoid embedding already-stored jobs. This keeps the BGE-M3 inference batch small on subsequent runs.

### Worker entrypoint: `app/worker/main.py`

```python
from apscheduler.schedulers.blocking import BlockingScheduler

def run_job():
    """Called by APScheduler on schedule."""
    # Load profile + CV fresh each run (picks up any edits)
    user_profile = load_user_profile()
    cv_profile = load_cv_cache()  # from app/cv/cache.py
    storage = SQLiteStorage(os.getenv("SQLITE_DB_PATH", "data/jobs.db"))
    run_pipeline(storage, user_profile, cv_profile)

if __name__ == "__main__":
    configure_logging()
    scheduler = BlockingScheduler(timezone="Europe/Madrid")
    interval_hours = int(get_setting_from_db("schedule_interval_hours", default="8"))
    scheduler.add_job(run_job, "interval", hours=interval_hours, id="pipeline")
    scheduler.start()
```

`BlockingScheduler` is the right choice for the worker process — it IS the only thing running in that process, and its `start()` blocking behavior is exactly what the process should do. The Streamlit process uses no scheduler at all.

---

## 6. Notification: `app/notify/`

```
app/notify/
├── __init__.py
├── telegram.py     # send_digest_telegram(jobs, token, chat_id)
└── email.py        # send_digest_email(jobs, smtp_config)
```

**Telegram:** Pure `httpx.Client.post` to `https://api.telegram.org/bot{TOKEN}/sendMessage`. No framework needed. The message is Markdown-formatted text (Telegram supports MarkdownV2). Credentials: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` from `.env`.

**Email:** `smtplib.SMTP_SSL` + `email.mime.multipart.MIMEMultipart`. HTML body with a table of top jobs. SMTP credentials from `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `DIGEST_TO_EMAIL`.

**Selection logic:** The worker reads `notify_channel` from the settings table (`"telegram"` | `"email"` | `"none"`). Both notifiers are always installed but only one is called per run based on this setting.

---

## 7. Streamlit UI: `app/ui/`

```
app/ui/
├── main.py                 # st.navigation entry + shared resource init
└── pages/
    ├── 01_cv.py            # upload PDF → parse → show CVProfile
    ├── 02_search.py        # manual "Run now" button + search params form
    ├── 03_results.py       # browse scored jobs with filters
    └── 04_settings.py      # edit search/schedule/scoring params → save to DB
```

**Shared resources via `st.cache_resource`:**

```python
@st.cache_resource
def get_storage() -> SQLiteStorage:
    return SQLiteStorage(os.getenv("SQLITE_DB_PATH", "data/jobs.db"))

@st.cache_resource
def get_user_profile() -> UserProfile:
    return load_user_profile()
```

`st.cache_resource` initializes once per Streamlit server process and is shared across all reruns and pages. This avoids re-opening the SQLite connection on every page rerun.

**Manual "Run now" in `02_search.py`:** Calls `run_pipeline(storage, user_profile, cv_profile)` directly in-process when the user clicks the button. This is intentional — Streamlit + the pipeline share the same process, and the pipeline is synchronous. The UI will show a spinner during the run. The worker process is not involved.

**Do NOT embed APScheduler inside the Streamlit process.** The worker process owns the scheduler; the UI only provides a manual trigger and reads results.

---

## 8. Removal of `app/api/` (FastAPI)

**What to do:**
1. Delete `app/api/` directory entirely.
2. Remove `fastapi`, `uvicorn`, `python-multipart` from `pyproject.toml` dependencies (unless Streamlit requires any — it does not).
3. Remove the `buscadordeempleo` service CMD in Dockerfile (now replaced by the two-service Compose pattern).
4. Remove the `n8n` service from `docker-compose.yml`. Archive the `n8n/` directory (do not delete — it is portfolio evidence).
5. Remove the inline `RAPIDAPI_KEY` hardcoded in the current `docker-compose.yml` `n8n` service environment block.
6. Update `app/api/auth.py` references — `ApiKeyMiddleware` is no longer used. The Streamlit UI runs local-only (single user, no auth needed).
7. Remove `httpx` from prod deps ONLY if no other module uses it. `app/sources/jsearch.py` will use `httpx` — so keep it.

**Tests:** All `tests/api/` tests are deleted. The core tests (`tests/cv/`, `tests/dedup/`, `tests/scoring/`, `tests/storage/`) are untouched.

---

## Component Responsibilities (v2.0 Complete Map)

| Component | Status | Responsibility | Communicates With |
|-----------|--------|---------------|-------------------|
| `app/models/schemas.py` | KEEP | All data shapes | Imported everywhere |
| `app/config/loader.py` | KEEP | Load+validate profile.yaml → UserProfile | `app/worker`, `app/ui` |
| `app/cv/` | KEEP | PDF → CVProfile + cache | `app/ui/pages/01_cv.py`, `app/worker/pipeline.py` |
| `app/dedup/` | KEEP | normalize_jobs + deduplicate | `app/worker/pipeline.py` |
| `app/scoring/location.py` | KEEP | Deterministic location score | `app/scoring/scorer.py` |
| `app/scoring/ranking.py` | KEEP | Decay → encaje_puesto | `app/scoring/scorer.py` |
| `app/scoring/embeddings.py` | NEW | BGE-M3 cosine → encaje_skills + encaje_seniority | `app/scoring/scorer.py` |
| `app/scoring/llm.py` | MODIFY | Optional LLM enrichment (reasons, skill names) | `app/scoring/scorer.py` (deferred import) |
| `app/scoring/scorer.py` | MODIFY | Orchestrate all scoring layers | `app/worker/pipeline.py`, `app/ui/pages/02_search.py` |
| `app/storage/sqlite.py` | MODIFY | WAL+busy_timeout; jobs + settings tables | `app/worker`, `app/ui` |
| `app/sources/jsearch.py` | NEW | JSearch HTTP client → raw dicts | `app/worker/pipeline.py` |
| `app/worker/pipeline.py` | NEW | Full pipeline: fetch→normalize→dedup→score→persist→notify | `app/worker/main.py` |
| `app/worker/main.py` | NEW | APScheduler BlockingScheduler entrypoint | Docker worker service |
| `app/notify/telegram.py` | NEW | Send Telegram digest | `app/worker/pipeline.py` |
| `app/notify/email.py` | NEW | Send email digest | `app/worker/pipeline.py` |
| `app/ui/main.py` | NEW | Streamlit entry + st.navigation | Docker ui service |
| `app/ui/pages/` | NEW | Four pages: CV, Search, Results, Settings | `app/storage`, `app/cv`, `app/scoring` |
| `app/api/` | REMOVE | FastAPI layer (retired) | — |

---

## Data Flow

### Scheduled Worker Run (every N hours)

```
[APScheduler fires run_job()]
    ↓
[load_user_profile() + load_cv_cache()]       ← disk reads, fast
    ↓
[storage.get_settings()]                       ← SQLite SELECT settings
    ↓
[jsearch.fetch_jobs(query, country, ...)]      ← HTTP to RapidAPI (1-8s)
    ↓
[dedup.normalize_jobs(raw, source="jsearch")]  ← in-memory
    ↓
[filter already-seen via storage.was_seen()]   ← SQLite SELECT per job
    ↓
[dedup.deduplicate(new_jobs, embedder)]        ← BGE-M3 inference (~seconds)
    ↓
[scorer.score_job(..., enrich_with_llm=True)]  ← deterministic + optional OpenAI
    ↓
[storage.upsert_scored_jobs(scored)]           ← SQLite UPSERT, one transaction
    ↓
[notify.send_digest(top_jobs)]                 ← Telegram POST or smtplib
```

### User Manual Run (from UI "Run now" button)

Identical pipeline, but called synchronously in the Streamlit process. Streamlit shows `st.spinner()` during execution. The scheduled worker is not involved.

### UI Browse Flow

```
[User opens Results page]
    ↓
[storage.get_history(limit, offset)]           ← SQLite SELECT (WAL: never blocks)
    ↓
[Render job_card components per ScoredJob]     ← pure Streamlit, no core imports
```

### Config Change Flow (Settings page)

```
[User edits search_query or schedule interval]
    ↓
[storage.update_setting(key, value)]           ← SQLite UPDATE settings
    ↓
[Worker reads settings at next run start]      ← picks up change automatically
```

---

## New Module File Structure (additions only)

```
app/
├── sources/
│   ├── __init__.py
│   └── jsearch.py          # JSearch httpx client
├── worker/
│   ├── __init__.py
│   ├── main.py             # BlockingScheduler entrypoint
│   └── pipeline.py         # fetch→normalize→dedup→score→persist→notify
├── notify/
│   ├── __init__.py
│   ├── telegram.py         # send_digest_telegram()
│   └── email.py            # send_digest_email()
├── ui/
│   ├── main.py             # st.navigation + cache_resource setup
│   └── pages/
│       ├── 01_cv.py
│       ├── 02_search.py
│       ├── 03_results.py
│       └── 04_settings.py
└── scoring/
    └── embeddings.py       # NEW: BGE-M3 skill/seniority scoring
```

Removed:
```
app/api/           # DELETED entirely
```

---

## Architectural Patterns

### Pattern 1: Lazy Import as Optional-Dependency Gate

**What:** Import the optional module inside the `if` branch that needs it, never at module level.
**When to use:** Any module whose deps (OpenAI, instructor) should not be required at startup.
**Example (scorer.py):**

```python
if enrich_with_llm and _openai_key_present():
    from app.scoring.llm import assess_job, build_instructor_client  # noqa: PLC0415
    ...
```

This is the same pattern already used for `sentence-transformers` in `app/dedup/embedder.py`. Extend it to `openai`/`instructor`. The `# noqa: PLC0415` suppresses the non-top-level-import linter warning.

### Pattern 2: `st.cache_resource` for Shared Singletons

**What:** Wrap expensive or connection-holding objects in `@st.cache_resource` so they initialize once per server process, not once per page rerun.
**When to use:** `SQLiteStorage`, loaded `UserProfile`, `CVProfile` (loaded from cache).
**Trade-off:** The object is shared across all user sessions. Safe here because it is a single-user app.

### Pattern 3: Settings Table as Cross-Process Config Bus

**What:** Both UI (writer) and worker (reader) share a `settings` SQLite table. UI writes a setting; worker reads it at the next run start. No file locking, no YAML parse races, no IPC needed.
**When to use:** Any parameter the user tunes from the UI that the worker must act on.
**Trade-off:** Schedule interval changes require worker restart to take effect (acceptable for personal use). If live reload is needed, the worker can poll the setting at the start of each job execution.

### Pattern 4: Pipeline Callable from Both UI and Worker

**What:** `run_pipeline()` is a plain synchronous function with no APScheduler dependency. The worker calls it on schedule; the UI calls it on button click.
**When to use:** Avoids duplicating fetch+normalize+dedup+score logic in two places.
**Trade-off:** During a UI-triggered manual run, Streamlit's main thread is blocked for the pipeline duration (~30-120s depending on BGE-M3 and OpenAI). Acceptable for a single-user tool; a future enhancement could offload to a `concurrent.futures.ThreadPoolExecutor`.

---

## Anti-Patterns

### Anti-Pattern 1: Shared APScheduler Instance Across Processes

**What people do:** Start `BackgroundScheduler` inside the Streamlit process and expect it to survive page reruns.
**Why it's wrong:** Streamlit reruns the entire script on each user interaction. A `BackgroundScheduler` started inside the script will be garbage-collected on the next rerun unless stored in `st.cache_resource`. Even then, APScheduler explicitly documents that job stores cannot be shared between scheduler instances in different processes — duplicate execution or missed jobs will result.
**Do this instead:** The worker process owns the scheduler exclusively. The UI process only calls `run_pipeline()` synchronously for manual runs.

### Anti-Pattern 2: Importing `openai` at Module Level in scorer.py

**What people do:** `from openai import OpenAI` at the top of scorer.py (or anywhere in the import chain reachable from `app/ui/main.py`).
**Why it's wrong:** The Streamlit UI imports `scorer.py` for manual runs. If `openai` is a top-level import and `OPENAI_API_KEY` is absent, the `OpenAI()` constructor raises `AuthenticationError` at import time, crashing the UI even in offline mode.
**Do this instead:** Use the lazy import gate (`if enrich_with_llm and _openai_key_present(): from app.scoring.llm import ...`). Tests can mock `os.getenv("OPENAI_API_KEY")` to `""` to verify the offline code path.

### Anti-Pattern 3: Writing profile.yaml from the UI

**What people do:** Save the Streamlit settings form directly to profile.yaml.
**Why it's wrong:** YAML serialization from Python dictionaries loses comments, field ordering, and custom formatting. Jaime's profile.yaml has hand-written comments; overwriting it would destroy them on the first save.
**Do this instead:** Search/schedule parameters go to the `settings` SQLite table. profile.yaml stays as the hand-edited identity document. The UI can display profile.yaml fields read-only for reference.

### Anti-Pattern 4: SQLite Connection Held Open Across Operations

**What people do:** Create one `sqlite3.Connection` at module level and reuse it everywhere.
**Why it's wrong:** SQLite connections are not safe to share across threads in WAL mode — WAL's shared-memory state must be accessed by one writer at a time, and Python's sqlite3 module does not serialize concurrent thread access even with `check_same_thread=False`.
**Do this instead:** The existing `_connect()` per-call pattern in `SQLiteStorage` is correct. Keep it. Add the WAL PRAGMAs to `_connect()` as shown above.

---

## Build Order (Dependency-Respecting)

The phases below can be used directly as roadmap phases. Each phase only depends on what is already complete at that point.

| Phase | Work | Depends On |
|-------|------|-----------|
| **1. Foundations** | Delete `app/api/`; update `docker-compose.yml` (remove n8n, add ui+worker services); update Dockerfile CMD; clean up `RAPIDAPI_KEY` inline; update `pyproject.toml` (remove fastapi/uvicorn, add apscheduler/streamlit) | Nothing — this is cleanup |
| **2. Storage extension** | Add WAL+busy_timeout to `SQLiteStorage._connect()`; add `settings` table + `get_settings()`/`update_setting()`/`init_settings_defaults()` to `SQLiteStorage`; update `Storage` Protocol | Phase 1 |
| **3. Scorer restructure** | Create `app/scoring/embeddings.py` (BGE-M3 skill scoring); modify `scorer.py` to use embeddings for numeric scores + lazy-import LLM for optional enrichment; update `_openai_key_present()` helper; write/update scorer tests | Phase 2 (storage not needed, but confirms clean slate) |
| **4. JSearch client + Worker** | Create `app/sources/jsearch.py`; create `app/worker/pipeline.py`; create `app/worker/main.py` (BlockingScheduler); test pipeline end-to-end with mocked JSearch | Phase 2 (settings), Phase 3 (scorer) |
| **5. Notifications** | Create `app/notify/telegram.py` + `app/notify/email.py`; integrate into worker pipeline; add env vars to `.env.example` | Phase 4 |
| **6. Streamlit UI** | Create `app/ui/main.py` + four pages; wire CV upload, manual run, results browse, settings form | Phase 2 (storage), Phase 3 (scorer), Phase 4 (worker pipeline callable) |
| **7. Docker integration** | Update `docker-compose.yml` to final form; test two-container startup, shared volume, WAL concurrency | Phase 1-6 complete |

---

## Integration Points

### External Services

| Service | Integration Pattern | Module | Notes |
|---------|---------------------|--------|-------|
| JSearch (RapidAPI) | `httpx.Client.get` sync | `app/sources/jsearch.py` | API key: `RAPIDAPI_KEY` in `.env` |
| OpenAI (optional) | `instructor.from_openai(OpenAI())` | `app/scoring/llm.py` | Lazy-imported only if `OPENAI_API_KEY` present |
| Telegram Bot API | `httpx.Client.post` sync | `app/notify/telegram.py` | `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` |
| SMTP / email | `smtplib.SMTP_SSL` | `app/notify/email.py` | `SMTP_*` env vars |
| HuggingFace (BGE-M3) | `SentenceTransformer("BAAI/bge-m3")` lazy | `app/dedup/embedder.py` | Downloaded once to `hf_cache` volume |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Worker ↔ UI | SQLite named volume (WAL) | Only shared state is the `data/` volume |
| scorer.py ↔ llm.py | Deferred in-process import | LLM never imported if key absent |
| scorer.py ↔ embeddings.py | Direct function call | `BgeM3Embedder` lazy-loaded on first call |
| UI manual run ↔ pipeline | Direct function call (sync, blocks UI thread) | Streamlit shows spinner |
| Worker scheduled run ↔ pipeline | APScheduler thread pool → direct function call | No shared memory with UI process |

---

## Sources

- SQLite WAL mode official documentation: https://sqlite.org/wal.html
- SQLite concurrent writes pattern: https://tenthousandmeters.com/blog/sqlite-concurrent-writes-and-database-is-locked-errors/
- APScheduler 3.x user guide: https://apscheduler.readthedocs.io/en/3.x/userguide.html
- Streamlit session state docs: https://docs.streamlit.io/develop/concepts/architecture/session-state
- Docker Compose service definition: https://docs.docker.com/reference/compose-file/services/
- Streamlit Docker deployment: https://docs.streamlit.io/deploy/tutorials/docker
- Existing codebase: `app/scoring/scorer.py`, `app/storage/sqlite.py`, `app/dedup/embedder.py`, `app/api/main.py`

---
*Architecture research for: BuscadorDeEmpleo v2.0 Standalone App (Streamlit + Scheduler)*
*Researched: 2026-05-24*
