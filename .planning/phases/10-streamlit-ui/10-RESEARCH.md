# Phase 10: Streamlit UI - Research

**Researched:** 2026-05-25
**Domain:** Streamlit 1.57 multipage app wiring; threading; caching; Pydantic v2 overlay
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Streamlit multipage via `st.navigation` + `st.Page` (programmatic API). Pages: CV,
  Search Config, Results, Settings, Status. `ui/app.py` is the entry point; page bodies live in
  `ui/pages/*.py`. Keep page modules thin — call into core.
- **D-02:** Shared helpers in `ui/services.py` (or `ui/state.py`): cached embedder, storage
  accessor, settings read/write, effective-profile builder. Page modules import these.
- **D-03:** `BgeM3Embedder` created **once per Streamlit process** via `@st.cache_resource`.
  NEVER at module top level, NEVER per interaction. Hard requirement (SC7).
- **D-04:** "Run now" calls `run_pipeline()` in a **background `threading.Thread`**, NOT inline.
  UI shows live status (`st.status`/spinner) by polling a thread-status flag + the `runs` table,
  and `st.rerun()`s when the thread finishes.
- **D-05 (RAM-critical):** "Run now" passes the `@st.cache_resource` embedder into
  `run_pipeline(embedder=...)`. A manual run must NOT load a second BGE-M3 in the UI process.
- **D-06:** Guard against two concurrent UI runs with a session/global "run in progress" flag
  (disable the button while running). SQLite WAL already handles worker/UI write concurrency.
- **D-07:** Effective-profile overlay: before scoring, overlay settings-table operational knobs
  onto profile.yaml's UserProfile — `pesos` from `score_weight_*` settings, `deal_breakers`
  from a new `deal_breakers` JSON setting. `profile.yaml` remains identity-only.
- **D-08:** Weight editing must respect PesosScoring sum-to-1.0 invariant. Settings page
  validates or normalizes before persisting.
- **D-09:** `rescore_stored_jobs()` path: read stored jobs, rebuild `Job`, re-run `score_job`
  with effective profile + cached embedder, `upsert_scored_jobs`. Lives in `app/pipeline.py`.
- **D-10:** Results list via `st.dataframe` with filter widgets. Selecting a row shows full
  breakdown using `get_history` row→dict + `JobScore.model_validate_json`.
- **D-11:** Status page reads `get_recent_runs()` → last run, next run, counts. Read-only.
- **D-12:** CV page: `st.file_uploader` → `pdf_hash` → `load_cached_profile` → on miss,
  `parse_cv(pdf_bytes)` + `save_cached_profile`. Cache hit: no re-parse.
- **D-13:** README rewritten for v2.0 standalone. n8n section archived/retired.

### Claude's Discretion

- Exact widget choices, page ordering, sidebar vs top filters, default Streamlit theme.
- Whether effective-profile overlay + rescore live in `app/pipeline.py` vs a new
  `app/profile_overlay.py` (must stay import-clean — no streamlit in `app/`).
- Thread-status signalling mechanism for "Run now".

### Deferred Ideas (OUT OF SCOPE)

- `num_pages` in the UI (UI-11) — v2.x
- Salary filter/column — v2.x
- Authentication on the Streamlit app — out of scope
- Custom theming — out of scope
- Live websocket push of worker progress — out of scope; polling the runs table suffices
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| UI-01 | Upload CV (PDF) → parse and cache CVProfile; show parse state + extracted profile | D-12: `parse_cv` + `pdf_hash` + cache; SC1 test pattern confirmed |
| UI-02 | Configure search conditions (country, language, positions, date_posted, types, remote-only) persisted in settings | `set_setting` already tested; search params already in settings table defaults |
| UI-03 | Browse all scored offers (list: title, company, score, recommendation; sort/filter) | `st.dataframe` with `on_select="rerun"` + `selection_mode` confirmed in 1.57 |
| UI-04 | Detail view: full score breakdown, reasons, skills | `get_history` returns `score.model_dump()` with all fields; use `st.expander` |
| UI-05 | Tune scoring weights + threshold; persist for worker | Overlay via `model_copy(update=...)` on UserProfile/PesosScoring; PesosScoring sum-to-1.0 invariant verified |
| UI-06 | Edit deal-breakers list; persist (not just in profile.yaml) | New `deal_breakers` JSON setting in settings table; overlay applies it |
| UI-07 | "Run now" button — non-blocking pipeline trigger | `threading.Thread` + module-level status dict + `st.fragment(run_every="2s")` polling pattern; ScriptRunContext gotcha documented |
| UI-08 | Re-score stored jobs with current weights, no re-fetch, with cost warning | `rescore_stored()` sibling in `app/pipeline.py`; `get_history` returns enough to reconstruct `Job` |
| UI-09 | Scheduler status panel — last run / next run / new offers found | `get_recent_runs()` already returns all required columns |
| UI-10 | UI stays responsive during long ops; embedder not reloaded per interaction | `@st.cache_resource` confirmed; thread passes cached instance into `run_pipeline(embedder=...)` |
| DOC-04 | README rewritten for v2.0 standalone | Content decision; no library research needed |
</phase_requirements>

---

## Summary

Phase 10 is a pure integration phase: the BuscadorDeEmpleo core (cv/dedup/scoring/storage/pipeline/notifications) is already built and import-clean. This phase wires it into a Streamlit 1.57 multipage app. The primary research questions are about Streamlit-specific mechanics: the programmatic navigation API, the correct caching decorator for a non-serializable ML model, the non-blocking threading pattern, and how to poll thread status without calling `st.*` from the background thread.

All seven high-value research questions are answered concretely below. The findings are grounded in Streamlit 1.57's actual API (verified via `uv run python` introspection and Context7 docs). Key findings: `st.navigation` + `st.Page` is the correct current API and `st.Page` accepts a `Callable` as well as a file path; `@st.cache_resource` is confirmed as the right decorator for BgeM3Embedder; the safest "Run now" pattern uses a module-level status dict (not `session_state`) to communicate across the thread boundary, combined with `st.fragment(run_every="2s")` to poll without full-page freezes; Pydantic v2 `model_copy(update={"pesos": ..., "deal_breakers": ...})` handles the overlay cleanly; `AppTest` from `streamlit.testing.v1` is available in 1.57 and supports widget simulation but has limits on `st.navigation` multi-page smoke tests.

