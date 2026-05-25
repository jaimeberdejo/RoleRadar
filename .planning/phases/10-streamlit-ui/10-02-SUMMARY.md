---
phase: 10-streamlit-ui
plan: "02"
subsystem: core-helpers
tags: [profile-overlay, rescore, status-helpers, storage, pipeline]
dependency_graph:
  requires: [10-01]
  provides: [app/profile_overlay.py, app/status_helpers.py, rescore_stored, get_history-remote, deal_breakers-default]
  affects: [10-03, 10-04, 10-05, 10-06]
tech_stack:
  added: []
  patterns: [pydantic-model_copy-overlay, deferred-import-pattern, per-job-error-isolation]
key_files:
  created:
    - app/profile_overlay.py
    - app/status_helpers.py
  modified:
    - app/storage/sqlite.py
    - app/pipeline.py
decisions:
  - "build_effective_profile uses model_copy(update=...) — minimal Pydantic v2 overlay; identity fields untouched"
  - "rescore_stored placed as sibling in pipeline.py — same import surface, no new module"
  - "get_history adds remote+url; existing keys unchanged — zero storage regression"
  - "deal_breakers default is '[]' (empty JSON list) — parses cleanly, never breaks overlay"
  - "run_pipeline fetches settings BEFORE profile load so overlay can apply them"
metrics:
  duration: "187s (~3 min)"
  completed_date: "2026-05-25"
  tasks: 3
  files: 4
---

# Phase 10 Plan 02: Core Helpers — Profile Overlay + Rescore + Status Summary

**One-liner:** Import-clean overlay helper (`build_effective_profile`) wiring UI settings into run_pipeline + rescore_stored, plus get_history remote/url fix, deal_breakers default seeding, and compute_next_run status helper.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | build_effective_profile + compute_next_run | fbd556b | app/profile_overlay.py, app/status_helpers.py |
| 2 | Fix get_history remote field + seed deal_breakers | f8fbd8d | app/storage/sqlite.py |
| 3 | rescore_stored() + run_pipeline uses effective profile | 39e7bc3 | app/pipeline.py |

## What Was Built

### app/profile_overlay.py — `build_effective_profile(settings, profile_path) -> UserProfile`
The central seam of Phase 10 (D-07). Overlays settings-table score weights and deal_breakers JSON onto the base profile.yaml identity (ranking_puestos, datos_personales, preferencias_* unchanged). PesosScoring's sum-to-1.0 validator fires at overlay construction time, surfacing bad weights early (T-10-02-02). Bad JSON deal_breakers fall back to profile.yaml value (T-10-02-01).

### app/status_helpers.py — `compute_next_run(runs, interval) -> datetime | None`
Pure Python, no external deps. Returns `runs[0]["started_at"] + timedelta(hours=interval)` or None on empty/missing/bad timestamp. Fully unit-testable without Streamlit.

### app/storage/sqlite.py — get_history + init_db
- `get_history` now returns `"remote"` and `"url"` keys alongside existing keys. `remote` is needed to reconstruct Job objects in rescore_stored; `url` is needed for the apply link in the Results UI (D-10 / UI-04).
- `_SETTING_DEFAULTS` now seeds `"deal_breakers": "[]"` via `INSERT OR IGNORE` — never clobbers an existing user value on upgrade (Pitfall 5 / UI-06).

### app/pipeline.py — run_pipeline + rescore_stored
- **run_pipeline**: settings now fetched before profile load; `load_user_profile` replaced with `build_effective_profile(settings, profile_path)` so the scheduled worker honors UI-edited weights and deal-breakers (D-07).
- **rescore_stored**: new sibling function. Reads stored jobs via `get_history`, reconstructs minimal `Job` objects (with `RemoteJob.unknown` fallback for None remote — T-10-02-03), re-runs `score_job` with the effective profile and injected embedder, upserts results. Does NOT call `_fetch_all` and does NOT call `record_run` (re-score is not a fetch run). Per-job error isolation via try/except.

## Verification Results

```
301 passed, 5 warnings in 11.39s
```

- Wave 0 RED guards: 15 tests → all GREEN
- Pre-existing suite: 286 tests → all GREEN (zero regression)
- Import-clean: `python -c "import app.pipeline, app.profile_overlay, app.status_helpers; assert 'streamlit' not in sys.modules"` passes

## Deviations from Plan

None — plan executed exactly as written. The step-number renumbering in run_pipeline's comment blocks (steps 2/3/4 resequenced as the settings fetch moved above profile load) is cosmetic-only.

## Known Stubs

None. All implementations are fully wired.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes beyond those already documented in the plan's threat model (T-10-02-01 through T-10-02-04).

## Self-Check: PASSED
