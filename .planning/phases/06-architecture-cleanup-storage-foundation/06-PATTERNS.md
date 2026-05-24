# Phase 6: Architecture Cleanup & Storage Foundation - Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 9 (2 modify, 3 modify infra, 2 delete, 1 create, 4 create tests)
**Analogs found:** 8 / 9 (worker.py stub has partial analog only)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/storage/sqlite.py` (MODIFY) | storage | CRUD | itself (existing file) | exact — extend in place |
| `app/storage/protocol.py` (MODIFY) | protocol | CRUD | itself (existing file) | exact — extend in place |
| `pyproject.toml` (MODIFY) | config | — | itself (existing file) | exact — dep swap |
| `docker-compose.yml` (MODIFY) | config | — | itself (existing file, current `buscadordeempleo` service block) | exact — restructure |
| `Dockerfile` (MODIFY) | config | — | itself (existing CMD line) | exact — one-line change |
| `.env.example` (MODIFY) | config | — | itself (existing file) | exact — update |
| `app/api/` (DELETE) | — | — | — | — |
| `tests/api/` (DELETE) | — | — | — | — |
| `worker.py` (CREATE) | entrypoint | event-driven | `app/storage/__init__.py` (deferred-import stub pattern) | partial — different role, same stub-with-clear-entrypoint shape |
| `tests/storage/test_sqlite.py` (EXTEND) | test | CRUD | itself (existing 10 tests) | exact — append new test functions |
| `tests/test_import_cleanliness.py` (CREATE) | test | — | `tests/storage/test_sqlite.py` (test file conventions) | role-match |
| `tests/test_no_secrets.py` (CREATE) | test | — | `tests/storage/test_sqlite.py` (test file conventions) | role-match |

---

## Pattern Assignments

### `app/storage/sqlite.py` (MODIFY — add WAL pragma, busy_timeout, settings table)

**Analog:** itself — `app/storage/sqlite.py` (read in full above)

**Existing `_connect()` to replace** (lines 44–53):
```python
def _connect(self) -> sqlite3.Connection:
    """Crea y devuelve una nueva conexión SQLite.

    check_same_thread=False: necesario porque FastAPI corre endpoints sync
    en un threadpool (cada request puede llegar desde un hilo distinto).
    Conexión-por-llamada es thread-safe a esta escala.
    """
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

**Replacement `_connect()` — WAL + busy_timeout pattern:**
```python
def _connect(self) -> sqlite3.Connection:
    """Crea y devuelve una nueva conexión SQLite con WAL + busy_timeout.

    journal_mode=WAL: database-level setting; persiste en el fichero tras la
        primera vez. Permite lecturas concurrentes mientras hay un escritor.
    busy_timeout=5000: connection-level setting — se resetea a 0 en cada nueva
        conexión. DEBE aplicarse aquí, no solo en init_db().
        Espera hasta 5 segundos antes de lanzar OperationalError en lock contention.
    """
    conn = sqlite3.connect(self._db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn
```

**Existing `init_db()` structure to extend** (lines 55–77) — the `with closing(self._connect()) as conn: with conn:` transaction pattern is the project-standard idiom. The settings table and seeding go inside the same `with conn:` block as the existing `CREATE TABLE IF NOT EXISTS jobs`:
```python
def init_db(self) -> None:
    """Crea la tabla jobs si no existe. Idempotente."""
    Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
    with closing(self._connect()) as conn:
        with conn:  # commit/rollback automático
            conn.execute("""CREATE TABLE IF NOT EXISTS jobs (...)""")
    logger.debug("SQLiteStorage.init_db: tabla jobs lista en %s", self._db_path)
```

**New settings table + seeding to add inside `init_db()`'s `with conn:` block:**
```python
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            _SETTING_DEFAULTS = {
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
                list(_SETTING_DEFAULTS.items()),
            )
```