**Primary recommendation:** Implement the "Run now" status polling via `st.fragment(run_every="2s")` that reads a module-level `_run_status` dict; this is the cleanest pattern in Streamlit 1.57 that avoids both the `ScriptRunContext` warning and full-page freezes.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CV upload + parse | UI (Streamlit page) | Core (`app/cv/`) | File bytes arrive via `st.file_uploader`; all parse logic stays in `app/cv/` |
| Settings persistence | Storage (SQLite `settings` table) | UI (read/write via `set_setting`) | Cross-process config bus; worker reads same table |
| Effective-profile overlay | Core helper (`app/` — no Streamlit) | UI calls helper | Must be import-clean; used by worker, Run now, Re-score |
| Embedder lifecycle | Streamlit process singleton (`@st.cache_resource`) | — | Non-serializable ML model; one instance per process |
| Run now (job fetch + score) | Background thread | Core (`run_pipeline`) | Non-blocking; thread calls pure Python with no `st.*` |
| Run now status polling | Streamlit fragment (`st.fragment run_every`) | Module-level status dict | Fragment polls dict every 2 s without full-page freeze |
| Re-score stored jobs | Core (`rescore_stored()` in `app/pipeline.py`) | UI triggers | Import-clean; reuses `score_job` + cached embedder |
| Results browsing + detail | UI (Streamlit `st.dataframe` + `st.expander`) | Storage (`get_history`) | Presentation only; data from storage |
| Scheduler status | UI (read-only `get_recent_runs()`) | Storage (runs table) | Read-only panel; no business logic |
| Secret display (never) | UI (boolean flags only) | — | Never render env-var values in the browser |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| streamlit | 1.57.0 | Multipage app framework | Already in pyproject.toml; confirmed installed |
| streamlit.testing.v1 | (bundled) | Unit-level app testing without browser | Available in 1.57; `AppTest` confirmed importable |
| threading (stdlib) | 3.13+ | Background "Run now" without freezing UI | No extra dep; correct tool for non-blocking work in same process |

All versions verified: `uv run streamlit --version` → 1.57.0 [VERIFIED: uv run]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | (bundled transitive dep) | `st.dataframe` input format | Results page DataFrame construction |
| json (stdlib) | — | Serialize `deal_breakers` list to settings string | Settings overlay for `deal_breakers` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `threading.Thread` + module-level dict | `add_script_run_ctx` to call `st.*` from thread | `add_script_run_ctx` is internal/unsupported API; module-level dict is stable and officially documented pattern |
| `threading.Thread` + polling | `st.fragment(run_every=...)` only (no thread) | Fragment can't run blocking pipeline code; thread does the work, fragment does the polling |
| `st.fragment(run_every=...)` polling | `st.rerun()` in a loop | `st.rerun()` in a loop blocks/re-renders the whole page; fragment rerun is scoped and cheaper |
| `get_history()` for rescore | New SQL query with full `Job` reconstruction | `get_history()` already returns all fields needed; `get_undelivered_qualifying` also returns full `ScoredJob`; either accessor suffices |

**Installation:** Already present in `pyproject.toml`. No new deps required for this phase.

---

## Architecture Patterns

### System Architecture Diagram

```
User (browser)
    │
    ▼
ui/app.py  ── st.navigation([CV, Search Config, Results, Settings, Status])
    │                │
    │          pg.run()  (executes selected page module)
    │
    ├─ ui/pages/cv.py
    │       │  st.file_uploader → pdf_hash → load_cached_profile
    │       │      (cache miss) → parse_cv(pdf_bytes) → save_cached_profile
    │       └──────────────────────────────────────────────────────────────▶ app/cv/
    │
    ├─ ui/pages/results.py
    │       │  st.dataframe(history_df) [on_select="rerun"]
    │       │  "▶ Run now" button
    │       │      │  ← checks _RUN_STATUS["running"] (module-level dict)
    │       │      └─▶ threading.Thread(target=_run_pipeline_thread).start()
    │       │              │  [NO st.* calls]
    │       │              └─▶ run_pipeline(storage, embedder=get_embedder(), ...)
    │       │                      └─▶ app/pipeline.py (fetch → dedup → score → persist)
    │       │
    │       │  @st.fragment(run_every="2s") poll_status_fragment()
    │       │      │  reads _RUN_STATUS["running"] / ["result"]
    │       │      └─▶ st.rerun() when done (full-app rerun refreshes results)
    │       │
    │       │  "↻ Re-score stored" button
    │       │      └─▶ rescore_stored(storage, get_embedder(), effective_profile)
    │       │              └─▶ app/pipeline.py::rescore_stored()
    │       └──────────────────────────────────────────────────────────────▶ app/storage/
    │
    ├─ ui/pages/settings.py
    │       │  PesosScoring widgets → validate sum==1.0 → set_setting(key, val)
    │       │  deal_breakers editor → json.dumps(list) → set_setting("deal_breakers", ...)
    │       └──────────────────────────────────────────────────────────────▶ app/storage/
    │
    ├─ ui/pages/search.py
    │       └─▶ set_setting(search_country / search_query / date_posted / ...)
    │
    ├─ ui/pages/status.py
    │       └─▶ get_recent_runs() → st.metric + st.dataframe
    │
    └─ ui/services.py  (shared helpers — no st.* at module level)
            │  get_embedder()          → @st.cache_resource (BgeM3Embedder)
            │  get_storage()           → SQLiteStorage (module-level singleton or cached)
            │  build_effective_profile()  → UserProfile.model_copy(update={...})
            └─▶ app/ core (all in-process calls)
```

### Recommended Project Structure

```
ui/
├── app.py               # entry: st.navigation + pg.run()
├── services.py          # @st.cache_resource embedder; storage; effective-profile builder
└── pages/
    ├── cv.py            # UI-01
    ├── search.py        # UI-02
    ├── results.py       # UI-03, UI-04, UI-07, UI-08
    ├── settings.py      # UI-05, UI-06
    └── status.py        # UI-09

app/
├── pipeline.py          # (EXISTING) run_pipeline() + NEW rescore_stored()
└── ...                  # all other core modules unchanged
```

### Pattern 1: st.navigation + st.Page (D-01)

**What:** The programmatic multipage API in Streamlit ≥ 1.36 (current: 1.57). `st.Page` accepts either a file path string (relative to the entry file) or a `Callable[[], None]`. Pages are registered in `st.navigation()`, which returns the selected page object; calling `.run()` on it executes that page.

**When to use:** Always — this is the recommended current API. The legacy auto-`pages/` magic-dir still works but is not preferred. [VERIFIED: Context7 /streamlit/docs + `uv run python -c "inspect.signature(st.Page)"`]

```python
# Source: Context7 /streamlit/docs — multipage fundamentals + introspection
# ui/app.py
import streamlit as st

cv_page      = st.Page("pages/cv.py",     title="CV",            icon=":material/description:")
search_page  = st.Page("pages/search.py", title="Búsqueda",      icon=":material/search:")
results_page = st.Page("pages/results.py",title="Resultados",    icon=":material/work:", default=True)
settings_page= st.Page("pages/settings.py",title="Configuración",icon=":material/settings:")
status_page  = st.Page("pages/status.py", title="Estado",        icon=":material/schedule:")

st.set_page_config(page_title="BuscadorDeEmpleo", page_icon=":material/work:", layout="wide")
pg = st.navigation([cv_page, search_page, results_page, settings_page, status_page])
pg.run()
```

