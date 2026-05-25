---
phase: 10-streamlit-ui
reviewed: 2026-05-25T00:00:00Z
depth: deep
files_reviewed: 14
files_reviewed_list:
  - app/profile_overlay.py
  - app/status_helpers.py
  - app/pipeline.py
  - app/storage/sqlite.py
  - ui/app.py
  - ui/services.py
  - ui/cv_logic.py
  - ui/results_logic.py
  - ui/settings_logic.py
  - ui/pages/cv.py
  - ui/pages/search.py
  - ui/pages/results.py
  - ui/pages/settings.py
  - ui/pages/status.py
findings:
  critical: 1
  warning: 7
  info: 5
  total: 13
status: resolved
resolved_at: 2026-05-25
resolution: "CR-01 + WR-01..WR-07 fixed (IN-03 too; IN-01/IN-02 acknowledged as intentional/noted). CR-01 (pipeline now consumes saved search settings — SC2) and WR-07 (re-score preserves original encaje_skills) each have a new regression test verified to fail without the fix. 363 tests green. Commits 50b8d10, b264045, 5adaea6, 31fc967, 0728e8d, 22035ed, 24eb91d."
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-25
**Depth:** deep (cross-file call-chain analysis)
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 10 wires the existing core (cv/dedup/scoring/storage/pipeline) into a Streamlit
multipage app. The stated security invariant — secrets rendered as booleans only — holds
cleanly: every secret access in the UI is `bool(os.getenv(...))`, no value ever reaches
`st.*` or logs (concern #3 verified clean). The `@st.cache_resource` embedder singleton is
correct and the cached instance is passed into both Run now and Re-score, so no second
BGE-M3 load occurs (concern #2 verified clean). CV upload uses sha256-keyed cache with a
strict 64-hex-char validator (`_HEX_RE`) preventing path traversal, restricts to PDF at the
widget, and wraps `resolve_cv_profile` in try/except (concern #6 verified clean). SQL is
fully parameterized and `deal_breakers` seeding uses `INSERT OR IGNORE` (concern #7 verified
clean).

However, the review surfaced one BLOCKER and several WARNINGs:

1. **The biggest functional defect (BLOCKER):** the Search Config page persists five settings
   (`search_query`, `search_language`, `employment_types`, `remote_only`, `date_posted`) that
   the fetch pipeline *never reads*. Queries come from `ranking_puestos`, and the pipeline
   overwrites `date_posted` with its own `date_posted_override`. The user can configure the
   search and click "Guardar — el próximo run usará estos parámetros", but the next run
   ignores almost all of it. This is silent, misleading no-op behavior in a tool the user
   relies on.

2. **Lock discipline is violated** in the Results polling fragment: the module docstring and
   `services.py` comment promise that *all* `_RUN_STATUS` mutations go through `_RUN_LOCK`, but
   `results.py` writes `_RUN_STATUS["result"]` and `_RUN_STATUS["error"]` directly without the
   lock, racing the background thread.

3. **Several unguarded conversions on persisted DB strings** (`float(...)`, `int(...)`,
   `json.loads(...)`) in the Settings page will raise and crash the page if the settings table
   ever holds a malformed/legacy value — the exact scenario the overlay defends against but the
   page does not.

The threading model is otherwise sound: the thread body never calls `st.*`, exceptions are
captured into `_RUN_STATUS["error"]`, `running` is reset in a `finally`, and `start_run()` has a
real lock-guarded double-run guard.

## Critical Issues

### CR-01: Search Config page persists settings the pipeline never consumes (silent no-op)

**File:** `ui/pages/search.py:49-54`, cross-referenced with `app/pipeline.py:176` and `app/sources/jsearch.py:132-134`
**Issue:** `save_search_settings()` writes `search_query`, `search_country`, `search_language`,
`date_posted`, `employment_types`, and `remote_only` to the settings table, and the page tells the
user *"Guardado — el próximo run del worker usará estos parámetros."* But the pipeline ignores most
of them:

- `pipeline.py:176` builds queries from `user_profile.ranking_puestos`, **not** `search_query`.
- `fetch_all_queries` (`jsearch.py:132-134`) reads only `date_posted_override`, `search_country`,
  and `num_pages`. It never reads `search_query`, `search_language`, `employment_types`, or
  `remote_only`.
- `pipeline.py:173-174` *overwrites* the run's `date_posted` with `date_posted_override`
  ("month"/"3days") computed from first-run logic, so the user's saved `date_posted` selectbox is
  also dead.

Net effect: of the six settings the page saves, only `search_country` actually influences a run.
The user is shown a success message implying control they do not have. For a tool whose core value
is "filter well against my real profile," a search-config page that doesn't configure the search is
a correctness/data-integrity defect, not a style nit.

**Fix:** Either (a) make the pipeline consume these settings — pass `search_query` (when non-empty)
into the query list, plumb `employment_types`/`remote_only`/`search_language` through
`fetch_all_queries` → `fetch_jsearch_query` params, and stop unconditionally overwriting
`date_posted`:

```python
# app/pipeline.py — respect saved date_posted unless first-run wants a wider window
saved_date = settings.get("date_posted")
date_posted = "month" if _is_first_run(storage) else (saved_date or "3days")
settings = {**settings, "date_posted_override": date_posted}

# build queries from saved search_query if present, else fall back to ranking
raw_query = (settings.get("search_query") or "").strip()
queries = [raw_query] if raw_query else [p.titulo for p in user_profile.ranking_puestos]
```

and in `jsearch.py` add `employment_types` / `remote_jobs_only` / `language` to `params`.
Or (b) if these knobs are intentionally out of scope for v2.0, remove the dead widgets and change
the page copy so the user is not told a falsehood. Do not leave the no-op widgets with the
"se usará" success message.

## Warnings

### WR-01: Polling fragment mutates `_RUN_STATUS` without `_RUN_LOCK` (lock-discipline violation / race)

**File:** `ui/pages/results.py:75,79`
**Issue:** `services.py:66-68` documents the invariant: *"All mutations go through `_RUN_LOCK` so the
thread and the Streamlit script thread never race."* But the polling fragment writes the shared dict
directly with no lock:

```python
_svc._RUN_STATUS["result"] = None   # line 75 — no _RUN_LOCK
_svc._RUN_STATUS["error"] = None    # line 79 — no _RUN_LOCK
```

These run on the main script thread while `_run_pipeline_thread` may be writing the same dict under
the lock. The documented guarantee is broken. In CPython the GIL makes a single key-assign atomic, so
this is unlikely to corrupt memory, but it (a) defeats the stated design contract and (b) creates a
genuine logical race: clearing `result`/`error` could clobber a fresh status the thread just wrote
between the read in `run_status_label` and these writes.

**Fix:** Route these clears through the lock (and through services, not by reaching into the module
global), e.g. add a `clear_run_result()` / `clear_run_error()` helper in `services.py`:

```python
# ui/services.py
def clear_run_result() -> None:
    with _RUN_LOCK:
        _RUN_STATUS["result"] = None

def clear_run_error() -> None:
    with _RUN_LOCK:
        _RUN_STATUS["error"] = None
```

and call `_svc.clear_run_result()` / `_svc.clear_run_error()` from the fragment.

### WR-02: Settings page crashes on malformed persisted `deal_breakers` JSON

**File:** `ui/pages/settings.py:120`
**Issue:** `current_db = json.loads(settings.get("deal_breakers", "[]"))` has no try/except. The
overlay (`profile_overlay.py:60-66`) explicitly defends against malformed/legacy `deal_breakers`
values in the settings table — which proves the team considers bad data there a real possibility —
but the Settings page does not. A non-JSON or non-list value (e.g. a legacy plain string, or a
truncated write) makes `json.loads` raise `JSONDecodeError`, which the page-render gate
(`except Exception: pass`, line 151-153) swallows, so the entire Settings page silently renders
blank/half-rendered with no error to the user.

**Fix:**
```python
import json
raw_db = settings.get("deal_breakers", "[]")
try:
    current_db = json.loads(raw_db)
    if not isinstance(current_db, list):
        current_db = []
except (json.JSONDecodeError, TypeError):
    current_db = []
```

### WR-03: Settings page `float()`/`int()` on persisted strings can crash the page

**File:** `ui/pages/settings.py:46,55,65,75,103`
**Issue:** Every weight `number_input` does `value=float(settings.get("score_weight_*", "..."))` and
the threshold does `value=int(settings.get("notification_min_score", "70"))`. The `.get(...)`
default only applies when the **key is absent**; if the key is present with a malformed value
(empty string, `"none"`, partial write), `float()`/`int()` raises `ValueError`. Because the render
body is wrapped in the gate's `except Exception: pass`, the page silently fails to render rather than
showing a usable error. Same unguarded-conversion pattern as WR-02.

**Fix:** Add a small safe-coerce helper and use it for all five conversions, e.g.:
```python
def _to_float(s, default):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default
peso_puesto = st.number_input(..., value=_to_float(settings.get("score_weight_puesto"), 0.35), ...)
```

### WR-04: `build_effective_profile` raises if persisted weights don't sum to 1.0 — uncaught in worker/Run-now path

**File:** `app/profile_overlay.py:51-56`, cross-referenced with `app/pipeline.py:167` and
`ui/services.py:83`
**Issue:** The overlay constructs `PesosScoring(...)` from the four `score_weight_*` settings, and
`PesosScoring.check_sum` (`schemas.py:78-83`) raises `ValueError` if they don't sum to 1.0 within
1e-6. The Settings page validates *before* saving (good), but legacy/partial data — or a manual DB
edit, or weights saved by an older build — can leave a non-summing set. When that happens:
- **Run now path:** `run_pipeline` calls `build_effective_profile` at line 167 with no try/except
  around it. The `ValueError` propagates out of `run_pipeline`, is caught by
  `_run_pipeline_thread`'s broad `except` (services.py:86), and lands in `_RUN_STATUS["error"]` — so
  the UI does surface it (acceptable).
- **Re-score path:** same — caught nowhere special but surfaced via the `st.spinner` block raising;
  `rescore_stored` calls it at line 344 with no guard, so the exception propagates into the page
  render and is swallowed by the gate's `except Exception: pass`, leaving the user with a dead
  "Re-puntuando…" spinner and no error.

The docstring (line 42-44) claims this "surfaces early" as a mitigation, but in the Re-score path it
surfaces as a silently-swallowed crash, not a user-visible error.

**Fix:** Wrap the `rescore_stored(...)` call in `results.py:113-117` in try/except and surface the
error via `st.error(...)`, and/or have `build_effective_profile` fall back to `base.pesos` (the
profile.yaml weights, already known valid) with a logged warning when the DB weights fail
validation, instead of raising:
```python
try:
    new_pesos = PesosScoring(puesto=..., skills=..., ubicacion=..., seniority=...)
except ValidationError:
    logger.warning("Persisted score_weight_* do not sum to 1.0 — falling back to profile.yaml pesos")
    new_pesos = base.pesos
```

### WR-05: Re-score "done" toast cleared before the user can see it (and result lost from Results refresh)

**File:** `ui/pages/results.py:74-76`
**Issue:** In `_poll()`, the `done` branch shows `st.success(msg)` and then immediately sets
`_RUN_STATUS["result"] = None` followed by `st.rerun()`. The rerun happens in the same tick, so the
success message ("Run completado — N nuevas ofertas puntuadas") is wiped before it is meaningfully
visible, and the count `r.scored` from the completed run is discarded. The user gets at most a
flicker. Combined with the fact that the result carries the only in-memory summary of what the run
produced, this throws away useful feedback.

**Fix:** Don't `st.rerun()` immediately after clearing; let the success render persist for at least
one full script run, or stash the completed summary into `st.session_state` before clearing
`_RUN_STATUS["result"]` so the headline survives the rerun.

### WR-06: `int(min_score)` / weight inputs trust the slider/number widget but history filter uses raw `score_total >= min_score`

**File:** `ui/results_logic.py:31` cross-referenced with `app/storage/sqlite.py:196-208`
**Issue:** `filter_history` compares `r["score_total"] >= min_score`. `score_total` comes from
`get_history`, where it is read straight from the DB column (`row["score_total"]`) without coercion;
the column is declared `INTEGER` but SQLite's dynamic typing does not guarantee it. If any stored row
has a NULL or non-int `score_total` (e.g. a row written by a path that didn't set it, or future
schema drift), the `>=` comparison against the Python int `min_score` raises `TypeError` and the
Results page crashes for the *whole* history, not just the bad row. `get_undelivered_qualifying`
already hardens `min_score` defensively at the storage boundary (line 238-244) — `get_history`
should be equally defensive about the row value it returns.

**Fix:** In `get_history`, coerce defensively (e.g. `"score_total": row["score_total"] if isinstance(row["score_total"], int) else 0`), or in `filter_history` skip rows whose `score_total` is not an int. Prefer hardening at the storage boundary for consistency with the existing pattern.

### WR-07: `rescore_stored` reconstructs `Job` with `description=""`, neutralizing `encaje_skills` for every job

**File:** `app/pipeline.py:355-365`
**Issue:** This is documented (D-09 limitation) but worth flagging as a correctness caveat the UI
underplays. Re-scored jobs always get `description=""`, so the skills sub-score is neutral (~50) for
*every* job on re-score. A user adjusts weights, hits Re-score to see the effect, and the
`encaje_skills` axis is effectively frozen at 50 — meaning the very axis most tied to "match against
my real CV" is the one re-score cannot recompute. The Results warning mentions it, but the re-scored
rows then *overwrite* the original (correctly-scored) `score_json` via `upsert_scored_jobs`
(line 373), so re-scoring **destroys** the better original skills scores and replaces them with
neutral 50s. This is a data-quality regression triggered by a UI button.

**Fix:** Either persist `description` in the jobs table so re-score can recompute skills properly, or
make re-score preserve the original `encaje_skills` (merge: keep stored `encaje_skills`, recompute
the deterministic axes) rather than clobbering it with a neutral value. At minimum, the cost-warning
copy should state that re-score will *overwrite and degrade* existing skill scores, not just that the
new ones are neutral.

## Info

### IN-01: Module-level `_RUN_STATUS` is process-global, not session-scoped

**File:** `ui/services.py:64-70`
**Issue:** Documented as an intentional single-user assumption (A2). Correct for this personal tool,
but worth noting: if the app is ever served to more than one concurrent browser session, one user's
Run now state and results leak into the other's UI. Acceptable for v2.0 scope; flagging so it isn't
forgotten if the tool is ever exposed multi-user.
**Fix:** No action needed now; if multi-user, move to `st.session_state` or key the status dict by
session id.

### IN-02: `_get_cv_profile` picks "most recent by mtime" cache file — silent ambiguity with multiple CVs

**File:** `app/pipeline.py:84-97`
**Issue:** When several CV caches exist in `data/.cache`, the pipeline silently uses whichever JSON
has the newest mtime. If the user uploaded two CVs, scoring uses the most recently *written* one,
which may not be the one they think is active. No user-visible indication of which CV is in use.
**Fix:** Consider surfacing the active CV (filename/hash) on the CV page or Status page, or store an
explicit "active CV hash" setting rather than relying on mtime.

### IN-03: Status page renders raw ISO timestamps in `st.metric`

**File:** `ui/pages/status.py:79,81-82`
**Issue:** `st.metric("Último run", s["last_run"])` shows the full ISO-8601 string
(`2026-05-25T...+00:00`) which is long and not localized. Cosmetic only.
**Fix:** Format with `datetime.fromisoformat(...).strftime("%Y-%m-%d %H:%M")` for readability;
guard the parse.

### IN-04: Broad `except Exception: pass` in every page gate hides real import/render errors

**File:** `ui/pages/search.py:133-135`, `ui/pages/results.py:225-227`, `ui/pages/settings.py:151-153`,
`ui/pages/status.py:112-114`
**Issue:** The `streamlit.runtime.exists()` gate is wrapped in `except Exception: pass` so the module
imports cleanly under pytest. But this also swallows genuine errors raised *during `_render()`* when
running live (e.g. WR-02/WR-03 crashes), leaving the page blank with no traceback and no user-facing
error. The intent (import-safety) only needs to catch the ImportError from `streamlit.runtime`, not
everything `_render()` can throw.
**Fix:** Narrow the gate so only the import/`exists()` check is guarded, and let `_render()`
exceptions propagate to Streamlit's normal error UI:
```python
try:
    from streamlit.runtime import exists as _st_running
    _running = _st_running()
except Exception:
    _running = False
if _running:
    _render()
```

### IN-05: `run_status_label` "done" depends on `result is not None` but result is cleared by the page, coupling logic to UI side-effects

**File:** `ui/results_logic.py:83-85` cross-referenced with `ui/pages/results.py:75`
**Issue:** The "done" state is inferred purely from `result is not None`. The page clears `result`
right after rendering, so the pure helper's notion of "done" is silently driven by a UI side-effect
elsewhere. This makes `run_status_label` harder to reason about/test in isolation (its output for a
given dict depends on whether the page already ran). Minor design smell.
**Fix:** Consider an explicit `"done"` flag in `_RUN_STATUS` set by the thread, decoupling
"completed" from "result still present."

---

_Reviewed: 2026-05-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
