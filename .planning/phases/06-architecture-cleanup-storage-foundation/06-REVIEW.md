---
phase: 06-architecture-cleanup-storage-foundation
reviewed: 2026-05-25T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - app/storage/sqlite.py
  - app/storage/protocol.py
  - worker.py
  - docker-compose.yml
  - Dockerfile
  - .env.example
  - pyproject.toml
findings:
  critical: 0
  warning: 4
  high: 0
  medium: 3
  low: 2
  total: 6
status: fixed_with_deferrals
fixed:
  - WR-01  # ui/app.py stub created; compose no longer crash-loops
  - IN-01  # depends_on: ui removed from worker service
  - WR-02  # worker reads schedule_interval_hours from settings DB
  - WR-03  # set_setting() docstring corrected to describe upsert semantics
deferred:
  - WR-04  # DB weights bypass PesosScoring.check_sum — deferred to Phase 7 (scoring refactor, where weights are consumed)
  - IN-02  # score_json NOT NULL constraint — deferred (info-level; invariant enforced by upsert path today)
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-25T00:00:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 6 delivers four coherent changes: WAL + busy_timeout on every `_connect()`, a new `settings` table with seeded defaults, the `get_settings()`/`set_setting()` methods (and their Protocol declarations), a `BlockingScheduler` stub in `worker.py`, and a two-service docker-compose restructure. The security posture is clean — no hardcoded credentials anywhere, `.env` is excluded via `.dockerignore`, and all SQL uses parameterized queries throughout.

The WAL pragma placement in `_connect()` is correct and the busy_timeout argument applies on every connection as intended. Settings seeding is idempotent (INSERT OR IGNORE). The Protocol signatures match the implementation exactly.

Four issues are found. The most operationally significant is that `docker compose up` will immediately crash the `ui` service because `ui/app.py` does not yet exist — this is partially scaffolding-by-design for Phase 10, but as delivered it produces a broken compose stack. The second important issue is a configuration divergence: the worker hardcodes `hours=6` while the DB stores a `schedule_interval_hours` setting that exists precisely to make this configurable. The remaining findings are a misleading docstring sentence and a missing score-weight sum guard when settings are loaded from the DB.

---

## Warnings

### WR-01: `docker compose up` crashes `ui` service — `ui/app.py` does not exist