Verified `st.Page` signature: `st.Page(page: str | Path | Callable[[], None], *, title=None, icon=None, url_path=None, default=False, visibility='visible')` [VERIFIED: introspection on 1.57.0]

Verified `st.navigation` signature: `st.navigation(pages: Sequence[PageType] | Mapping[SectionHeader, Sequence[PageType]], *, position='sidebar', expanded=False)` [VERIFIED: introspection on 1.57.0]

**st.set_page_config must be the FIRST Streamlit call in app.py** (before `st.navigation`) — calling it after any other Streamlit command raises `StreamlitAPIException`. [VERIFIED: Context7 pattern]

### Pattern 2: @st.cache_resource for BgeM3Embedder (D-03)

**What:** `@st.cache_resource` caches the return value of a function globally across all sessions and reruns. Unlike `@st.cache_data`, it does NOT serialize the return value — required for non-serializable objects like ML models. The function runs exactly once per Streamlit process lifetime (unless the cache is cleared). [VERIFIED: Context7 /streamlit/docs caching.md]

**Why not `@st.cache_data`:** `st.cache_data` requires pickling the return value. `BgeM3Embedder` wraps a `SentenceTransformer` model (~2.3 GB loaded into RAM) which is not picklable. `st.cache_resource` holds the object reference directly. [VERIFIED: Context7 — "Return values of st.cache_resource do not need to be serializable"]

**Thread-safety:** The cached BgeM3Embedder object itself is NOT protected by `@st.cache_resource` with a lock — the caching guarantees one construction, but concurrent calls to `.embed()` share the same Python object. In this project, only the background "Run now" thread calls `.embed()` via `run_pipeline(embedder=...)`, and at any given time at most one pipeline thread runs (guarded by `_RUN_STATUS["running"]` flag). Single-threaded `.embed()` usage is inherently safe; the `SentenceTransformer.encode()` method itself is not designed for concurrent calls so the single-thread guarantee is important. [ASSUMED — SentenceTransformer thread-safety; single-run guard in D-06 mitigates this regardless]

```python
# Source: Context7 /streamlit/docs — cache_resource pattern + introspection
# ui/services.py
import streamlit as st
from app.dedup.embedder import BgeM3Embedder

@st.cache_resource
def get_embedder() -> BgeM3Embedder:
    """Instantiate BgeM3Embedder once per Streamlit process.
    
    Called from Results page (Run now, Re-score) and from any page that needs
    embeddings. Returns the same instance on every call — no 2nd model load.
    """
    return BgeM3Embedder()
```

### Pattern 3: Non-blocking "Run now" (D-04, D-05) — the critical pattern

**The problem:** Streamlit is single-threaded per session. Calling `run_pipeline()` inline blocks the entire UI thread for the duration of the pipeline run (potentially minutes). The user sees no feedback and cannot interact with anything.

**Why `threading.Thread` from the Streamlit thread loses context:** Streamlit attaches a `ScriptRunContext` to the script thread. Threads spawned from it do NOT automatically inherit this context. If the background thread calls any `st.*` function, Streamlit logs: `"Thread 'Thread-N': missing ScriptRunContext! This warning can be ignored when running in bare mode."` and the `st.*` call silently has no effect (or worse, writes to the wrong session). [VERIFIED: Context7 /streamlit/docs multithreading.md]

**The correct pattern — two halves:**

Half 1: The worker thread does NO `st.*` calls. It writes status to a module-level dict.
Half 2: A `@st.fragment(run_every="2s")` in the Results page polls the dict and renders status.

Why `@st.fragment` instead of `st.rerun()` loop:
- `st.fragment(run_every="2s")` causes only the fragment function to rerun every 2 seconds, not the whole page. This is cheap and doesn't discard widget state outside the fragment.
- `st.fragment` is available in Streamlit 1.57.0 [VERIFIED: `"fragment" in dir(st)` on 1.57.0, signature confirmed].
- When the fragment detects `_RUN_STATUS["done"] = True`, it calls `st.rerun()` for a full-app rerun to refresh the Results dataframe with new data.

```python
# Source: Context7 /streamlit/docs — multithreading.md + fragment docs
# Conceptual pattern — planner writes the actual implementation

# ui/services.py  ──  module-level status dict (NOT session_state — visible across reruns)
_RUN_STATUS: dict = {"running": False, "result": None, "error": None}

def _run_pipeline_thread(storage, embedder, profile_path) -> None:
    """Runs in background thread. NEVER calls st.* functions."""
    from app.pipeline import run_pipeline, PipelineResult
    _RUN_STATUS["running"] = True
    _RUN_STATUS["result"] = None
    _RUN_STATUS["error"] = None
    try:
        result: PipelineResult = run_pipeline(
            storage=storage,
            embedder=embedder,          # ← D-05: the @st.cache_resource instance
            profile_path=profile_path,
        )
        _RUN_STATUS["result"] = result
    except Exception as exc:
        _RUN_STATUS["error"] = str(exc)
    finally:
        _RUN_STATUS["running"] = False

# ui/pages/results.py
import threading
import streamlit as st
from ui.services import get_embedder, get_storage, _RUN_STATUS

def run_now_button():
    """Run Now button + status — call this at the top of results.py."""
    if st.button("▶ Run now", disabled=_RUN_STATUS["running"]):
        if not _RUN_STATUS["running"]:
            t = threading.Thread(
                target=_run_pipeline_thread,
                args=(get_storage(), get_embedder(), None),
                daemon=True,
            )
            t.start()
            st.rerun()   # force immediate rerun so button disables

    # Fragment polls every 2 seconds while a run is active
    _poll_run_status()

@st.fragment(run_every="2s" if _RUN_STATUS["running"] else None)
def _poll_run_status():
    if _RUN_STATUS["running"]:
        st.status("Buscando y puntuando ofertas…", state="running")
    elif _RUN_STATUS["result"] is not None:
        result = _RUN_STATUS["result"]
        st.success(f"Run completado — {result.scored} nuevas ofertas puntuadas.")
        _RUN_STATUS["result"] = None   # clear after display
        st.rerun()                      # full-app rerun → Results refreshes
    elif _RUN_STATUS["error"] is not None:
        st.error(f"Error en el run: {_RUN_STATUS['error']}")
        _RUN_STATUS["error"] = None
```

**Critical gotchas in this pattern:**
1. The fragment's `run_every` must be dynamic: pass `"2s"` when running, `None` when idle (avoids unnecessary polling when nothing is happening). The `run_every` parameter is evaluated each time the parent page reruns.
2. `_RUN_STATUS` is a module-level dict — one instance per Streamlit process, shared across all sessions. For a personal single-user tool this is fine and simpler than per-session tracking. For multi-user, use `st.session_state` keyed by session id. [ASSUMED — single user; stated in CLAUDE.md "personal tool"]
3. The background thread writes to `_RUN_STATUS` without a lock because Python dict writes for simple keys are GIL-protected for CPython. For production code, add `threading.Lock`. [ASSUMED — CPython GIL behavior; recommended to add lock anyway]
4. `st.button(disabled=...)` is re-evaluated on each script rerun. When `_RUN_STATUS["running"]` is `True`, the button renders as disabled — preventing double-runs (D-06).