**New `get_settings()` method — mirrors `was_seen()` read pattern** (lines 121–127):
```python
def get_settings(self) -> dict[str, str]:
    """Devuelve todas las settings como {key: value_str}. Valores son strings."""
    with closing(self._connect()) as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}
```

**New `set_setting()` method — mirrors `upsert_scored_jobs()` write pattern** (lines 79–119, the `with closing(self._connect()) as conn: with conn:` upsert structure):
```python
def set_setting(self, key: str, value: str) -> None:
    """Upsert de una setting. value debe ser un string (JSON-encoded si complejo)."""
    with closing(self._connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
```

**Docstring update for class-level comment** (lines 1–15) — update the "FastAPI corre endpoints sync en un threadpool" sentence in the module docstring and the `_connect()` docstring. The new rationale is two-process concurrency (UI + worker), not FastAPI threadpool.

---

### `app/storage/protocol.py` (MODIFY — add settings methods to Protocol)

**Analog:** itself — `app/storage/protocol.py` (read in full above)

**Existing method signature style** (lines 29–35) — each method is a one-liner with `...` body, matching PEP 544 Protocol style:
```python
    def init_db(self) -> None: ...

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None: ...

    def was_seen(self, job_id: str) -> bool: ...

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
```

**New methods to append in the same style:**
```python
    def get_settings(self) -> dict[str, str]: ...

    def set_setting(self, key: str, value: str) -> None: ...
```

Place after `get_history`. No new imports needed — signatures use only built-in types.

---

### `pyproject.toml` (MODIFY — dependency swap)

**Analog:** itself — current `dependencies` block (lines 5–17)

**Current block to modify:**
```toml
dependencies = [
    "fastapi>=0.128.0",
    "httpx>=0.28.1",
    "instructor>=1.15.1",
    "openai>=2.38.0",
    "pydantic>=2.13.4",
    "pymupdf>=1.27.2.3",
    "python-dotenv>=1.2.2",
    "python-multipart>=0.0.22",
    "pyyaml>=6.0.3",
    "sentence-transformers>=5.5.1",
    "uvicorn[standard]>=0.31.1",
]
```

**Remove:** `fastapi>=0.128.0`, `uvicorn[standard]>=0.31.1`, `python-multipart>=0.0.22`

**Add:** `streamlit>=1.57.0`, `apscheduler>=3.11.2,<4.0`, `python-telegram-bot>=22.7`

**Post-edit command:** `uv sync` (regenerates `uv.lock`; commit both `pyproject.toml` + `uv.lock` together).

---

### `docker-compose.yml` (MODIFY — two services from one image, fix leaked secret)

**Analog:** itself — current `buscadordeempleo` service block (lines 17–71) is the structural template for both new services.

**Existing service block conventions to copy:**
- `build: .` + `image: buscadordeempleo:latest` — keep on the `ui` service only; `worker` uses `image:` alone
- `env_file: - .env` — keep on both services
- `environment:` block with `SQLITE_DB_PATH: /app/data/jobs.db` and `HF_HOME: /app/.cache/huggingface` — copy to both
- Named volume mounts `data:/app/data` and `hf_cache:/app/.cache/huggingface` — copy to both
- `restart: unless-stopped` — keep on both
- Top-level `volumes:` block with `driver: local` — keep `data` and `hf_cache`; remove `n8n_data`

**Critical change on line 92** — replace literal:
```yaml
      RAPIDAPI_KEY: dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148
```
with env interpolation (not in the compose at all — it lives in `.env`, injected via `env_file`). Remove the `RAPIDAPI_KEY:` line from the `environment:` block entirely; `env_file: .env` already makes it available to the container at runtime.

**Remove entirely:** the `n8n:` service block (lines 74–99) and `n8n_data:` volume (line 113).

**New `ui` service command:**
```yaml
    command: ["uv", "run", "streamlit", "run", "ui/app.py", "--server.port", "8501"]
    ports:
      - "8501:8501"
```

**New `worker` service additions:**
```yaml
    command: ["uv", "run", "python", "worker.py"]
    depends_on: [ui]
```

