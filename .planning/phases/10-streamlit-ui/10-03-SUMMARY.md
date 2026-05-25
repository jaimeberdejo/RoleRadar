---
phase: 10-streamlit-ui
plan: "03"
subsystem: ui
tags: [streamlit, navigation, embedder-singleton, threading, run-status, wave-2]
dependency_graph:
  requires: [10-02]
  provides: [ui/services.py, ui/app.py]
  affects: [ui/pages/cv.py, ui/pages/search.py, ui/pages/results.py, ui/pages/settings.py, ui/pages/status.py]
tech_stack:
  added: []
  patterns:
    - "@st.cache_resource for non-serializable ML model singleton (UI-10/SC7)"
    - "threading.Thread + module-level dict for non-blocking UI runs (D-04)"
    - "threading.Lock for all _RUN_STATUS mutations (D-06)"
    - "st.navigation + st.Page for 5-page programmatic multipage navigation (D-01)"
key_files:
  created:
    - ui/services.py
    - tests/ui/test_services.py
  modified:
    - ui/app.py
decisions:
  - "get_embedder() and get_storage() both use @st.cache_resource (not @st.cache_data) because BgeM3Embedder and SQLiteStorage are non-serializable objects"
  - "All _RUN_STATUS mutations use threading.Lock even though CPython GIL would mostly protect them — explicit lock is hygiene (Assumption A3 from RESEARCH)"
  - "Background thread is daemonized so process exit is not blocked if user closes the browser"
  - "BgeM3Embedder patched in tests via patch+get_embedder.clear() to avoid loading the 2.3 GB model (Pitfall 7)"
metrics:
  duration_minutes: 3
  completed: "2026-05-25"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 3
---

# Phase 10 Plan 03: UI Shell — services.py + app.py Navigation Summary

**One-liner:** Streamlit navigation shell (5-page st.navigation, set_page_config first) and shared helpers module (@st.cache_resource embedder/storage singleton, lock-guarded non-blocking run-status machinery with zero st.* calls in the background thread).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ui/services.py — cached embedder, storage, run-status machinery | 1307979 | ui/services.py (created) |
| 2 | ui/app.py — st.navigation shell (replace stub) | 475fff6 | ui/app.py (replaced) |
| 3 | tests/ui/test_services.py — embedder singleton + run-status | 71475f5 | tests/ui/test_services.py (created) |

## What Was Built

### ui/services.py
The shared seam that all 5 page modules (Plans 04-06) will import:

- `get_embedder()` — `@st.cache_resource` wrapper that creates exactly one `BgeM3Embedder` per Streamlit process lifetime. Satisfies UI-10/SC7/D-03. The cached instance is injected into `run_pipeline(embedder=...)` so no second 2.3 GB model loads during "Run now" (D-05).
- `get_storage()` — `@st.cache_resource` SQLiteStorage singleton. init_db is idempotent so repeated calls are safe.
- `get_effective_profile(profile_path=None)` — thin passthrough to `app.profile_overlay.build_effective_profile(settings, profile_path)`. Reads settings from storage and applies overlay.
- `_RUN_STATUS` dict (`{"running": False, "result": None, "error": None}`) guarded by `_RUN_LOCK` (threading.Lock).
- `_run_pipeline_thread(storage, embedder, profile_path)` — background thread target. Contains ZERO `st.*` calls (T-10-03-01 mitigation). Writes only to `_RUN_STATUS` under the lock.
- `start_run(profile_path=None) -> bool` — checks `_RUN_STATUS["running"]` under the lock before starting; returns `False` if already running (T-10-03-02 / D-06 double-run guard). Spawns daemon thread.

### ui/app.py
The Streamlit entry point replacing the "UI en construcción" stub:
- `st.set_page_config(...)` is the FIRST `st.*` call (Pitfall 6 — must precede `st.navigation`).
- 5 pages registered via `st.Page`: CV, Búsqueda, Resultados (default=True), Configuración, Estado.
- Paths relative to `ui/app.py` → `pages/cv.py` etc. (created in Plans 04-06; expected to be absent at this stage).
- `pg = st.navigation([...])` then `pg.run()`.

### tests/ui/test_services.py
3 tests covering the services contract (SC7 + D-04/D-05/D-06):
- `test_embedder_singleton` — patches `BgeM3Embedder` constructor + clears cache → calls `get_embedder()` twice → asserts `a is b` (identity equality).
- `test_start_run_refuses_double` — sets `_RUN_STATUS["running"]=True` directly → asserts `start_run()` returns `False`.
- `test_run_status_completes` — patches `app.pipeline.run_pipeline` to return `_FakePipelineResult(scored=2)` → calls `start_run()` → polls `_RUN_STATUS["running"]` with 3 s timeout → asserts `running=False`, `result.scored==2`, `error=None`.
- `autouse` fixture resets `_RUN_STATUS` before and after every test to prevent leakage.

## Verification Results

```
# Unit tests
uv run python -m pytest tests/ui/test_services.py -q   → 3 passed
uv run python -m pytest --tb=no                        → 304 passed (301 pre-existing + 3 new)

# Import-cleanliness
python -c "import app.pipeline, app.profile_overlay; ..."  → streamlit NOT in sys.modules

# ui/app.py
python -c "import ast; ast.parse(open('ui/app.py').read())"  → OK
grep -c "st.Page("  ui/app.py                               → 5
awk order check (set_page_config before st.navigation)       → OK
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

The 5 page files (`ui/pages/cv.py`, `ui/pages/search.py`, `ui/pages/results.py`, `ui/pages/settings.py`, `ui/pages/status.py`) do not yet exist. This is intentional and per-plan: `ui/app.py` registers the pages by path; the page files will be created in Plans 04-06 (Wave 3). The navigation shell cannot be run via `streamlit run ui/app.py` until the page files exist — this is the expected interface-first ordering.

## Threat Surface Scan

No new network endpoints, auth paths, or trust-boundary schema changes introduced. The only new surface is the background-thread pipeline launcher — already analyzed in the plan's threat model (T-10-03-01 through T-10-03-04) and mitigated by: zero `st.*` in the thread body (T-10-03-01), lock-guarded double-run check (T-10-03-02), `@st.cache_resource` singleton with test-verified identity (T-10-03-03).

## Self-Check: PASSED
