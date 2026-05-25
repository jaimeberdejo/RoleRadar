---
phase: 10-streamlit-ui
plan: "05"
subsystem: ui
tags: [streamlit, results-page, filtering, scoring, run-now, rescore]
dependency_graph:
  requires: [10-03, 08-04]
  provides: [UI-03, UI-04, UI-07, UI-08]
  affects: [ui/app.py]
tech_stack:
  added: []
  patterns:
    - st.dataframe on_select="rerun" + selection_mode="single-row" for row selection
    - "@st.fragment(run_every=...) dynamic polling — 2s while running, None when idle"
    - Pure logic module (ui/results_logic.py) extracted for unit testing
    - Page-render gated by streamlit.runtime.exists() (D-12 pattern)
key_files:
  created:
    - ui/results_logic.py
    - ui/pages/results.py
    - tests/ui/test_results_logic.py
  modified: []
decisions:
  - "filter_history and build_results_df extracted to ui/results_logic.py (pure, no st.*) for testability"
  - "run_every dynamic: '2s' while running, None when idle — self-stopping fragment (Pitfall 1)"
  - "Re-score confirmation uses st.session_state['_rescore_confirm'] flag + two buttons (confirm/cancel)"
  - "OPENAI_API_KEY shown as bool(os.getenv(...)) — value never rendered (T-10-05-01)"
  - "url accessed via row.get('url') — absent URL skipped silently (T-10-05-04)"
metrics:
  duration: 169s
  completed_date: "2026-05-25"
  tasks_completed: 2
  files_changed: 3
---

# Phase 10 Plan 05: Results Page Summary

Results page delivers all four highest-value UI requirements: sortable/filterable scored-offer list (UI-03), full score breakdown with apply URL on row select (UI-04), non-blocking Run now via shared thread launcher with live status polling (UI-07/SC4), and cost-warned Re-score of stored jobs with no re-fetch (UI-08).

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| 1 | ui/results_logic.py + tests (pure filter/df/status helpers) | a858c71 | Done |
| 2 | ui/pages/results.py — list + detail + Run now + Re-score | 58d46db | Done |

(TDD RED commit: 1abd5f4 — failing tests committed before implementation)

## Key Files

**Created:**
- `/Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/ui/results_logic.py` — pure helpers: `filter_history`, `build_results_df`, `run_status_label`
- `/Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/ui/pages/results.py` — Results page (UI-03/04/07/08)
- `/Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/tests/ui/test_results_logic.py` — 11 unit tests

## Test Results

- Pre-existing: 308 tests GREEN (unchanged)
- New: 11 tests for results_logic helpers GREEN
- Total: **319 tests GREEN**

## Deviations from Plan

None — plan executed exactly as written.

### TDD Gate Compliance

- RED commit: `test(10-05): add failing tests for results_logic pure helpers` (1abd5f4) — all 11 tests failed with ModuleNotFoundError as expected
- GREEN commit: `feat(10-05): implement results_logic pure helpers` (a858c71) — all 11 tests pass

## Threat Flags

No new security-relevant surface beyond what the plan's threat model covers. All five T-10-05-* mitigations applied as specified.

## Known Stubs

None — all display data comes from `storage.get_history()` real storage. Score breakdown fields use `.get()` with fallback to `"—"` for robustness against old schema rows, which is intentional and correct (not a stub).

## Self-Check: PASSED

Files exist:
- `ui/results_logic.py` — FOUND
- `ui/pages/results.py` — FOUND
- `tests/ui/test_results_logic.py` — FOUND

Commits exist:
- 1abd5f4 (RED tests) — FOUND
- a858c71 (GREEN impl) — FOUND
- 58d46db (results.py) — FOUND
