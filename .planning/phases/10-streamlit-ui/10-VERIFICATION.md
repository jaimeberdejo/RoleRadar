---
phase: 10-streamlit-ui
verified: 2026-05-25T12:00:00Z
status: human_needed
score: 7/7
overrides_applied: 0
human_verification:
  - test: "CV page: upload a real PDF, confirm CVProfile renders (skills, experience, education). Then re-upload the same PDF and confirm it shows 'Perfil cargado de caché (mismo PDF, no se re-parsea).' without calling the LLM again."
    expected: "First upload triggers parse; second upload shows cache-hit caption immediately with no spinner delay. Score breakdown fields are populated from the actual CV content."
    why_human: "Cache-hit path and live PDF rendering require an active Streamlit runtime with a real or fixture PDF; the parse_cv LLM call is mocked in unit tests but the end-to-end browser flow is visual."
  - test: "Results page: click 'Run now', observe the live status indicator (spinner/status widget) while the run is in progress. Confirm the UI does not freeze and that the button becomes disabled. After the run completes, confirm the results table refreshes."
    expected: "Button disables immediately, status fragment shows 'running…', UI remains interactive (can switch pages), on completion the success headline appears and results update."
    why_human: "Non-freeze feel and background-thread lifecycle are runtime behaviors; only detectable in the browser."
  - test: "Results page: expand a scored offer row and confirm the detail panel shows all four sub-scores (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority), reasons_for/against, matched/missing skills, and a working apply URL link."
    expected: "All four metric columns are populated; reasons/skills sections appear when present; the 'Ver oferta' link button opens the job URL."
    why_human: "Row-selection expand flow and visual completeness of the breakdown panel require a browser."
  - test: "Settings page: enter scoring weights that do NOT sum to 1.0 (e.g. 0.40 + 0.30 + 0.20 + 0.20 = 1.10) and click 'Guardar pesos'. Confirm a Spanish error message blocks the save."
    expected: "st.error shows 'Los pesos deben sumar 1.0 (suman 1.1).' No set_setting call is made."
    why_human: "The validation feedback is a visual UI element; functionally covered by test_settings_page.py but the browser appearance needs human confirmation."
---

# Phase 10: Streamlit UI Verification Report

**Phase Goal:** Jaime can run the entire tool from a browser tab: upload his CV, configure search parameters and scoring weights, browse and filter all scored offers with full score breakdowns, trigger an immediate run, and inspect the scheduler status — with all settings persisted so the worker respects them.