**Remove:** `healthcheck:` block (lines 59–70) and `ports: - "8000:8000"` from the service that becomes `ui`.

---

### `Dockerfile` (MODIFY — one-line CMD change)

**Analog:** itself — last line (line 44)

**Current CMD to replace:**
```dockerfile
CMD ["uv", "run", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**New CMD (neutral fallback — both services override via compose `command:`):**
```dockerfile
CMD ["uv", "run", "python", "-c", "print('Use: docker compose up')"]
```

Also update line 22 (`COPY app/ ./app/`) — no change needed to that line.  
Remove line 29 (`EXPOSE 8000`) or replace with `EXPOSE 8501` — since compose overrides the port anyway, deleting is cleaner.

---

### `.env.example` (MODIFY — v2.0 vars, remove FastAPI vars)

**Analog:** itself — current file (4 active lines + 6 comment-only lines)

**Remove:** the `API_KEY=` block (lines 17–22) — FastAPI auth key; no longer exists.

**Add:** documented v2.0 variables. Follow the existing comment style: `# Description. Optional note.` above each var, blank line between groups.

**Full v2.0 structure to produce:**
```
# LLM para scoring y parseo de CV. Opcional — scoring se desactiva si ausente.
# OPENAI_API_KEY=sk-proj-...

# Modelos opcionales (defaults en código):
# OPENAI_MODEL_CV=gpt-4o-mini
# OPENAI_MODEL_SCORING=gpt-4o

# Persistencia SQLite local. Ruta opcional:
# SQLITE_DB_PATH=data/jobs.db

# API de empleo (JSearch via RapidAPI). Necesaria para el worker.
# Rotar la clave anterior en https://rapidapi.com — la clave anterior estaba expuesta.
# RAPIDAPI_KEY=

# Notificaciones Telegram (opcional, Fase 9):
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_CHAT_ID=

# Notificaciones email SMTP (opcional, Fase 9):
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=
# SMTP_PASSWORD=

# Observabilidad Langfuse (opcional):
# LANGFUSE_PUBLIC_KEY=pk-lf-...
# LANGFUSE_SECRET_KEY=sk-lf-...
```

---

### `worker.py` (CREATE — stub entrypoint)

**Analog (partial):** `app/storage/__init__.py` (lines 16–33) — the deferred-import pattern and the clear entrypoint shape. Also the research RESEARCH.md lines 476–496 provide the exact APScheduler stub.

**No existing file** in the repo uses APScheduler. Use the pattern from RESEARCH.md directly.

**Project conventions to match:**
- `from __future__ import annotations` at top (every project file uses this)
- Module-level docstring (every project file has one)
- Logging via `logging.getLogger(__name__)` (present in `sqlite.py`, `__init__.py`, etc.)
- Type hints on all functions

**Stub pattern:**
```python
"""Worker BuscadorDeEmpleo — proceso de fondo con APScheduler.

Punto de entrada del contenedor `worker` en docker-compose.yml.
En Fase 8 se implementará el pipeline completo; esta versión es un stub
que arranca el scheduler vacío para que el contenedor permanezca activo.

NO instanciar APScheduler dentro de Streamlit — este módulo corre en un
proceso separado.
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Pipeline principal — implementado en Fase 8."""
    logger.info("Pipeline stub: no implementado aún (Fase 8)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Worker arrancando (stub — Fase 8 implementa el pipeline)")
    scheduler = BlockingScheduler(
        timezone=ZoneInfo("Europe/Madrid"),
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": 3600,
            "max_instances": 1,
        },
    )
    scheduler.add_job(run_pipeline, "interval", hours=6, id="pipeline")
    scheduler.start()
```

---

### `tests/storage/test_sqlite.py` (EXTEND — append 4 new test functions)

**Analog:** itself — existing 10 tests (read in full above). New tests follow identical conventions.