**File:** `docker-compose.yml:21` / `Dockerfile:36-39`
**Issue:** The `ui` service command is `["uv", "run", "streamlit", "run", "ui/app.py", "--server.port", "8501"]`. The Dockerfile creates an empty `ui/` directory (`RUN mkdir -p ui`) but does not copy `ui/app.py` (it doesn't exist yet — only `ui/.gitkeep` is committed). Running `docker compose up` or `docker compose up --build` will start the `ui` container and immediately exit with a file-not-found error. Because `restart: unless-stopped` is set, it will restart in a tight loop. The `worker` service depends on `ui` starting (not healthy), so it starts regardless, but the overall compose stack is broken.

This is documented as "Phase 10" work in the Dockerfile comment, but there is no placeholder that keeps the service alive, nor a README warning. Anyone who runs `docker compose up` now will get a crash loop with no obvious explanation.

**Fix:** Add a stub `ui/app.py` that keeps the container alive with a clear message:
```python
# ui/app.py — placeholder until Phase 10
import streamlit as st
st.title("BuscadorDeEmpleo")
st.info("UI en construcción — Fase 10")
```
Alternatively, comment out or gate the `ui` service command in `docker-compose.yml` with a note, or add a `healthcheck` so that the `restart: unless-stopped` behavior is documented as expected.

---

### WR-02: Worker hardcodes `hours=6` — diverges from `schedule_interval_hours` DB setting

**File:** `worker.py:36`
**Issue:** The scheduler is configured with a fixed `hours=6` interval:
```python
scheduler.add_job(run_pipeline, "interval", hours=6, id="pipeline")
```
The `settings` table (seeded in `init_db()`) stores `"schedule_interval_hours": "6"` specifically to make this value runtime-configurable without a code change or container rebuild. As written, changing `schedule_interval_hours` in the UI (via `set_setting()`) will have no effect on the worker — the DB setting and the actual interval are silently diverged from the first run. When Phase 8 implements the full pipeline, this will either be caught and fixed, or (worse) the setting will appear editable in the UI while doing nothing.

**Fix:** Read the setting from the DB before starting the scheduler:
```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from app.storage import get_storage_backend
    storage = get_storage_backend()
    settings = storage.get_settings()
    interval_hours = int(settings.get("schedule_interval_hours", "6"))
    scheduler = BlockingScheduler(
        timezone=ZoneInfo("Europe/Madrid"),
        job_defaults={"coalesce": True, "misfire_grace_time": 3600, "max_instances": 1},
    )
    scheduler.add_job(run_pipeline, "interval", hours=interval_hours, id="pipeline")
    scheduler.start()
```
This ensures the DB setting is the authoritative source from day one. Even as a stub, reading it here validates that the setting round-trips correctly.

---

### WR-03: `set_setting()` docstring first sentence contradicts the implementation

**File:** `app/storage/sqlite.py:205`
**Issue:** The docstring opens with:
```
INSERT OR IGNORE semántica: INSERT OR IGNORE solo para defaults (init_db).
```
Read in isolation this sentence says `set_setting()` uses INSERT OR IGNORE semantics — but the function actually uses `ON CONFLICT(key) DO UPDATE SET value = excluded.value`, which overwrites existing values. The intended meaning (only `init_db` uses INSERT OR IGNORE; `set_setting` uses ON CONFLICT DO UPDATE) is backwards from what the sentence says. Any future contributor reading this docstring will be confused about the function's actual contract.

**Fix:** Rewrite to:
```python
"""Upsert de una setting. value debe ser un string (JSON-encoded si complejo).

Usa ON CONFLICT(key) DO UPDATE para sobreescribir el valor existente.
A diferencia de init_db() que usa INSERT OR IGNORE (no destruye valores ya
configurados por el usuario), set_setting() siempre actualiza.
Nunca borra otras claves — upsert atómico solo del par (key, value).
"""
```

---

### WR-04: `get_settings()` returns raw strings for DB-sourced score weights — no sum validation before use

**File:** `app/storage/sqlite.py:192-200`
**Issue:** `get_settings()` returns `{"score_weight_puesto": "0.35", ...}` as plain strings. The `PesosScoring` model in `app/models/schemas.py` validates that weights sum to 1.0 when loaded from `profile.yaml`, but there is no equivalent validation when weights are read from the DB. A user who edits `score_weight_puesto` to `"0.50"` via the UI without adjusting the others will silently produce weights that sum to 1.15. The pipeline in Phase 8 will use whatever floats it gets, and scoring will be subtly wrong with no error raised.

This is a design gap rather than a bug in the current code (the pipeline is a stub), but the DB settings are the runtime-configurable override path and the validation gap should be addressed before Phase 8 is wired up.

**Fix:** The caller that assembles `PesosScoring` from DB settings should construct a `PesosScoring` instance (which triggers `check_sum`) rather than reading weights as raw floats. For defensive depth, add a `validate_settings_weights()` helper:
```python
def _build_pesos_from_settings(settings: dict[str, str]) -> PesosScoring:
    """Construye PesosScoring desde settings del DB. Lanza ValueError si no suman 1.0."""
    return PesosScoring(
        puesto=float(settings["score_weight_puesto"]),
        skills=float(settings["score_weight_skills"]),
        ubicacion=float(settings["score_weight_ubicacion"]),
        seniority=float(settings["score_weight_seniority"]),
    )
```

---

## Info

### IN-01: `worker` depends on `ui` but only shares the SQLite volume — dependency is misleading

**File:** `docker-compose.yml:61-63`
**Issue:** `worker` declares `depends_on: ui`. The worker does not communicate with the `ui` Streamlit service at all — both services are independent consumers of the shared `data` volume (SQLite DB). The `depends_on` without `condition: service_healthy` only guarantees that Docker starts the `ui` container before the `worker` container, not that Streamlit is ready. Since the worker reads/writes directly to the DB file, there is no real dependency on the `ui` service being alive. The dependency is semantically incorrect: it implies a coupling that doesn't exist and will cause the worker not to start at all if the `ui` service is in a crash loop (see WR-01).

**Fix:** Remove the `depends_on: ui` from the `worker` service. If startup ordering is desired for operational reasons (e.g., ensuring `init_db()` runs from the ui path before the worker), use `depends_on` with `condition: service_healthy` and add a proper healthcheck to the `ui` service.

---

### IN-02: `score_json TEXT` column has no `NOT NULL` constraint — `get_history()` would silently drop the row

**File:** `app/storage/sqlite.py:77`
**Issue:** The `jobs` table defines `score_json TEXT` without `NOT NULL`. In `get_history()`, rows with a `NULL` `score_json` (which cannot be inserted by the current code path but could arise from direct DB manipulation or future code) would be silently dropped with a warning log because `JobScore.model_validate_json(None)` raises `TypeError`, which is caught by the bare `except Exception`. This is not a correctness bug today (the `upsert_scored_jobs` path always supplies a non-null `score_json`), but the schema doesn't enforce the invariant and the error message for a NULL case would be confusing.

**Fix:** Add `NOT NULL` to `score_json`:
```sql
score_json TEXT NOT NULL,
```
This makes the DB schema self-documenting and prevents a class of silent data loss.

---

_Reviewed: 2026-05-25T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