**Verified:** 2026-05-25T12:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | CV page parses+displays CVProfile; reload doesn't re-parse same file | VERIFIED | `ui/cv_logic.py::resolve_cv_profile` implements sha256-keyed cache-first flow; `ui/pages/cv.py` shows 'Perfil cargado de caché' caption on hit; `tests/ui/test_cv_page.py` (2 tests, all pass) assert cache-hit path skips `parse_cv` |
| SC2 | Saving search params causes next worker run to use them — no Docker restart | VERIFIED | **CR-01 fix verified in code:** `pipeline.py:247-248` builds queries from `settings["search_query"]` when non-empty, else falls back to `ranking_puestos`; `pipeline.py:238` respects saved `date_posted` on non-first-run; `jsearch.py:156-158` plumbs `search_language`, `employment_types`, `remote_only` into fetch params. Three dedicated regression tests (`test_run_pipeline_uses_saved_search_query`, `test_run_pipeline_falls_back_to_ranking_when_no_search_query`, `test_run_pipeline_respects_saved_date_posted_when_not_first_run`) all PASS. JSearch tests (`test_fetch_all_queries_cr01_settings_forwarded`) assert `language`, `employment_types`, `remote_jobs_only` reach the HTTP request params. |
| SC3 | Results page lists all scored offers sortable+filterable; row expand shows full breakdown | VERIFIED | `ui/pages/results.py` uses `st.dataframe(on_select="rerun", selection_mode="single-row")` with filter widgets (score slider + recommendation multiselect); expand section renders all 4 sub-scores via `st.columns(4)` + `st.metric`, plus reasons/skills. `tests/ui/test_results_logic.py` (11 tests) cover `filter_history` and `build_results_df`. Visual confirmation needed (human item 3). |
| SC4 | "Run now" triggers pipeline in non-blocking background thread; live status; no freeze; refreshes on completion | VERIFIED (automated layer) | `ui/services.py::start_run` spawns a daemon thread with double-run guard under `_RUN_LOCK`; thread body calls `run_pipeline` and never calls `st.*`; `@st.fragment(run_every="2s")` polling pattern in `results.py:76-95`; WR-01 fix: `_svc.clear_run_result()` / `_svc.clear_run_error()` route clears through lock. `test_run_status_completes` asserts thread sets `running=False` + `result` on completion. No-freeze feel requires human browser test (human item 2). |
| SC5 | Settings weights/deal-breakers persist to settings table; Re-score applies new weights without re-fetching; WR-07: rescore preserves original encaje_skills | VERIFIED | `ui/pages/settings.py` calls `validate_and_pack_weights` before any `set_setting`; deal-breakers saved as JSON via `pack_deal_breakers`. `build_effective_profile` overlay used by `run_pipeline` (pipeline.py:230), `rescore_stored` (pipeline.py:420), and `start_run` (via run_pipeline). **WR-07 fix:** `pipeline.py::_merge_preserving_skills` preserves stored `encaje_skills` and recomputes `score_total` from merged sub-scores; `test_rescore_preserves_original_encaje_skills` asserts the stored value (75) is preserved post-rescore (PASS). |
| SC6 | Scheduler status panel shows last run, next run, new-offers count from runs table | VERIFIED | `ui/pages/status.py::summarize_status` reads `get_recent_runs()` and calls `compute_next_run(runs, interval_hours)` from `app/status_helpers.py`; renders `st.metric` for last_run, next_run, new_seen, notified. IN-03 addressed: `_format_ts()` formats ISO timestamps as "YYYY-MM-DD HH:MM". `tests/ui/test_status_page.py` (10 tests, all pass). |
| SC7 | BGE-M3 model never reloaded on interaction — @st.cache_resource one instance/process | VERIFIED | `ui/services.py::get_embedder` decorated `@st.cache_resource`; injected into `run_pipeline(embedder=...)` and `rescore_stored(embedder=...)` at all call sites. `test_embedder_singleton` asserts `get_embedder() is get_embedder()` (same object; PASS). |