**Conventions to mirror:**
- Module docstring opening: `"""Tests unitarios de ... — REQ-ID, REQ-ID."""`
- `_make_scored_job()` helper already defined — reuse it in the WAL concurrency test
- `db` fixture already defined — use it for settings tests (it calls `init_db()` which seeds defaults)
- Section header comment style: `# ── Description ──────...─`
- Test naming: `test_<what>_<expected_outcome>` in Spanish snake_case
- Assertion messages in Spanish strings (consistent with existing tests lines 116–120)

**New section to append:**
```python
# ──────────────────────────────────────────────────────────────────────────────
# STORE-04: settings table — defaults, get, set
# ──────────────────────────────────────────────────────────────────────────────


def test_get_settings_defaults(db: SQLiteStorage) -> None:
    """get_settings() devuelve todas las claves por defecto tras init_db(). (STORE-04)"""
    settings = db.get_settings()

    assert "search_query" in settings
    assert "schedule_interval_hours" in settings
    assert settings["score_weight_puesto"] == "0.35"
    assert settings["notification_channel"] == "none"


def test_set_setting_roundtrip(db: SQLiteStorage) -> None:
    """set_setting() actualiza el valor; get_settings() devuelve el nuevo. (STORE-04)"""
    db.set_setting("schedule_interval_hours", "12")

    settings = db.get_settings()

    assert settings["schedule_interval_hours"] == "12"


# ──────────────────────────────────────────────────────────────────────────────
# STORE-06: WAL mode + busy_timeout
# ──────────────────────────────────────────────────────────────────────────────


def test_wal_mode_activo(db: SQLiteStorage) -> None:
    """PRAGMA journal_mode devuelve 'wal' tras init_db(). (STORE-06)"""
    import sqlite3

    conn = sqlite3.connect(db._db_path)
    mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
    conn.close()

    assert mode == "wal", f"Se esperaba 'wal', se obtuvo '{mode}'"


def test_wal_concurrent_write_read_no_lock(tmp_path) -> None:
    """Escritura concurrente (hilo worker) + lectura (hilo UI): sin OperationalError. (STORE-06)"""
    import threading
    import time

    db = SQLiteStorage(str(tmp_path / "wal_test.db"))
    db.init_db()
    errors: list[Exception] = []

    def writer() -> None:
        for i in range(50):
            try:
                db.upsert_scored_jobs([_make_scored_job(f"job-{time.time()}-{i}")])
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    t = threading.Thread(target=writer)
    t.start()
    for _ in range(50):
        try:
            db.get_history(limit=10)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    t.join()

    assert errors == [], f"Errores concurrentes WAL: {errors}"
```

---

### `tests/test_import_cleanliness.py` (CREATE)

**Analog:** `tests/storage/test_sqlite.py` — test file conventions (docstring, imports, test naming).

**No fixture needed** — pure stdlib `sys.modules` check.

**Project conventions to match:**
- `from __future__ import annotations`
- Module docstring with requirement IDs (MIG-01)
- No fixture — standalone test function

```python
"""Tests de limpieza de imports — MIG-01.

Verifica que eliminar app/api/ no deja rastros de fastapi/uvicorn
en el grafo de imports del paquete app.storage.
"""
from __future__ import annotations

import sys


def test_fastapi_not_importable_after_removal() -> None:
    """Importar app.storage no arrastra fastapi ni uvicorn. (MIG-01)

    Si algún módulo de app.storage importara fastapi transitivamente,
    este test fallaría — señalando un import olvidado al borrar app/api/.
    """
    import app.storage  # noqa: F401

    assert "fastapi" not in sys.modules, (
        "fastapi está en sys.modules tras importar app.storage — "
        "comprobar imports en app/storage/ o app/__init__.py"
    )
    assert "uvicorn" not in sys.modules, (
        "uvicorn está en sys.modules tras importar app.storage"
    )
```

---

### `tests/test_no_secrets.py` (CREATE)

**Analog:** `tests/storage/test_sqlite.py` — test file conventions. The test reads a file from disk — similar in spirit to `test_get_history_omite_fila_corrupta` which opens a raw sqlite3 connection to inject data.