**Alternative via `add_script_run_ctx`:** Streamlit documents this as an unsupported internal API. Avoid for production code. [VERIFIED: Context7 — "this is an internal API and not officially supported"]

### Pattern 4: Settings → UserProfile Overlay (D-07, D-08)

**What:** Build an "effective UserProfile" by loading profile.yaml and overlaying the four scoring-weight settings + deal_breakers from the settings table. Used by Run now, Re-score, and (optionally) the scheduled worker.

**Pydantic v2 `model_copy`:** Creates a shallow or deep copy of a model with specific field overrides. When the override is a nested model (`pesos: PesosScoring`), pass the new nested instance directly. `model_copy` re-runs field-level validators but NOT `@model_validator`-decorated validators by default. To force the PesosScoring sum-to-1.0 validator, construct a new `PesosScoring(...)` and pass it as the `pesos` update — the validator runs at `PesosScoring.__init__`. [VERIFIED: Context7 /pydantic/pydantic models.md]

```python
# Source: Context7 /pydantic/pydantic — model_copy docs
# app/profile_overlay.py  (OR in app/pipeline.py — planner decides; must NOT import streamlit)
from __future__ import annotations
from app.models.schemas import UserProfile, PesosScoring
from app.config.loader import load_user_profile
import json
from pathlib import Path

def build_effective_profile(settings: dict, profile_path: str | Path | None = None) -> UserProfile:
    """Overlay settings-table operational knobs onto profile.yaml UserProfile.
    
    Identity fields (datos_personales, ranking_puestos, preferencias_ubicacion,
    preferencia_remoto) come from profile.yaml unchanged.
    Operational fields (pesos, deal_breakers) are overridden by settings table values.
    
    Raises ValueError if constructed PesosScoring weights don't sum to 1.0
    (should be caught upstream in the Settings page before persisting).
    """
    base = load_user_profile(path=profile_path)

    # Build new PesosScoring from settings (validator enforces sum==1.0)
    new_pesos = PesosScoring(
        puesto=float(settings.get("score_weight_puesto", "0.35")),
        skills=float(settings.get("score_weight_skills", "0.30")),
        ubicacion=float(settings.get("score_weight_ubicacion", "0.20")),
        seniority=float(settings.get("score_weight_seniority", "0.15")),
    )

    # Parse deal_breakers from settings (JSON list string)
    raw_db = settings.get("deal_breakers", "")
    try:
        new_deal_breakers: list[str] = json.loads(raw_db) if raw_db else base.deal_breakers
    except (json.JSONDecodeError, TypeError):
        new_deal_breakers = base.deal_breakers

    return base.model_copy(update={"pesos": new_pesos, "deal_breakers": new_deal_breakers})
```

**Settings table gap:** `deal_breakers` key is NOT currently seeded in `init_db`'s `_SETTING_DEFAULTS`. The planner must add it. Default value: `json.dumps(profile.yaml's deal_breakers list)` OR `"[]"`. This requires a small `init_db` migration (already has pattern for idempotent column additions via `PRAGMA table_info`). [VERIFIED: reading sqlite.py — `_SETTING_DEFAULTS` dict does not contain `"deal_breakers"` key]

### Pattern 5: Re-score Stored Jobs (D-09)

**What:** Read all stored jobs, rebuild `Job` objects, re-run `score_job` with the current effective profile, upsert the new scores. No JSearch fetch.

**Data access:** `get_history(limit=N)` returns `list[dict]` where each dict has keys: `id`, `title`, `company`, `score_total`, `recommendation`, `first_seen`, `last_seen`, `score` (deserialized `JobScore.model_dump()`). It does NOT return `description`, `raw`, `url` directly — those are NOT stored in the jobs table.

Looking at `upsert_scored_jobs` and `was_seen`, the SQL schema is:
```sql
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT, title TEXT, company TEXT, location TEXT, remote TEXT,
    url TEXT, source TEXT, score_total INTEGER, recommendation TEXT,
    score_json TEXT, first_seen TEXT, last_seen TEXT, seen INTEGER
)
```

The `url` and `source` columns ARE in the table (confirmed from sqlite.py lines 67-84). A `Job` reconstruction from a history row needs: `id`, `title`, `company`, `location`, `remote`, `url`, `source` — all available in the jobs table. `description` and `raw` are NOT stored (description is the heavy field; `raw` is original payload). This means:

- `job.description` will be `""` (empty string) in a re-scored Job — `score_job` uses `job.description or ""` defensively throughout, so this produces a `encaje_skills = 50` (neutral) result since there's no description to embed.
- **This is a known limitation**: re-score without re-fetch cannot recompute skill cosine similarity. The re-score is mainly useful for updating `pesos` weights (deterministic recalculation), `deal_breakers`, and any seniority changes.

The planner should document this limitation in the UI confirmation dialog.

For a complete re-score accessor that returns `Job` objects (including description from storage), a new `get_history_jobs()` method on SQLiteStorage would be needed — but since description isn't stored, this isn't viable without re-fetching. The current approach is correct as designed. [VERIFIED: reading sqlite.py schema and get_history implementation]

```python
# app/pipeline.py — rescore_stored() sibling
def rescore_stored(
    *,
    storage=None,
    embedder=None,
    profile_path=None,
) -> PipelineResult:
    """Re-score all stored jobs with current effective profile. No JSearch fetch.
    
    description is not stored → encaje_skills will be 50 (neutral) for all jobs.
    Useful for weight/deal_breaker updates. See D-09.
    """
    from app.config.loader import load_user_profile  # noqa: PLC0415
    from app.storage import get_storage_backend  # noqa: PLC0415
    from app.models.schemas import Job, RemoteJob  # noqa: PLC0415

    result = PipelineResult()
    if storage is None:
        storage = get_storage_backend()
    if embedder is None:
        from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
        embedder = BgeM3Embedder()

    settings = storage.get_settings()
    user_profile = _build_effective_profile(settings, profile_path)  # overlay helper
    cv_profile = _get_cv_profile()

    history = storage.get_history(limit=10000)  # all stored jobs
    rescored: list[ScoredJob] = []
    for row in history:
        try:
            job = Job(
                id=row["id"],
                title=row["title"],
                company=row["company"],
                location=row.get("location"),
                remote=RemoteJob(row["score"]["recommendation"]),  # not stored... 
                # NOTE: remote not available in get_history dict — needs schema check
                url=None,
                source="rescore",
            )
            job_score = score_job(job, user_profile, cv_profile, embedder)
            rescored.append(ScoredJob(job=job, score=job_score))
        except Exception as exc:
            result.errors.append(f"rescore({row['id']}): {exc}")

    if rescored:
        storage.upsert_scored_jobs(rescored)
    result.scored = len(rescored)
    return result