**Score:** 7/7 truths verified (automated layer)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/profile_overlay.py` | `build_effective_profile(settings, profile_path) -> UserProfile` | VERIFIED | 91 lines; overlays pesos + deal_breakers; WR-04 fallback on invalid weights; import-clean (no streamlit) |
| `app/status_helpers.py` | `compute_next_run(runs, interval_hours) -> datetime\|None` | VERIFIED | 46 lines; pure Python; handles empty/malformed timestamps |
| `app/pipeline.py` | `run_pipeline` + `rescore_stored` + CR-01 fix | VERIFIED | 478 lines; `rescore_stored` at line 371; CR-01 query-building at lines 247-248; date_posted at line 238; `_merge_preserving_skills` WR-07 fix |
| `app/storage/sqlite.py` | `get_history` with remote field + deal_breakers default | VERIFIED | `get_history` dict includes `"remote": row["remote"]` (line 201); `_SETTING_DEFAULTS` includes `"deal_breakers": "[]"` (line 122); WR-06 defensive score_total coercion |
| `app/sources/jsearch.py` | `employment_types`/`remote_only`/`language` plumbed into request params | VERIFIED | Lines 74-80 add `language`, `employment_types`, `remote_jobs_only` to params when set; `fetch_all_queries` reads `search_language`, `employment_types`, `remote_only` from settings |
| `ui/app.py` | 5-page navigation via `st.navigation` + `set_page_config` first | VERIFIED | 14 lines; `set_page_config` is line 5 (first Streamlit call); `st.navigation([cv, search, results, settings, status])` |
| `ui/services.py` | `get_embedder` (@st.cache_resource), `start_run`, `_RUN_STATUS`, WR-01 lock helpers | VERIFIED | 135 lines; `clear_run_result()` and `clear_run_error()` added (WR-01); all `_RUN_STATUS` mutations under `_RUN_LOCK` |
| `ui/cv_logic.py` | `resolve_cv_profile(pdf_bytes) -> (CVProfile, was_cached)` | VERIFIED | 45 lines; cache-first: `pdf_hash → load_cached_profile → parse_cv + save_cached_profile` |
| `ui/pages/cv.py` | CV upload page with cache-hit caption | VERIFIED | Renders `_render_cv_profile`; shows 'Perfil cargado de caché' on hit |
| `ui/pages/search.py` | Search Config page persisting all 6 settings via `set_setting` | VERIFIED | `save_search_settings` persists `search_query`, `search_country`, `search_language`, `date_posted`, `employment_types`, `remote_only` |
| `ui/pages/results.py` | Results list + detail + Run now + Re-score (all 4 sub-scores in detail) | VERIFIED | `st.dataframe(on_select="rerun")`; expand shows 4 `st.metric` for sub-scores + reasons + skills; WR-01/WR-04/WR-05 fixes applied |
| `ui/pages/settings.py` | Weights+threshold (UI-05) + deal-breakers (UI-06) + boolean secrets | VERIFIED | WR-02/WR-03 guards (`_to_float`, `_to_int`, `try/except json.loads`); channel_status() renders boolean only via `settings_logic.channel_status()` |
| `ui/pages/status.py` | Scheduler status panel from `get_recent_runs` + `compute_next_run` | VERIFIED | `summarize_status` calls `compute_next_run`; IN-03 fix: `_format_ts()` formats timestamps |
| `ui/results_logic.py` | `filter_history` + `build_results_df` + `run_status_label` | VERIFIED | Pure helpers; 11 tests pass |
| `ui/settings_logic.py` | `validate_and_pack_weights` + `pack_deal_breakers` + `channel_status` | VERIFIED | PesosScoring validation before save; booleans-only channel_status |
| `README.md` | v2.0 standalone: `docker compose up` (ui+worker), no active FastAPI/n8n quick-start | VERIFIED | FastAPI/n8n only in "Legado" section (lines 374-382); all active docs describe Streamlit + APScheduler + docker compose |
| `docs/archive/n8n/README.md` | Legacy archive note | VERIFIED | Exists; states "n8n ya no es necesario"; links to active README |
| `tests/ui/` (11 test files, 71 tests) | All UI tests green | VERIFIED | 71 passed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `ui/services.py::get_embedder` | `app.dedup.embedder.BgeM3Embedder` | `@st.cache_resource` constructor | WIRED | Line 22-30; `test_embedder_singleton` asserts singleton |
| `ui/services.py::_run_pipeline_thread` | `app.pipeline.run_pipeline` | deferred import + call with cached embedder | WIRED | Lines 97-100; embedder injected; never calls `st.*` |
| `app/pipeline.py::run_pipeline` | `app.profile_overlay.build_effective_profile` | deferred import + call | WIRED | Lines 228-230; overlay applied before query building |
| `app/pipeline.py::rescore_stored` | `app.profile_overlay.build_effective_profile` | deferred import + call | WIRED | Lines 419-420 |
| `app/pipeline.py` (CR-01) | `settings["search_query"]` | query-list construction | WIRED | Lines 247-248; `raw_query = settings.get("search_query") or ""` |
| `app/sources/jsearch.py::fetch_all_queries` | `language`/`employment_types`/`remote_only` request params | settings dict keys | WIRED | Lines 156-158 read from settings; lines 74-80 add to params |
| `ui/pages/settings.py` | `storage.set_setting` (deal_breakers JSON, score_weight_*, notification_min_score) | save button | WIRED | Lines 116, 132, 159 |
| `ui/pages/status.py` | `app.status_helpers.compute_next_run` | deferred import + call in summarize_status | WIRED | Line 56 |
| `ui/pages/results.py` | `ui.services.start_run` + `_RUN_STATUS` | Run now button + fragment polling | WIRED | Lines 62, 77-93; uses `_svc.clear_run_result()` (WR-01) |
| `ui/pages/results.py` | `app.pipeline.rescore_stored` | Re-score button (with cost warning) | WIRED | Lines 127-144; `rescore_stored(storage=get_storage(), embedder=get_embedder())` |
| `ui/cv_logic.py::resolve_cv_profile` | `app.cv.cache` (pdf_hash/load_cached_profile/save_cached_profile) + `app.cv.parser.parse_cv` | cache-first call chain | WIRED | Lines 17-18 imports; lines 39-44 logic |
| `app/storage/sqlite.py::get_history` | `jobs.remote` column | row dict includes remote | WIRED | Line 201: `"remote": row["remote"]` |
| `app/storage/sqlite.py::init_db` | `deal_breakers` settings default | `_SETTING_DEFAULTS` + `INSERT OR IGNORE` | WIRED | Line 122; `test_deal_breakers_seeded_in_defaults` (PASS) |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `ui/pages/results.py` | `history` (list of scored offers) | `storage.get_history(limit=500)` → SQLite `jobs` table | Yes — real DB rows deserialized from `score_json` | FLOWING |
| `ui/pages/status.py` | `runs` (run history) | `storage.get_recent_runs(limit=10)` → SQLite `runs` table | Yes — real DB rows | FLOWING |
| `ui/pages/settings.py` | `settings` (current weights/deal-breakers) | `storage.get_settings()` → SQLite `settings` table | Yes — real DB rows (seeded with defaults on `init_db`) | FLOWING |
| `app/pipeline.py` | `user_profile` (effective profile) | `build_effective_profile(settings, profile_path)` → `load_user_profile(path)` + settings overlay | Yes — reads real `profile.yaml` then overlays live settings | FLOWING |
| `app/pipeline.py` | queries (for fetch) | `settings.get("search_query")` or `ranking_puestos` titles | Yes — CR-01 fix ensures saved search_query reaches fetch | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Core app modules don't import streamlit | `python -c "import app.pipeline, app.profile_overlay, app.status_helpers, app.storage.sqlite; import sys; print('FAIL' if any('streamlit' in m for m in sys.modules) else 'PASS')"` | PASS: No streamlit in sys.modules | PASS |
| 363 tests green | `python -m pytest --tb=no 2>&1 \| grep passed` | 363 passed, 5 warnings in 11.29s | PASS |
| CR-01 regression: saved search_query drives query list | `pytest tests/test_pipeline.py::test_run_pipeline_uses_saved_search_query` | 1 passed | PASS |
| CR-01 regression: saved date_posted honored on non-first-run | `pytest tests/test_pipeline.py::test_run_pipeline_respects_saved_date_posted_when_not_first_run` | 1 passed | PASS |
| CR-01 regression: jsearch plumbs language/employment_types/remote_only | `pytest tests/sources/test_jsearch.py` | 11 passed | PASS |
| WR-07 regression: rescore preserves original encaje_skills | `pytest tests/ui/test_rescore.py::test_rescore_preserves_original_encaje_skills` | 1 passed | PASS |
| WR-01: lock-guarded clear helpers | `pytest tests/ui/test_services.py::test_clear_run_result_clears_under_lock tests/ui/test_services.py::test_clear_run_error_clears_under_lock` | 2 passed | PASS |
| SC7: embedder singleton | `pytest tests/ui/test_services.py::test_embedder_singleton` | 1 passed | PASS |
| Secrets booleans only (channel_status) | `grep -n "bool(os.getenv" ui/settings_logic.py` | Returns only bool(os.getenv(...)); no secret values exposed | PASS |
| deal_breakers seeded in init_db | `pytest tests/ui/test_deal_breakers_setting.py` | 3 passed | PASS |
| get_history includes remote field | `pytest tests/ui/test_storage_remote_field.py` | 1 passed | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| UI-01 | 10-04 | CV upload → parse + cache CVProfile | SATISFIED | `ui/cv_logic.py::resolve_cv_profile`; `ui/pages/cv.py`; 2 tests |
| UI-02 | 10-04 | Search params (country, language, position, date_posted, remote-only) persisted for worker | SATISFIED | `ui/pages/search.py::save_search_settings` persists all 6 keys; pipeline consumes them (CR-01 fix) |
| UI-03 | 10-05 | Navigate all scored offers, sortable/filterable | SATISFIED | `ui/pages/results.py` + `ui/results_logic.py::filter_history + build_results_df`; 11 tests |
| UI-04 | 10-05 | Full score breakdown: 4 sub-scores + reasons + skills | SATISFIED | Results page expander shows `encaje_puesto/skills/ubicacion/seniority` via `st.metric` + reasons + skills |
| UI-05 | 10-01, 10-02, 10-06 | Scoring weights + threshold, persisted, drives worker | SATISFIED | `ui/pages/settings.py` + `validate_and_pack_weights` + `build_effective_profile` overlay in pipeline |
| UI-06 | 10-01, 10-02, 10-06 | Deal-breakers editable, persisted, drives worker | SATISFIED | deal_breakers JSON in settings table; `pack_deal_breakers`; `build_effective_profile` overlay applies them |
| UI-07 | 10-03, 10-05 | "Run now" triggers shared pipeline non-blocking | SATISFIED | `ui/services.py::start_run` + daemon thread; SC4 verified |
| UI-08 | 10-01, 10-02, 10-05 | Re-score stored without re-fetch; WR-07 preserves encaje_skills | SATISFIED | `rescore_stored` + `_merge_preserving_skills`; regression test passes |
| UI-09 | 10-01, 10-02, 10-06 | Scheduler status: last run / next run / new-offers count | SATISFIED | `ui/pages/status.py::summarize_status` + `compute_next_run`; 10 tests |
| UI-10 | 10-03 | BGE-M3 not reloaded on interaction; @st.cache_resource | SATISFIED | `get_embedder` @st.cache_resource; singleton test passes |
| DOC-04 | 10-07 | README rewritten for v2.0 standalone (Streamlit + worker) | SATISFIED | README describes `docker compose up` (ui+worker); FastAPI/n8n only in "Legado" section; n8n archived at `docs/archive/n8n/README.md` |

**All 11 Phase 10 requirements: SATISFIED**

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `ui/pages/cv.py` | all | No `streamlit.runtime.exists()` gate — page body runs at module top level | Info | cv.py uses `import streamlit as st` at the top and runs the page body unconditionally. Unlike the other 4 pages, it does not have the `try: from streamlit.runtime import exists` gate. This means importing `ui/pages/cv.py` under pytest requires a Streamlit runtime — but there are currently no tests that import cv.py directly (the tests use `ui.cv_logic` instead, which is import-clean). Not a blocker for the current test suite. |
| All 4 non-CV pages | last ~8 lines | `except Exception: pass` swallows render errors (IN-04) | Warning | The broad catch keeps tests safe but hides genuine runtime errors. The REVIEW flagged this; it was acknowledged as an intentional pattern tradeoff for this personal tool. |

No blocker anti-patterns. No hardcoded secret values found anywhere in the UI layer.

---

### Human Verification Required

#### 1. CV page cache-hit flow in browser

**Test:** Upload any PDF. Observe the `CVProfile` renders with skills, experience, education. Then upload the exact same PDF again.
**Expected:** Second upload immediately shows "Perfil cargado de caché (mismo PDF, no se re-parsea)." with no spinner delay and no LLM call.
**Why human:** End-to-end cache-hit and visual CVProfile rendering require an active Streamlit runtime with a real PDF.

#### 2. "Run now" non-blocking feel

**Test:** On the Results page, click "Run now". While the run is in progress, switch to another page (e.g. Status) and back, then return to Results.
**Expected:** The button is disabled while running; the status fragment shows a running indicator; the UI remains fully interactive; on completion the headline appears and the table refreshes.
**Why human:** Thread lifecycle, UI responsiveness, and fragment polling behavior are runtime phenomena not capturable by unit tests.

#### 3. Full score breakdown detail view

**Test:** On the Results page, click any row in the scored offers table. Expand the detail panel.
**Expected:** All four sub-scores shown as metric cards (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority); reasons_for/against appear as bullet lists when present; a "Ver oferta" link button is present for offers with a URL.
**Why human:** Row selection and visual completeness of the detail panel require a browser.

#### 4. Settings weight validation blocking save

**Test:** On the Settings page, enter weights that sum to more than 1.0 (e.g. all four at 0.30 = 1.20) and click "Guardar pesos".
**Expected:** A red Spanish error message appears ("Los pesos deben sumar 1.0 (suman 1.2)."); no settings are written to the DB.
**Why human:** Visual feedback from `st.error` requires a browser; functionally covered by `test_settings_page.py::test_validate_and_pack_weights_*` but UI appearance is not tested.

---

### Gaps Summary

No automated gaps. All seven ROADMAP success criteria are verified in code and tests:
- SC2 (CR-01): pipeline consumes all saved search settings — three regression tests pass
- SC5 (WR-07): rescore preserves original encaje_skills — dedicated regression test passes
- SC4 (WR-01): lock-discipline fixed — `clear_run_result/clear_run_error` helpers tested
- 363 tests pass, 0 failures
- app/ core never imports streamlit (spot-check and dedicated pipeline tests confirm)
- Secrets displayed as booleans only — `channel_status()` verified; no secret values reach `st.*`
- DOC-04 satisfied: README rewritten for v2.0 standalone; n8n properly archived

The four human-needed items are genuinely visual/interactive behaviors that cannot be verified programmatically: in-browser CV render, no-freeze run behavior, detail panel visual completeness, and settings error display. The automated layer is fully green; status is `human_needed` solely because of these four visual checks.

---

*Verified: 2026-05-25T12:00:00Z*
*Verifier: Claude (gsd-verifier)*