**Project conventions to match:**
- `from __future__ import annotations`
- Module docstring with requirement IDs (MIG-03)
- Use `pathlib.Path` for file access (project standard)

```python
"""Tests de secretos en ficheros de configuración — MIG-03.

Verifica que docker-compose.yml no contiene la RAPIDAPI_KEY literal
(la clave fue expuesta en el working tree; este test previene regresiones).
"""
from __future__ import annotations

from pathlib import Path

# Ruta resuelta desde __file__ para funcionar independientemente del CWD
_REPO_ROOT = Path(__file__).parent.parent


def test_docker_compose_no_literal_rapidapi_key() -> None:
    """docker-compose.yml no contiene la RAPIDAPI_KEY literal. (MIG-03)

    La clave expuesta anteriormente era:
        dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148
    Este test falla si esa cadena (o cualquier otra clave inline) aparece en el fichero.
    """
    compose_path = _REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml no encontrado en {_REPO_ROOT}"

    content = compose_path.read_text(encoding="utf-8")

    # La clave expuesta no debe aparecer nunca más
    assert "dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148" not in content, (
        "RAPIDAPI_KEY literal encontrada en docker-compose.yml — usar ${RAPIDAPI_KEY:-}"
    )
    # Verificación estructural: el fichero debe usar interpolación para RAPIDAPI_KEY
    # (si la variable aparece, debe ser como ${RAPIDAPI_KEY...})
    assert "RAPIDAPI_KEY: dfae" not in content
```

---

## Shared Patterns

### Connection + transaction idiom
**Source:** `app/storage/sqlite.py` lines 86–88 and 122–127
**Apply to:** all new `get_settings()` and `set_setting()` methods
```python
# Read pattern
with closing(self._connect()) as conn:
    rows = conn.execute("SELECT ...").fetchall()

# Write pattern
with closing(self._connect()) as conn:
    with conn:  # commit on success, rollback on exception
        conn.execute("INSERT OR ...", (params,))
```

### Logging
**Source:** `app/storage/sqlite.py` line 26 + lines 119, 77
**Apply to:** `worker.py` and updated `sqlite.py` docstring
```python
logger = logging.getLogger(__name__)
# ...
logger.info("upsert_scored_jobs: %d ofertas persistidas en %s", len(scored), self._db_path)
logger.debug("SQLiteStorage.init_db: tabla jobs lista en %s", self._db_path)
```

### `from __future__ import annotations`
**Source:** every project file
**Apply to:** all new/modified Python files in this phase

### Test fixture for tmp_path storage
**Source:** `tests/storage/test_sqlite.py` lines 65–70
**Apply to:** new WAL test that creates its own `SQLiteStorage` instance (uses `tmp_path` directly rather than the `db` fixture, because it needs a fresh DB to control threading)
```python
@pytest.fixture
def db(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    return storage
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `worker.py` (full implementation) | entrypoint | event-driven | No APScheduler usage exists in the codebase; stub pattern derived from RESEARCH.md and APScheduler 3.x docs |

---

## Deletion Checklist (no analog needed — pure removal)

| Path | Type | Reason |
|---|---|---|
| `app/api/` | directory | FastAPI layer decommissioned; all imports verified confined here |
| `tests/api/` | directory | All 8 test files + conftest.py import `fastapi.testclient` — break at collection time after `app/api/` is gone |
| `n8n/` | directory | Archive to `docs/archive/n8n/` (move, not delete) |
| `docs/N8N-WORKFLOW.md` | file | Archive to `docs/archive/n8n/N8N-WORKFLOW.md` (move, not delete) |

---

## Metadata

**Analog search scope:** `app/storage/`, `tests/storage/`, `tests/`, `docker-compose.yml`, `pyproject.toml`, `Dockerfile`, `.env.example`, `tests/api/conftest.py`
**Files read:** 10
**Pattern extraction date:** 2026-05-25