```

**Important schema gap for rescore:** `get_history()` returns a dict with `score` as the deserialized `JobScore.model_dump()` but NOT `remote` as a top-level key — it's not included in the SELECT result dict (only `score_total`, `recommendation` at top level). The `remote` column IS in the DB. The planner should either:
- Add `remote` to the `get_history()` return dict (minor sqlite.py change), OR
- Use `get_undelivered_qualifying` as a model for reconstructing full `Job` objects (it already does this correctly from all table columns).

Recommended: add `"remote": row["remote"]` to the dict in `get_history()` — one-line change.

### Pattern 6: st.dataframe with row selection (D-10)

**What:** `st.dataframe` in Streamlit 1.57 supports interactive row selection via `on_select="rerun"` and `selection_mode`. [VERIFIED: `inspect.signature(st.dataframe)` on 1.57.0 confirms `on_select`, `selection_mode`, `selection_default` parameters]

```python
# Source: Context7 /streamlit/docs — row_selections.md tutorial
import pandas as pd
import streamlit as st

# Build DataFrame from get_history() results
history = get_storage().get_history(limit=200)
if not history:
    st.info("No hay ofertas puntuadas todavía. Pulsa «Run now» o espera al worker.")
    return

df = pd.DataFrame([{
    "Título": r["title"],
    "Empresa": r["company"],
    "Score": r["score_total"],
    "Recomendación": r["recommendation"],
    "_idx": i,
} for i, r in enumerate(history)])

# Score filter
min_score = st.slider("Score mínimo", 0, 100, 0, key="results_min_score")
rec_filter = st.multiselect(
    "Recomendación",
    ["strong_fit", "good_fit", "maybe", "skip"],
    default=["strong_fit", "good_fit", "maybe"],
    key="results_rec_filter",
)
filtered_df = df[(df["Score"] >= min_score) & (df["Recomendación"].isin(rec_filter))]

