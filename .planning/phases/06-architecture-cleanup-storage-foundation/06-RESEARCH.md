# Phase 6: Architecture Cleanup & Storage Foundation - Research

**Researched:** 2026-05-25
**Domain:** Python infrastructure migration — FastAPI removal, SQLite WAL, Docker Compose restructure, dependency swap
**Confidence:** HIGH (all critical claims verified via codebase inspection, pip registry, or official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Two Docker services (`ui` + `worker`) from a single image, shared named volumes (`data/`, `hf_cache/`).
- `BlockingScheduler` lives in the worker process — NEVER APScheduler inside Streamlit.
- APScheduler **3.11.x** (not v4 alpha); timezone via `ZoneInfo("Europe/Madrid")` — not pytz.
- `settings` table is the cross-process config bus; `profile.yaml` remains only for hand-edited identity (name, ranking, deal-breakers).
- `RAPIDAPI_KEY` must be `${RAPIDAPI_KEY:-}` interpolated, never literal. **First task of this phase.**
- Persistence stays SQLite-only (Supabase removed from scope 2026-05-23). The `app/storage/protocol.py` Protocol stays so a future network backend remains pluggable.

### Claude's Discretion
All implementation choices are at Claude's discretion — this is a pure infrastructure/migration phase.

### Deferred Ideas (OUT OF SCOPE)
None — infrastructure phase, scope is fully bounded by the ROADMAP success criteria.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MIG-01 | FastAPI retired — `app/api/` deleted; core consumed in-process; `fastapi`/`uvicorn`/`python-multipart` deps removed | Verified: all fastapi imports are confined to `app/api/` — safe to delete entire directory |
| MIG-02 | n8n retired — no `n8n` service in docker-compose; n8n artifacts archived | Verified: n8n service + `n8n_data` volume exist in current compose; docs/N8N-WORKFLOW.md and n8n/workflow.json exist on disk |
| MIG-03 | RAPIDAPI_KEY never inline — compose uses `${RAPIDAPI_KEY:-}`, `.env.example` updated, key rotated | Verified: literal key `dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148` is hardcoded at line 92 of docker-compose.yml |
| MIG-04 | docker-compose has two services (UI Streamlit + worker) from one image, sharing `data` + `hf_cache` volumes | Research documents the exact compose v2 pattern |
| STORE-04 | `settings` table (key-value) with defaults; `get_settings()`/`set_setting()` on storage | Research documents schema, seeding pattern, JSON encoding |
| STORE-06 | SQLite WAL + `busy_timeout=5000` on every connection; concurrent write+read safe | Research documents exact PRAGMA sequence and connection factory pattern |
| DOC-05 | `.env.example` updated for v2.0 (RAPIDAPI_KEY, OPENAI optional, TELEGRAM_*, SMTP_*, schedule) | Research documents all v2.0 env vars; FastAPI/API_KEY vars to remove |
</phase_requirements>

---

## Summary

Phase 6 is a pure infrastructure migration with zero user-facing behavior. It decommissions the FastAPI/n8n layer from v1.0 and lays the plumbing for the v2.0 two-process Streamlit+APScheduler architecture.

The five concrete deliverables are: (1) delete `app/api/` and all tests that depend on it; (2) fix the leaked RAPIDAPI_KEY in docker-compose.yml by rotating it to `${RAPIDAPI_KEY:-}`; (3) swap three `pyproject.toml` deps out and three in; (4) restructure docker-compose.yml from one FastAPI service + one n8n service into two services (`ui` + `worker`) from the same image; (5) extend `SQLiteStorage` with WAL pragma, `busy_timeout`, a `settings` table, and two new methods.

All five deliverables are well-bounded, verifiable, and have no ambiguous design decisions. The most nuanced piece is the SQLite WAL connection factory: pragmas must run on every connection open, not once on init, because the current `_connect()` creates a new connection per call. The settings table schema and the docker-compose restructure follow clear, well-documented patterns.

**Primary recommendation:** Execute tasks in this order to avoid broken states — (1) fix the secret first (safety), (2) delete `app/api/` + API tests, (3) swap pyproject.toml deps, (4) extend SQLiteStorage, (5) rewrite docker-compose.yml, (6) update `.env.example`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Config bus (settings table) | Database / Storage | — | Cross-process; both UI and worker read/write via SQLiteStorage |
| Dependency management | Build / pyproject.toml | Docker image | Removing fastapi family; adding streamlit/apscheduler/python-telegram-bot |
| Secret management | Docker Compose env interpolation | `.env` file | `${VAR:-}` prevents literal values in committed files |
| SQLite concurrency safety | Database / Storage | Connection factory | WAL + busy_timeout applied at connection layer, not at schema layer |
| Container orchestration | Docker Compose | Dockerfile | Two services (`ui` + `worker`) override `command`; same `image:` |
| n8n artifact archival | Repository structure | — | Move docs/N8N-WORKFLOW.md + n8n/ to docs/archive/n8n/ |

---

## Standard Stack

### Core (already in project — keep)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlite3 | stdlib | Storage | Already in use; no new dep needed for WAL/settings |
| pydantic | >=2.13.4 | Schema validation | Existing project standard |
| python-dotenv | >=1.2.2 | `.env` loading | Existing project standard |
| pyyaml | >=6.0.3 | profile.yaml loading | Existing project standard |

### New Dependencies (to add in Phase 6)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| streamlit | >=1.57.0 | UI framework (Phase 10) | Locked v2.0 arch decision; install now so worker process can import without it |
| APScheduler | >=3.11.2,<4.0 | Scheduling (Phase 8) | Locked 3.11.x; BlockingScheduler in worker; add dep now |
| python-telegram-bot | >=22.7 | Telegram notifications (Phase 9) | Phase 9 will use it; add to manifest in Phase 6 |

**Version note on APScheduler:** Latest 3.x is 3.11.2 as of 2026-05-25. [VERIFIED: pip registry]  
**Version note on streamlit:** Latest is 1.57.0 as of 2026-05-25. [VERIFIED: pip registry]  
**Version note on python-telegram-bot:** Latest is 22.7 as of 2026-05-25. [VERIFIED: pip registry]  
**CRITICAL: Pin APScheduler below 4.0** — v4 is a full API rewrite (async-only) incompatible with `BlockingScheduler`. `>=3.11.2,<4.0` pins to the correct series.

### Dependencies to Remove
| Library | Reason |
|---------|--------|
| fastapi >=0.128.0 | `app/api/` deleted; no remaining import |
| uvicorn[standard] >=0.31.1 | FastAPI entrypoint removed |
| python-multipart >=0.0.22 | Only used by FastAPI file upload routes |

**Verification that removal is safe:** `grep -rn "fastapi\|uvicorn\|multipart" app/ --include="*.py"` confirms all matches are in `app/api/` only. [VERIFIED: codebase inspection]

### Installation
```bash
# Remove old deps
uv remove fastapi uvicorn python-multipart

# Add new deps
uv add "streamlit>=1.57.0" "apscheduler>=3.11.2,<4.0" "python-telegram-bot>=22.7"
```

---

## Architecture Patterns

### System Architecture Diagram (v2.0 target after Phase 6)

```
┌──────────────────────────────────────────────────────────────────┐
│  Docker Compose (one image: buscadordeempleo:latest)             │
│                                                                  │
│  ┌────────────────────┐      ┌──────────────────────────────┐   │
│  │  service: ui        │      │  service: worker              │   │
│  │  command: streamlit │      │  command: python worker.py   │   │
│  │  run ui/app.py      │      │                              │   │
│  │  ports: 8501        │      │  APScheduler.BlockingScheduler│   │
│  │                     │      │  (interval from settings)    │   │
│  └────────┬────────────┘      └───────────┬──────────────────┘   │
│           │  reads/writes                 │  reads/writes         │
│           └──────────────┬────────────────┘                      │
│                          ▼                                        │
│              ┌─────────────────────┐                             │
│              │  SQLite (WAL mode)  │                             │
│              │  /app/data/jobs.db  │                             │
│              │  tables: jobs,      │                             │
│              │          settings   │                             │
│              └─────────────────────┘                             │
│                          │                                        │
│              volume: data (named, shared between both services)   │
│              volume: hf_cache (BGE-M3 model cache)               │
└──────────────────────────────────────────────────────────────────┘
```

Data flow: UI reads settings → displays jobs; Worker reads settings at run start → fetches → scores → writes jobs.

### Recommended Project Structure (post-Phase 6)

```
app/
├── config/           # profile.yaml loader (unchanged)
├── cv/               # CV parsing (unchanged)
├── dedup/            # Dedup + embeddings (unchanged)
├── models/           # Pydantic schemas (unchanged)
├── obs/              # Logging/tracing stubs (unchanged)
├── scoring/          # Scoring heuristic (unchanged)
└── storage/
    ├── __init__.py   # get_storage_backend() (unchanged)
    ├── protocol.py   # Storage Protocol — ADD get_settings()/set_setting()
    └── sqlite.py     # SQLiteStorage — ADD WAL pragma, busy_timeout, settings table
# (app/api/ DELETED entirely)

worker.py             # NEW: worker entrypoint (stub only in Phase 6)
ui/                   # NEW: placeholder dir (actual UI in Phase 10)

tests/
├── api/              # DELETED (depends on fastapi)
├── storage/
│   └── test_sqlite.py  # EXTEND: add settings + WAL concurrency tests
├── ...               # all other tests unchanged
```

### Pattern 1: SQLite Connection Factory with WAL + busy_timeout

**What:** Every call to `_connect()` applies PRAGMA journal_mode=WAL and PRAGMA busy_timeout=5000 before returning the connection. This is the correct approach because `_connect()` is called per-operation (not once).

**Why not once in `init_db()`:** WAL mode is a database-level setting that persists across connections once set, BUT `busy_timeout` is a connection-level setting — it resets to 0 on every new connection. Setting it only in `init_db()` leaves all subsequent connections with timeout=0 (immediate SQLITE_BUSY on any lock). [VERIFIED: SQLite documentation + community sources]

**When to use:** Apply in `_connect()` so every connection (whether for read or write) gets both.

```python
# Source: verified pattern from SQLite documentation + docsaid.org/en/blog/sqlite-wal-busy-timeout-for-workers/
def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")    # database-level, idempotent
    conn.execute("PRAGMA busy_timeout=5000;")   # connection-level: MUST be per-connection
    return conn
```

**Verification query:** `conn.execute("PRAGMA journal_mode;").fetchone()[0]` should return `"wal"` after the first write connection sets it. WAL mode is then persistent for the database file.

**Concurrency guarantee in WAL mode:** SQLite WAL allows concurrent readers + one writer without readers blocking the writer or vice versa. The `busy_timeout=5000` makes a second writer wait up to 5 seconds before raising `sqlite3.OperationalError: database is locked`. [VERIFIED: SQLite official docs + multiple sources]

### Pattern 2: settings Table — Key-Value with JSON Values

**What:** A flat `(key TEXT PRIMARY KEY, value TEXT)` table where values are JSON-encoded strings. This allows storing strings, numbers, dicts (scoring weights), and lists (deal-breakers for future UI editing) in one table without schema migration when new keys are added.

**Why key-value, not typed columns:** The settings keys evolve across phases (8 adds notification keys, 10 adds UI-controlled keys). A key-value table with `INSERT OR IGNORE` seeding is schema-free by design. No migration needed to add a new default.

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

**Seeding defaults idempotently:**
```python
# INSERT OR IGNORE: only inserts if key absent — never overwrites user-set values
DEFAULTS = {
    "search_query": '"AI Engineer" OR "ML Engineer"',
    "search_country": "ES",
    "schedule_interval_hours": "6",         # JSON string of int
    "dedup_threshold": "0.85",              # JSON string of float
    "score_weight_puesto": "0.35",
    "score_weight_skills": "0.30",
    "score_weight_ubicacion": "0.20",
    "score_weight_seniority": "0.15",
    "notification_min_score": "70",
    "notification_channel": "none",         # "none" | "telegram" | "email"
}
# All values stored as plain strings (JSON-encoded when needed for complex types)
```

**get_settings() signature:**
```python
def get_settings(self) -> dict[str, str]:
    """Returns all settings as {key: value_str}. Values are JSON strings."""
    with closing(self._connect()) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}
```

**set_setting() signature:**
```python
def set_setting(self, key: str, value: str) -> None:
    """Upsert a single setting. value must be a JSON-serializable string."""
    with closing(self._connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
```

**For scoring weights (dict):** Callers JSON-encode before storing, JSON-decode after retrieving:
```python
import json
storage.set_setting("score_weights", json.dumps({"puesto": 0.35, "skills": 0.30}))
weights = json.loads(storage.get_settings()["score_weights"])
```

The simpler flat approach (one key per weight) avoids the JSON decode step in callers and is preferred for this phase. Each weight is its own key: `score_weight_puesto`, `score_weight_skills`, etc. [ASSUMED: design choice — caller simplicity preferred over compactness]

### Pattern 3: Docker Compose — Two Services, One Image, Shared Volumes

**What:** Both services use `image: buscadordeempleo:latest` (built once from the single Dockerfile) but override `command` to run different entrypoints. Named volumes are declared once in the top-level `volumes:` block and listed under both services.

**Compose v2 syntax (verified):**
```yaml
services:
  ui:
    build: .                            # build once, both services use same image
    image: buscadordeempleo:latest
    command: ["uv", "run", "streamlit", "run", "ui/app.py", "--server.port", "8501"]
    ports:
      - "8501:8501"
    env_file: .env
    environment:
      SQLITE_DB_PATH: /app/data/jobs.db
      HF_HOME: /app/.cache/huggingface
    volumes:
      - data:/app/data
      - hf_cache:/app/.cache/huggingface
    restart: unless-stopped

  worker:
    image: buscadordeempleo:latest      # reuses image built by ui service
    command: ["uv", "run", "python", "worker.py"]
    depends_on: [ui]
    env_file: .env
    environment:
      SQLITE_DB_PATH: /app/data/jobs.db
      HF_HOME: /app/.cache/huggingface
    volumes:
      - data:/app/data
      - hf_cache:/app/.cache/huggingface
    restart: unless-stopped

volumes:
  data:
    driver: local
  hf_cache:
    driver: local
```

**Key point:** Only the `ui` service has `build: .`. The `worker` service uses `image:` alone — Docker Compose builds once and reuses. [VERIFIED: Docker Compose documentation]

**Secret safety:** `RAPIDAPI_KEY` stays in `.env` (gitignored), injected via `env_file: .env`. It never appears as a literal value in docker-compose.yml. The worker service reads it from the environment when calling JSearch (Phase 8).

**Dockerfile command override:** Remove the `CMD ["uv", "run", "uvicorn", "app.api.main:app", ...]` line from the Dockerfile or replace it with a neutral default (e.g., `CMD ["uv", "run", "python", "-c", "print('Use docker compose up')"]`). Both services override `command:` anyway, so the Dockerfile CMD becomes the fallback for standalone `docker run` only.

### Pattern 4: FastAPI Removal — What to Delete vs. What to Keep

**Delete entirely:**
- `app/api/` (entire directory: `main.py`, `auth.py`, `deps.py`, `routes/`)
- `tests/api/` (entire directory: all 38 tests + conftest.py depend on `fastapi.testclient.TestClient`)

**Archive (move, don't delete):**
- `docs/N8N-WORKFLOW.md` → `docs/archive/n8n/N8N-WORKFLOW.md`
- `n8n/workflow.json` → `docs/archive/n8n/workflow.json`

**Keep unchanged:**
- `app/errors.py` — custom exceptions (CVParseError, etc.) are used by core modules, not only by FastAPI handlers
- `app/obs/logging_config.py` — the comment mentions uvicorn but the code is general-purpose structured logging; keep as-is

**Import cleanliness test (to write in Wave 0):**
```python
def test_fastapi_not_importable_after_removal():
    """After removing app/api/, importing app.storage must not pull in fastapi."""
    import sys
    import app.storage  # noqa: F401
    assert "fastapi" not in sys.modules
    assert "uvicorn" not in sys.modules
```

### Anti-Patterns to Avoid

- **Setting busy_timeout only in init_db():** `busy_timeout` is connection-level; it resets to 0 on every new connection. Must be in `_connect()`.
- **Using pytz with APScheduler 3.11:** APScheduler 3.10+ switched to `zoneinfo`. Do not pass `pytz.timezone(...)` — pass `ZoneInfo("Europe/Madrid")` directly. [VERIFIED: APScheduler 3.x changelog]
- **APScheduler inside Streamlit:** Streamlit re-runs the full script on each interaction; a `BlockingScheduler.start()` inside Streamlit would block the UI thread or create multiple scheduler instances. Worker is a separate process. [ASSUMED based on Streamlit execution model, confirmed by locked decision]
- **`INSERT OR REPLACE` for settings upsert:** `INSERT OR REPLACE` deletes and re-inserts, which would reset `rowid` and any audit columns. Use `ON CONFLICT(key) DO UPDATE SET value = excluded.value`.
- **Committing `uv.lock` before `uv sync`:** After editing `pyproject.toml`, run `uv sync` to regenerate `uv.lock`, then commit both together.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process config bus | Custom file watcher / shared dict | SQLite `settings` table + WAL | Already have SQLite; atomic reads; both processes use same storage layer |
| Concurrent write-lock retry | `while True: try: write except: sleep()` | `PRAGMA busy_timeout=5000` | SQLite built-in retry; more reliable, one PRAGMA line |
| Timezone-aware scheduling | Custom cron parser | APScheduler 3.11 + ZoneInfo | Handles DST, misfire, coalesce, restarts |
| Two-process image sharing | Two separate Dockerfiles | One Dockerfile + `command:` override in compose | Single build layer; both processes always in sync |

---

## Runtime State Inventory

This phase includes a rename/cleanup component (removing RAPIDAPI_KEY literal, decommissioning n8n). Explicit audit:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | No data in the `settings` table (it doesn't exist yet) | CREATE TABLE + seed defaults in `init_db()` |
| Live service config | `n8n` Docker service runs an n8n process with internal SQLite at `/home/node/.n8n` (in volume `n8n_data`). Workflows, credentials, and encryption key stored there — NOT in git. | Volume `n8n_data` becomes orphaned; user may `docker volume rm buscadordeempleo_n8n_data` if no longer needed |
| OS-registered state | None — no OS-level task scheduler entries for this project | None |
| Secrets/env vars | `RAPIDAPI_KEY` was a literal in `docker-compose.yml` (never committed to git per gitignore — BUT it was in working tree and leaked in chat). User must rotate the key out-of-band. Code change: replace literal with `${RAPIDAPI_KEY:-}`. | User action: rotate key; code action: replace literal |
| Build artifacts | `uv.lock` contains fastapi/uvicorn/python-multipart resolution. After removing from pyproject.toml, `uv sync` regenerates it. | Run `uv sync` after `pyproject.toml` edit; commit both |

**Key clarification on the RAPIDAPI_KEY leak:** According to REQUIREMENTS.md Out-of-Scope, "Re-escritura del historial git por la RapidAPI key — Innecesaria: el valor nunca se commiteó (solo en working tree) — basta editar + rotar." No git history rewrite needed. [VERIFIED: REQUIREMENTS.md] The task is: (1) edit docker-compose.yml to use `${RAPIDAPI_KEY:-}`, (2) user rotates the key on RapidAPI dashboard.

---

## Common Pitfalls

### Pitfall 1: busy_timeout not applied to subsequent connections
**What goes wrong:** `init_db()` sets `busy_timeout=5000` on its connection. A later `_connect()` call opens a fresh connection with timeout=0. Concurrent worker write arrives; UI read gets `OperationalError: database is locked` immediately.
**Why it happens:** `busy_timeout` is a per-connection setting in SQLite's C API, not persisted in the database file. WAL mode IS persisted in the database file after first use.
**How to avoid:** Apply both pragmas in `_connect()`, not in `init_db()`. The `init_db()` method calls `_connect()` so it gets the pragmas too.
**Warning signs:** Test passes with single-process usage but fails under concurrent thread test.

### Pitfall 2: APScheduler 4 API sneaking in via `uv add apscheduler`
**What goes wrong:** `uv add apscheduler` without a version cap resolves to 4.x (if it becomes stable), which has a completely different API — no `BlockingScheduler`, no `add_job()` with trigger strings, async-only.
**Why it happens:** Latest available version is 3.11.2 now, but v4 may become stable before this project is done.
**How to avoid:** Pin as `apscheduler>=3.11.2,<4.0` in pyproject.toml. [VERIFIED: APScheduler PyPI page lists both 3.x and 4.x]

### Pitfall 3: tests/api/ collection fails after app/api/ deletion
**What goes wrong:** pytest tries to collect `tests/api/conftest.py` which does `from fastapi.testclient import TestClient` — import error before any test runs, breaking the whole suite.
**Why it happens:** pytest collects conftest.py at directory level before running tests; the import fails at collection time.
**How to avoid:** Delete `tests/api/` entirely in the same task as deleting `app/api/`. Do not leave `tests/api/` with broken imports.
**Warning signs:** `pytest --collect-only` shows `ImportError` in collection output.

### Pitfall 4: settings table missing from Protocol breaks type checking
**What goes wrong:** `SQLiteStorage` gets `get_settings()`/`set_setting()` methods but `Storage` Protocol doesn't — downstream code using the Protocol type hint can't call these methods without a cast.
**Why it happens:** Protocol defines the contract; implementors and callers agree on it.
**How to avoid:** Add `get_settings()` and `set_setting()` to `protocol.py` in the same task as extending `sqlite.py`.

### Pitfall 5: Orphaned n8n_data volume in compose
**What goes wrong:** After removing the `n8n` service from docker-compose.yml, `docker compose up` no longer manages `n8n_data`. The volume remains on disk but is invisible to the compose project.
**Why it happens:** Named volumes declared in removed services are not auto-deleted.
**How to avoid:** Remove `n8n_data` from the `volumes:` top-level block too. User can manually `docker volume rm buscadordeempleo_n8n_data` if they want to reclaim space. Document in commit message.
**Warning signs:** `docker volume ls | grep n8n` still shows the volume after `docker compose down`.

### Pitfall 6: worker.py stub missing at Docker build time
**What goes wrong:** `docker-compose.yml` references `command: ["uv", "run", "python", "worker.py"]` but `worker.py` doesn't exist yet — container starts and immediately exits with `ModuleNotFoundError`.
**Why it happens:** Phase 6 adds the dep and compose structure but doesn't implement the worker (that's Phase 8).
**How to avoid:** Create a minimal `worker.py` stub that prints a startup message and sleeps, or raises a clear `NotImplementedError`. The container must stay alive for the volume mount to work.

---

## Code Examples

### SQLiteStorage._connect() with WAL + busy_timeout

```python
# Source: verified pattern — docsaid.org/en/blog/sqlite-wal-busy-timeout-for-workers/
# and sqlite.org/c3ref/busy_timeout.html
def _connect(self) -> sqlite3.Connection:
    """Crea y devuelve una nueva conexión SQLite con WAL + busy_timeout.

    journal_mode=WAL: database-level setting, persists after first set.
        Concurrent UI reads + worker writes without blocking each other.
    busy_timeout=5000: connection-level setting, MUST be set per-connection.
        Waits up to 5 seconds before raising OperationalError on lock contention.
    """
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn
```

### SQLiteStorage.init_db() with settings table

```python
def init_db(self) -> None:
    """Crea tablas si no existen e inserta defaults de settings. Idempotente."""
    Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(self._connect()) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    remote TEXT,
                    url TEXT,
                    source TEXT,
                    score_total INTEGER,
                    recommendation TEXT,
                    score_json TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    seen INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            # Seed defaults — INSERT OR IGNORE: never overwrites user-set values
            defaults = {
                "search_query": '"AI Engineer" OR "ML Engineer"',
                "search_country": "ES",
                "schedule_interval_hours": "6",
                "dedup_threshold": "0.85",
                "score_weight_puesto": "0.35",
                "score_weight_skills": "0.30",
                "score_weight_ubicacion": "0.20",
                "score_weight_seniority": "0.15",
                "notification_min_score": "70",
                "notification_channel": "none",
            }
            conn.executemany(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                list(defaults.items()),
            )
```

### APScheduler 3.11.x BlockingScheduler stub (worker.py)

```python
# Source: apscheduler.readthedocs.io/en/3.x/userguide.html
# VERIFIED: BlockingScheduler + ZoneInfo("Europe/Madrid") is supported in APScheduler 3.11.x
from zoneinfo import ZoneInfo
from apscheduler.schedulers.blocking import BlockingScheduler

def run_pipeline():
    """Stub — implemented in Phase 8."""
    raise NotImplementedError("Worker pipeline not yet implemented (Phase 8)")

if __name__ == "__main__":
    scheduler = BlockingScheduler(
        timezone=ZoneInfo("Europe/Madrid"),
        job_defaults={
            "coalesce": True,          # run once even if missed multiple intervals
            "misfire_grace_time": 3600, # 1-hour grace before skipping a missed run
            "max_instances": 1,
        },
    )
    scheduler.add_job(run_pipeline, "interval", hours=6, id="pipeline")
    scheduler.start()
```

### Concurrent WAL test pattern

```python
# Source: [ASSUMED pattern — derived from Python threading + sqlite3 stdlib]
import threading, time, sqlite3

def test_wal_concurrent_write_read_no_lock(tmp_path):
    """Worker thread writes while main thread reads — no OperationalError."""
    from app.storage.sqlite import SQLiteStorage
    db = SQLiteStorage(str(tmp_path / "wal_test.db"))
    db.init_db()

    errors = []

    def writer():
        for _ in range(50):
            try:
                db.upsert_scored_jobs([_make_scored_job(f"job-{time.time()}")])
            except Exception as e:
                errors.append(e)

    t = threading.Thread(target=writer)
    t.start()
    for _ in range(50):
        try:
            db.get_history(limit=10)
        except Exception as e:
            errors.append(e)
    t.join()

    assert errors == [], f"Concurrent WAL errors: {errors}"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastAPI + uvicorn HTTP service | Core consumed in-process (no HTTP layer) | v2.0 (this phase) | Eliminates network round-trips; simpler deployment |
| n8n for orchestration | APScheduler BlockingScheduler in worker process | v2.0 (this phase) | Self-contained scheduling; no external service |
| Connection-per-call without WAL | Connection-per-call + WAL + busy_timeout | v2.0 (this phase) | Safe concurrent UI read + worker write |
| No settings table (profile.yaml only) | settings table for operational config | v2.0 (this phase) | Cross-process config bus; UI can write, worker reads |
| pyproject.toml has fastapi/uvicorn | pyproject.toml has streamlit/apscheduler | v2.0 (this phase) | Import-clean package; `import app.*` no longer pulls fastapi |

**Deprecated/outdated in this phase:**
- `app/api/`: The entire FastAPI layer. All tests in `tests/api/` depend on it and are removed.
- `CMD ["uv", "run", "uvicorn", ...]` in Dockerfile: replaced by `command:` override in compose.
- `OPENAI_API_KEY` as required var: remains in .env.example but marked optional (SCORE-14 in Phase 7 makes LLM optional). Phase 6 just documents it as optional in `.env.example`.
- `API_KEY` var for FastAPI authentication: removed from `.env.example` entirely.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Flat key-value design for settings (one key per weight) is preferred over a JSON dict value | Architecture Patterns / Pattern 2 | Low — either approach works; planner can choose the JSON-dict variant if callers are simpler that way |
| A2 | `worker.py` stub should sleep/loop to keep container alive rather than raise immediately | Common Pitfalls / Pitfall 6 | Low — if it raises, the container restarts (unless-stopped). A stub that loops is cleaner. |
| A3 | APScheduler BlockingScheduler inside Streamlit is anti-pattern (no direct code to verify) | Anti-Patterns | Low — locked decision in STATE.md; the Streamlit docs confirm script re-run model |

**Claims verified or cited (not assumed):**
- All fastapi imports confined to `app/api/` — verified by grep [VERIFIED: codebase]
- APScheduler latest 3.x is 3.11.2 — [VERIFIED: pip registry]
- Streamlit latest is 1.57.0 — [VERIFIED: pip registry]
- python-telegram-bot latest is 22.7 — [VERIFIED: pip registry]
- busy_timeout is connection-level (not database-level) — [CITED: sqlite.org/c3ref/busy_timeout.html]
- RAPIDAPI_KEY literal is at docker-compose.yml line 92 — [VERIFIED: codebase]
- n8n artifacts: docs/N8N-WORKFLOW.md and n8n/workflow.json on disk — [VERIFIED: codebase]
- All existing fastapi tests are in tests/api/ (38 tests, 969 lines) — [VERIFIED: codebase]
- No RAPIDAPI_KEY ever committed to git — [CITED: REQUIREMENTS.md Out-of-Scope]

---

## Open Questions

1. **worker.py stub port**
   - What we know: Phase 6 needs a `worker.py` so the Docker service doesn't crash. Phase 8 implements the real pipeline.
   - What's unclear: Should the stub import APScheduler and run an empty scheduler (cleaner, proves dep works), or just `import time; time.sleep(1e9)`?
   - Recommendation: Use a minimal `BlockingScheduler` with a no-op job. This also serves as a smoke test that APScheduler installs correctly.

2. **tests/api/ — archive or delete?**
   - What we know: 38 tests, 969 lines. All depend on `fastapi.testclient`. None of the tested behavior exists after Phase 6.
   - What's unclear: Should they be archived to `tests/archive/api/` for reference, or deleted?
   - Recommendation: Delete. The behavior they tested (HTTP endpoints) no longer exists. Keeping broken tests creates confusion. The git history preserves them.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | uv/pyproject.toml | ✓ | 3.13.x (via uv image) | — |
| uv | Dep management | ✓ | Present in Dockerfile base image | pip |
| Docker / docker compose | Two-service setup | ✓ | Running (docker-compose.yml works) | — |
| sqlite3 | WAL + settings | ✓ | stdlib (no install) | — |
| APScheduler 3.11.x | Worker dep | ✗ (not yet installed) | — | None needed — just `uv add` |
| streamlit | UI dep | ✗ (not yet installed) | — | None needed — just `uv add` |
| python-telegram-bot | Notif dep | ✗ (not yet installed) | — | None needed — just `uv add` |

**Missing dependencies with no fallback:** None — the three missing deps are the whole point of this phase's `uv add` task.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/storage/ -q` |
| Full suite command | `uv run pytest -q` (minus tests/api/ which is deleted) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MIG-01 | `import app.storage` does not load fastapi/uvicorn | unit | `uv run pytest tests/storage/test_import_cleanliness.py -x` | ❌ Wave 0 |
| MIG-02 | `docker compose config` shows no `n8n` service | smoke (manual) | `docker compose config | grep n8n` returns empty | — manual |
| MIG-03 | docker-compose.yml contains no literal RAPIDAPI_KEY | unit | `uv run pytest tests/test_no_secrets.py -x` | ❌ Wave 0 |
| MIG-04 | compose has `ui` + `worker` services, same image, shared volumes | smoke (manual) | `docker compose config` | — manual |
| STORE-04 | `storage.get_settings()` returns all default keys | unit | `uv run pytest tests/storage/test_sqlite.py::test_get_settings_defaults -x` | ❌ Wave 0 |
| STORE-04 | `set_setting()` updates a key; `get_settings()` reflects change | unit | `uv run pytest tests/storage/test_sqlite.py::test_set_setting_roundtrip -x` | ❌ Wave 0 |
| STORE-06 | Concurrent thread write + main thread read: no OperationalError | unit | `uv run pytest tests/storage/test_sqlite.py::test_wal_concurrent_write_read_no_lock -x` | ❌ Wave 0 |
| STORE-06 | `PRAGMA journal_mode` returns `wal` after init | unit | `uv run pytest tests/storage/test_sqlite.py::test_wal_mode_active -x` | ❌ Wave 0 |
| DOC-05 | `.env.example` contains RAPIDAPI_KEY and no API_KEY | grep / unit | `grep RAPIDAPI_KEY .env.example && ! grep "^API_KEY=" .env.example` | — manual |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/storage/ -q`
- **Per wave merge:** `uv run pytest -q` (full suite, excluding deleted tests/api/)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/storage/test_sqlite.py` — extend with: `test_get_settings_defaults`, `test_set_setting_roundtrip`, `test_wal_mode_active`, `test_wal_concurrent_write_read_no_lock`
- [ ] `tests/test_import_cleanliness.py` — `test_fastapi_not_importable_after_removal`
- [ ] `tests/test_no_secrets.py` — `test_docker_compose_no_literal_rapidapi_key`

*(Existing `tests/storage/test_sqlite.py` has 10 passing tests; new tests extend it. Other test dirs are unaffected by this phase.)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | FastAPI auth layer being removed; no auth in standalone app (single user) |
| V3 Session Management | No | No sessions in worker or CLI tool |
| V4 Access Control | No | Single-user tool, no RBAC |
| V5 Input Validation | Partial | Settings values validated as strings; JSON parse caller validates types |
| V6 Cryptography | No | No new crypto operations in this phase |
| V7 Error Handling | Yes | Worker entrypoint should not leak stack traces to stdout logs in prod |
| V14 Configuration | Yes | Secrets via env vars only (`${RAPIDAPI_KEY:-}`), never literals |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Literal secret in committed file | Information Disclosure | `${VAR:-}` interpolation; never hardcode |
| SQL injection in settings key/value | Tampering | Parameterized queries only (`?` placeholders) |
| settings table poisoning (malformed value) | Tampering | Caller validates types after JSON parse; storage layer treats values as opaque strings |

---

## Sources

### Primary (HIGH confidence)
- Codebase grep: `app/api/` imports — confirmed isolation of fastapi to API layer
- Codebase read: `app/storage/sqlite.py`, `app/storage/protocol.py`, `docker-compose.yml`, `pyproject.toml`, `Dockerfile` — all read verbatim
- pip registry: APScheduler 3.11.2, streamlit 1.57.0, python-telegram-bot 22.7 — verified current versions

### Secondary (MEDIUM confidence)
- [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — BlockingScheduler, job_defaults, coalesce, misfire_grace_time
- [APScheduler 3.x BlockingScheduler API](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/blocking.html) — constructor, start(), shutdown()
- [SQLite WAL + busy_timeout Python pattern](https://docsaid.org/en/blog/sqlite-wal-busy-timeout-for-workers/) — connection factory pattern
- [Docker Compose volumes docs](https://docs.docker.com/reference/compose-file/volumes/) — shared named volumes between services
- [Docker Compose merge/override](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) — command override pattern

### Tertiary (LOW confidence)
- None — all critical claims have PRIMARY or SECONDARY sourcing.

---

## Metadata

**Confidence breakdown:**
- Standard stack (versions): HIGH — verified via pip registry
- FastAPI removal safety: HIGH — verified by grep that no imports exist outside `app/api/`
- SQLite WAL + busy_timeout pattern: HIGH — verified against SQLite official docs + multiple sources
- settings table design: HIGH for schema; MEDIUM for key naming (design choice)
- Docker Compose two-service pattern: HIGH — verified against official Docker docs
- APScheduler 3.11.x + ZoneInfo: MEDIUM — docs confirmed ZoneInfo support in 3.10+; not locally executable

**Research date:** 2026-05-25
**Valid until:** 2026-06-25 (stable infra domain; dep versions valid ~30 days)