event = st.dataframe(
    filtered_df[["Título", "Empresa", "Score", "Recomendación"]],
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

# Detail view on row selection
if event.selection.rows:
    selected_idx = filtered_df.iloc[event.selection.rows[0]]["_idx"]
    row = history[selected_idx]
    score = row["score"]  # already deserialized JobScore.model_dump()
    with st.expander("Detalle completo", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Puesto", score["desglose"]["encaje_puesto"])
        col2.metric("Skills", score["desglose"]["encaje_skills"])
        col3.metric("Ubicación", score["desglose"]["encaje_ubicacion"])
        col4.metric("Seniority", score["desglose"]["encaje_seniority"])
        st.write("**Razones a favor:**", score["reasons_for"])
        st.write("**Razones en contra:**", score["reasons_against"])
```

**Sorting:** `st.dataframe` provides built-in column sorting by clicking headers — no extra code needed. Filtering is done before passing to `st.dataframe`.

### Pattern 7: AppTest for Streamlit testing

**What:** `streamlit.testing.v1.AppTest` simulates a Streamlit app run in Python without a browser. Available in Streamlit 1.57.0. [VERIFIED: `from streamlit.testing.v1 import AppTest` successful on 1.57.0]

**Limits with st.navigation multipage:** `AppTest.from_file("ui/app.py")` runs the entry file and executes the navigation setup. To test a specific page in isolation, use `AppTest.from_file("ui/pages/results.py")` and inject `session_state` before `.run()`. `AppTest.switch_page(page_path: str)` navigates to a different page. [VERIFIED: `AppTest.switch_page` confirmed in 1.57.0 introspection]

**What's reliably testable:**
- Widget state: button clicks, slider values, multiselect, text_input, etc.
- Non-background-thread paths: CV page cache hit/miss, Settings save, Search Config save
- Exception absence: `assert not at.exception`
- Output elements: `at.success[0].value`, `at.error[0].value`, `at.markdown[0].value`

**What's NOT reliable in AppTest:**
- Background thread behavior (threading.Thread spawned inside `.run()` may not complete before test assertions)
- `@st.cache_resource` — the cache is fresh for each `AppTest` run, so the model would load (avoid in tests; mock via `@patch`)
- The "run in progress" live status (fragment polling is not easily simulated)

**Recommended testing strategy (from CONTEXT.md `<specifics>`):**
1. **Unit-test the core helpers** (pytest, no AppTest needed):
   - `build_effective_profile(settings, profile_path)` — verifies overlay logic + PesosScoring validation
   - `rescore_stored()` — with FakeEmbedder + in-memory SQLite
   - `next_run_from_settings(settings)` — deterministic datetime computation
   - Run-status state machine (mock thread, check dict state)
2. **AppTest smoke tests** (nice-to-have, not blocking):
   - Settings page: input weights → save → verify `st.success` present
   - CV page: inject `session_state` to simulate cache hit → verify CVProfile display
   - Status page: inject storage with sample runs → verify `st.metric` counts

```python
# Source: Context7 /streamlit/docs — AppTest tutorial
# tests/ui/test_settings_page.py
from streamlit.testing.v1 import AppTest
from unittest.mock import patch

def test_settings_page_weight_validation(tmp_path):
    """Settings page shows error when weights don't sum to 1.0."""
    at = AppTest.from_file("ui/pages/settings.py", default_timeout=10)
    # Mock storage so no real DB needed
    with patch("ui.services.get_storage") as mock_storage:
        mock_storage.return_value.get_settings.return_value = {
            "score_weight_puesto": "0.35",
            "score_weight_skills": "0.30",
            "score_weight_ubicacion": "0.20",
            "score_weight_seniority": "0.15",
        }
        at.run()
        # Simulate bad weights (don't sum to 1.0)
        at.number_input[0].set_value(0.99).run()  # puesto weight
        at.button[0].click().run()   # Save button
        assert at.error[0].value.startswith("Los pesos deben sumar 1.0")
```

### Anti-Patterns to Avoid

- **Calling `st.*` from a background thread:** Results in "missing ScriptRunContext" warnings and silent no-ops. The background thread ONLY writes to a module-level dict. [VERIFIED: Context7 multithreading.md]
- **Loading BgeM3Embedder at module top level:** `BgeM3Embedder._ensure_loaded()` imports sentence-transformers and loads 2.3 GB on first `.embed()`. At module top level, this happens at import time — 2-4 second delay on every page rerun, not once per process. [VERIFIED: reading embedder.py]
- **Calling `st.set_page_config` after other Streamlit calls:** Must be the first `st.*` call. Put it in `ui/app.py` before `pg = st.navigation(...)`. [VERIFIED: Streamlit docs pattern]
- **Using the legacy `pages/` magic directory:** Not wrong, but does not support programmatic navigation (role-based, dynamic pages). The `st.navigation` API in D-01 is preferred. [VERIFIED: Context7]
- **Importing `streamlit` in `app/` core modules:** Breaks the import-cleanliness invariant. The UI layer imports from `app/`; `app/` must never import from `ui/`. [VERIFIED: existing `test_import_cleanliness.py` pattern]
- **Persisting PesosScoring weights without validating sum:** The `PesosScoring` validator runs at construction time. If the UI calls `set_setting` with invalid weights and the worker constructs PesosScoring from them, the worker crashes mid-run. Validate in the UI before writing. [VERIFIED: reading schemas.py — `@model_validator(mode="after") check_sum`]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sortable/filterable table | Custom HTML table | `st.dataframe` with `on_select="rerun"` | Built-in sort, resize, search, clipboard; row selection API in 1.57 |
| Loading indicator during background work | Custom JS/AJAX | `st.fragment(run_every="2s")` + `st.status(state="running")` | Fragment-scoped rerun avoids full-page thrash; `st.status` has built-in spinner |
| ML model singleton | Python module-level variable | `@st.cache_resource` | Module-level is re-imported on each Streamlit hot-reload; cache_resource survives hot-reload within the same process |
| Weight normalization math | Custom normalization | Validate-and-reject with `PesosScoring` | The existing validator is the source of truth; normalization can silently hide user input errors |
| Page routing | Custom session_state switch | `st.navigation` + `st.Page` | Handles URL routing, browser history, page titles/favicons automatically |
| CV cache lookup | Custom file manager | `pdf_hash` + `load_cached_profile` + `save_cached_profile` (already built) | Already handles hash validation, missing file, corrupt JSON, path traversal prevention |

---

## Common Pitfalls

### Pitfall 1: "run_every" on fragment is always "2s" even when idle
**What goes wrong:** Fragment reruns every 2 seconds forever, even when no pipeline run is active. Wasteful; causes unnecessary reruns.
**Why it happens:** `run_every` is set statically at decoration time if not computed dynamically.
**How to avoid:** Pass `run_every="2s" if _RUN_STATUS["running"] else None` so the fragment self-stops when the run finishes. The fragment re-evaluates `run_every` on each parent page rerun, so flipping the flag works correctly.
**Warning signs:** Streamlit metrics show high rerun frequency when no operations are active.

### Pitfall 2: Double "Run now" click causes two pipeline threads
**What goes wrong:** User clicks "Run now" twice quickly → two `threading.Thread` instances → two concurrent `run_pipeline()` executions → SQLite contention + double scoring of the same jobs.
**Why it happens:** The button `disabled` state is only applied on the NEXT rerun (after the first click triggers `st.rerun()`). There's a brief window.
**How to avoid:** Check `_RUN_STATUS["running"]` BEFORE starting the thread: `if not _RUN_STATUS["running"]: _RUN_STATUS["running"] = True; thread.start()`. This sets the flag before `st.rerun()` is called, so the next rerun sees `disabled=True` immediately.
**Warning signs:** `_RUN_STATUS["running"]` already `True` when button callback runs.

### Pitfall 3: PesosScoring sum-to-1.0 validator crashes at scoring time, not at save time
**What goes wrong:** User saves weights that nearly sum to 1.0 but fail the `abs(total - 1.0) > 1e-6` check → `run_pipeline` crashes mid-run with `ValueError: Los pesos deben sumar 1.0`.
**Why it happens:** Floating-point arithmetic in the UI (e.g., 0.35 + 0.30 + 0.20 + 0.15 = 1.0000000000000002 in IEEE 754). Not caught until `PesosScoring(...)` is constructed.
**How to avoid:** Before calling `set_setting`, construct a `PesosScoring` with the candidate values in a `try/except ValidationError`. Show the error immediately. Alternatively, round weights to 4 decimal places before construction.
**Warning signs:** `ValidationError` mentioning "Los pesos deben sumar 1.0" in worker logs.

### Pitfall 4: `get_history` dict missing `remote` field → Job reconstruction fails in rescore
**What goes wrong:** `rescore_stored()` tries to reconstruct `Job` objects from `get_history()` dicts and finds no `remote` field → `RemoteJob(None)` raises `ValueError`.
**Why it happens:** `get_history()` currently does not include `remote` in the returned dict (only `id`, `title`, `company`, `score_total`, `recommendation`, `first_seen`, `last_seen`, `score`).
**How to avoid:** Add `"remote": row["remote"]` to `get_history()` return dict. One-line change in `sqlite.py`. [VERIFIED: reading get_history implementation — `remote` column in DB but not in dict]
**Warning signs:** `ValueError: 'None' is not a valid RemoteJob` in rescore logs.

### Pitfall 5: `deal_breakers` setting not seeded in `init_db` → KeyError in overlay
**What goes wrong:** On a fresh DB, `settings.get("deal_breakers", "")` returns `""` → overlay uses `base.deal_breakers` (from profile.yaml). This is acceptable behavior, but writing deal_breakers from the UI requires the key to exist. `set_setting` handles upsert so the write works. The issue is only if overlay code does `settings["deal_breakers"]` (dict access, not `.get()`).
**How to avoid:** Always use `settings.get("deal_breakers", "")` with a default. Optionally seed the key in `init_db` defaults. [VERIFIED: reading sqlite.py `_SETTING_DEFAULTS`]

### Pitfall 6: `st.set_page_config` called after `st.navigation`
**What goes wrong:** `StreamlitAPIException: `set_page_config()` can only be called once per app page, and must be called as the first Streamlit command in your script.`
**Why it happens:** `st.navigation` is itself a Streamlit command. If `set_page_config` comes after, it raises.
**How to avoid:** Always call `st.set_page_config(...)` as the FIRST line in `ui/app.py`, before `pg = st.navigation(...)`.

### Pitfall 7: `@st.cache_resource` embedder gets a new instance per test in AppTest
**What goes wrong:** AppTest clears caches between runs by default → `get_embedder()` constructs a real `BgeM3Embedder` → sentence-transformers is imported → model downloads (or fails in CI without network/GPU).
**Why it happens:** AppTest creates a fresh Streamlit session for each `at.run()`.
**How to avoid:** In tests, mock `get_embedder` at the services layer: `with patch("ui.services.get_embedder", return_value=FakeEmbedder()):`. Do not rely on AppTest cache behavior for the embedder.

---

## Code Examples

### Build effective profile and rescore (core helper)

```python
# Source: Pydantic v2 model_copy docs (Context7 /pydantic/pydantic) + codebase reading
# app/profile_overlay.py (import-clean — no streamlit)
import json
from pathlib import Path
from app.models.schemas import UserProfile, PesosScoring
from app.config.loader import load_user_profile

def build_effective_profile(
    settings: dict[str, str],
    profile_path: str | Path | None = None,
) -> UserProfile:
    """Overlay settings-table pesos + deal_breakers onto profile.yaml UserProfile."""
    base = load_user_profile(path=profile_path)
    new_pesos = PesosScoring(
        puesto=float(settings.get("score_weight_puesto", "0.35")),
        skills=float(settings.get("score_weight_skills", "0.30")),
        ubicacion=float(settings.get("score_weight_ubicacion", "0.20")),
        seniority=float(settings.get("score_weight_seniority", "0.15")),
    )
    raw_db = settings.get("deal_breakers", "")
    try:
        new_deal_breakers: list[str] = json.loads(raw_db) if raw_db else base.deal_breakers
    except (json.JSONDecodeError, TypeError):
        new_deal_breakers = base.deal_breakers
    return base.model_copy(update={"pesos": new_pesos, "deal_breakers": new_deal_breakers})
```

### Weight validation in Settings page

```python
# Source: schemas.py PesosScoring model_validator; Context7 /streamlit/docs
# ui/pages/settings.py (excerpt)
import streamlit as st
from pydantic import ValidationError
from app.models.schemas import PesosScoring

def save_weights(puesto: float, skills: float, ubicacion: float, seniority: float, storage) -> None:
    try:
        PesosScoring(puesto=puesto, skills=skills, ubicacion=ubicacion, seniority=seniority)
    except ValidationError as e:
        total = puesto + skills + ubicacion + seniority
        st.error(f"Los pesos deben sumar 1.0 (suman {total:.4f}).")
        return
    storage.set_setting("score_weight_puesto", str(puesto))
    storage.set_setting("score_weight_skills", str(skills))
    storage.set_setting("score_weight_ubicacion", str(ubicacion))
    storage.set_setting("score_weight_seniority", str(seniority))
    st.success("Guardado — el próximo run del worker usará estos pesos.")
```

### CV page cache-first pattern

```python
# Source: Context7 /streamlit/docs file_uploader; codebase app/cv/ reading
# ui/pages/cv.py
import streamlit as st
from app.cv.cache import pdf_hash, load_cached_profile, save_cached_profile
from app.cv.parser import parse_cv

def render_cv_page() -> None:
    st.header("CV")
    uploaded = st.file_uploader("Sube tu CV en PDF", type=["pdf"])
    if not uploaded:
        st.info("Aún no has subido un CV. El scoring de skills usará un perfil vacío.")
        return

    pdf_bytes = uploaded.read()
    h = pdf_hash(pdf_bytes)
    cached = load_cached_profile(h)
    if cached is not None:
        st.caption("Perfil cargado de caché (mismo PDF, no se re-parsea).")
        _render_cv_profile(cached)
        return

    with st.status("Parseando CV…", expanded=True):
        try:
            profile = parse_cv(pdf_bytes)
            save_cached_profile(h, profile)
            st.write("CV parseado y cacheado.")
        except Exception as exc:
            st.error(f"No se pudo parsear el CV: {exc}. Revisa que sea un PDF válido.")
            return
    _render_cv_profile(profile)
```

### Status page next-run computation

```python
# Source: codebase get_recent_runs + Python datetime stdlib
# ui/pages/status.py (excerpt)
from datetime import datetime, timezone, timedelta

def compute_next_run(runs: list[dict], schedule_interval_hours: float) -> datetime | None:
    """Compute expected next run from last run timestamp + interval."""
    if not runs:
        return None
    last_started = runs[0].get("started_at")
    if not last_started:
        return None
    try:
        last_dt = datetime.fromisoformat(last_started)
    except ValueError:
        return None
    return last_dt + timedelta(hours=schedule_interval_hours)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `pages/` magic directory (auto-discovery) | `st.navigation` + `st.Page` (programmatic) | Streamlit 1.36 | Full control over titles, icons, URL paths, conditional pages; recommended over magic dir |
| `@st.cache` (deprecated) | `@st.cache_data` + `@st.cache_resource` | Streamlit 1.18 | `cache_resource` for non-serializable objects (models, connections); `cache_data` for serializable data |
| `st.experimental_rerun()` | `st.rerun()` | Streamlit 1.27 | No longer experimental; same behavior |
| `st.experimental_fragment` | `st.fragment` | Streamlit 1.37 | Stable API; `run_every` parameter for auto-polling |

**Deprecated/outdated:**
- `@st.cache`: Removed in 1.18+. Use `@st.cache_data` or `@st.cache_resource`.
- `st.experimental_rerun()`: Replaced by `st.rerun()`.
- `pages/` magic directory: Still functional but `st.navigation` is the recommended current API for programmatic multipage apps.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | SentenceTransformer is not safe for concurrent calls from multiple threads | Pattern 2 (cache_resource thread-safety) | If it IS thread-safe, no risk; the single-run guard (D-06) already prevents concurrency anyway |
| A2 | `_RUN_STATUS` module-level dict is single-user (one concurrent session) | Pattern 3 (threading) | If multi-user, dict is shared across sessions → wrong status shown to second user. Acceptable: CLAUDE.md defines this as a personal single-user tool |
| A3 | CPython GIL makes dict key assignments thread-safe for simple types | Pattern 3 (threading) | If false, add `threading.Lock`; low risk on CPython but recommended hygiene |
| A4 | `sentence-transformers>=5.5.1` (in pyproject.toml) uses same `SentenceTransformer("BAAI/bge-m3")` API | Pattern 2 code example | If API changed in 5.5.x, embedder.py `_ensure_loaded` would already be broken in existing tests; low risk |

**Empty assumptions about Streamlit API:** All Streamlit API claims in this research were verified via `uv run python` introspection on Streamlit 1.57.0 and/or Context7 /streamlit/docs.

---

## Open Questions

1. **Where should `build_effective_profile` live?**
   - What we know: Must be import-clean (no streamlit); used by UI (Run now + Re-score), and optionally the worker.
   - What's unclear: `app/pipeline.py` (as a private helper used internally) vs `app/profile_overlay.py` (explicit module).
   - Recommendation: Claude's discretion (CONTEXT.md). `app/profile_overlay.py` is cleaner for testability; `app/pipeline.py` avoids a new module. Either works.

2. **Should the worker also use `build_effective_profile` for settings-driven pesos/deal_breakers?**
   - What we know: `run_pipeline()` currently calls `load_user_profile()` directly (no overlay). The worker won't see UI-edited weights/deal_breakers unless it uses the overlay too.
   - What's unclear: This is hinted at in D-07 ("used by worker + Run now + Re-score") but the existing worker.py calls `run_pipeline()` which calls `load_user_profile()`.
   - Recommendation: Yes — modify `run_pipeline()` to call `build_effective_profile(settings)` instead of `load_user_profile()` directly, so all three paths are consistent. This requires adding the overlay logic inside `run_pipeline` or passing `effective_profile` as a param.

3. **`get_history` limit for Re-score (how many jobs to re-score?)**
   - What we know: `get_history(limit=50)` default. Re-scoring ALL jobs is expensive (N OpenAI calls if key present).
   - Recommendation: `rescore_stored()` takes a `limit` param with a reasonable default (e.g., 500); UI warning shows count before confirming.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Streamlit | UI framework | ✓ | 1.57.0 (confirmed via `uv run`) | — |
| AppTest (streamlit.testing.v1) | UI smoke tests | ✓ | bundled with 1.57.0 | — |
| pytest | Test framework | ✓ | ≥9.0.3 (pyproject.toml) | — |
| pandas | st.dataframe | ✓ | (transitive dep of streamlit) | — |
| uv | Package runner | ✓ | 0.9.24 | — |

All required dependencies available. No blocking gaps.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥ 9.0.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ui/ -x -q` |
| Full suite command | `uv run pytest -q --tb=short` |

Current baseline: 286 tests passing. [VERIFIED: `uv run pytest --tb=no` on 2026-05-25]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| UI-01 (SC1) | CV cache hit → no re-parse | unit | `uv run pytest tests/ui/test_cv_page.py -x` | ❌ Wave 0 |
| UI-01 (SC1) | CV cache miss → parse + save | unit | `uv run pytest tests/ui/test_cv_page.py -x` | ❌ Wave 0 |
| UI-02 (SC2) | Search Config save → `set_setting` called | unit | `uv run pytest tests/ui/test_search_page.py -x` | ❌ Wave 0 |
| UI-05 (D-08) | Weights sum ≠ 1.0 → ValidationError, not persisted | unit | `uv run pytest tests/ui/test_settings_page.py::test_invalid_weights -x` | ❌ Wave 0 |
| UI-05 (D-08) | Weights sum = 1.0 → persisted via set_setting | unit | `uv run pytest tests/ui/test_settings_page.py::test_valid_weights -x` | ❌ Wave 0 |
| UI-07 (D-07) | Effective-profile overlay applies settings pesos | unit | `uv run pytest tests/ui/test_profile_overlay.py -x` | ❌ Wave 0 |
| UI-07 (D-07) | Effective-profile overlay applies deal_breakers | unit | `uv run pytest tests/ui/test_profile_overlay.py -x` | ❌ Wave 0 |
| UI-08 (D-09) | rescore_stored() re-scores stored jobs with new weights | unit | `uv run pytest tests/ui/test_rescore.py -x` | ❌ Wave 0 |
| UI-09 (SC6) | compute_next_run() returns correct datetime | unit | `uv run pytest tests/ui/test_status_helpers.py -x` | ❌ Wave 0 |
| UI-10 (SC7) | get_embedder() returns same instance on second call | unit | `uv run pytest tests/ui/test_services.py::test_embedder_singleton -x` | ❌ Wave 0 |
| import-clean | `ui/` modules do not import streamlit into `app/` | unit | `uv run pytest tests/test_import_cleanliness.py -x` | ✅ (extend) |
| AppTest smoke | Settings page renders without exception | smoke | `uv run pytest tests/ui/test_apptest_smoke.py -x` | ❌ nice-to-have |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ui/ -x -q` (new UI tests only, fast)
- **Per wave merge:** `uv run pytest -q --tb=short` (full 286+ suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/ui/__init__.py` — test package init
- [ ] `tests/ui/test_profile_overlay.py` — covers overlay + PesosScoring sum validation (UI-05, UI-06, UI-07)
- [ ] `tests/ui/test_rescore.py` — covers `rescore_stored()` with FakeEmbedder (UI-08)
- [ ] `tests/ui/test_status_helpers.py` — covers `compute_next_run()`, next-run calc (UI-09)
- [ ] `tests/ui/test_services.py` — covers `get_embedder()` singleton reuse (UI-10/SC7)
- [ ] `tests/ui/test_cv_page.py` — covers cache hit/miss logic extracted from cv.py (UI-01/SC1)
- [ ] `tests/ui/test_settings_page.py` — covers weight validation in settings.py (UI-05/D-08)
- [ ] `tests/ui/test_search_page.py` — covers search params persistence (UI-02/SC2)
- [ ] `tests/ui/test_apptest_smoke.py` — optional AppTest smoke tests (nice-to-have)

*(Note: UI logic tests target extracted pure-Python helpers — overlay, rescore, next-run — NOT the Streamlit widget layer. The widget layer is covered by AppTest smoke tests where feasible.)*

---

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Personal local tool; out of scope (CONTEXT.md deferred) |
| V3 Session Management | no | Single user; Streamlit session defaults sufficient |
| V4 Access Control | no | No multi-user; no role-based routes |
| V5 Input Validation | yes | PesosScoring sum-to-1.0 validator; JSON deserialization for deal_breakers |
| V6 Cryptography | no | No crypto operations in UI phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret value in UI render | Information Disclosure | Never render env-var values; show boolean "configured: ✓/✗" only (already in CONTEXT.md D and UI-SPEC) |
| Settings table injection | Tampering | All `set_setting` calls use parameterized `?` placeholders (already verified in sqlite.py) |
| Path traversal via pdf_hash | Tampering | `_validate_hash` in `cache.py` rejects non-hex-64 strings (already built; no new attack surface) |
| Arbitrary file read via file_uploader | Tampering | `st.file_uploader(type=["pdf"])` restricts MIME type; `pdf_hash` only reads bytes, does not execute |

---

## Sources

### Primary (HIGH confidence)
- `/streamlit/docs` (Context7) — `st.navigation`, `st.Page`, `st.cache_resource`, multithreading, `st.fragment`, `st.dataframe` row selection, `AppTest`
- Streamlit 1.57.0 runtime introspection via `uv run python` — all API signatures verified
- `/pydantic/pydantic` (Context7) — `model_copy(update=...)` pattern
- Codebase reading — `app/storage/sqlite.py`, `app/pipeline.py`, `app/scoring/scorer.py`, `app/models/schemas.py`, `app/dedup/embedder.py`, `app/cv/cache.py`, `app/cv/parser.py`, `app/config/loader.py`

### Secondary (MEDIUM confidence)
- Context7 /streamlit/docs multithreading.md — `add_script_run_ctx` vs module-level dict pattern; confirmed "internal API, not officially supported" warning

### Tertiary (LOW confidence — assumptions only)
- SentenceTransformer thread-safety claim (A1) — not verified against SentenceTransformers 5.5.x source; single-run guard (D-06) mitigates regardless

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified via introspection and Context7
- Architecture: HIGH — all APIs confirmed on 1.57.0; patterns from official docs
- Pitfalls: HIGH for Streamlit-specific pitfalls (verified); MEDIUM for SentenceTransformer concurrency (assumed)
- Threading pattern: HIGH — module-level dict + fragment polling is the recommended pattern from official Streamlit multithreading docs

**Research date:** 2026-05-25
**Valid until:** 2026-07-25 (Streamlit is fast-moving; verify `st.fragment` API if upgrading past 1.57)
