---
phase: 10-streamlit-ui
plan: "06"
subsystem: ui
tags: [streamlit, settings, status, weight-validation, deal-breakers, scheduler-dashboard]
dependency_graph:
  requires: [10-03, app/models/schemas.py, app/status_helpers.py, app/storage/sqlite.py]
  provides: [ui/pages/settings.py, ui/pages/status.py, ui/settings_logic.py]
  affects: [ui/app.py navigation, profile_overlay weights, worker deal_breakers, notification threshold]
tech_stack:
  added: []
  patterns:
    - D-12 streamlit.runtime.exists() import guard (all 3 new files)
    - TDD RED/GREEN for Task 1 (settings_logic) and Task 3 (status)
    - Pure helper extraction: settings_logic.py + summarize_status() (testable without Streamlit)
    - PesosScoring validator as gate before set_setting() (T-10-06-02)
    - channel_status() returns booleans only — never secret strings (T-10-06-01)
    - Deferred import of compute_next_run inside summarize_status (avoids top-level cycles)
key_files:
  created:
    - ui/settings_logic.py
    - ui/pages/settings.py
    - ui/pages/status.py
    - tests/ui/test_settings_page.py
    - tests/ui/test_status_page.py
  modified: []
decisions:
  - "settings_logic.py has zero Streamlit imports — pure Python for full testability"
  - "str(0.30) == '0.3' in Python; test assertions use float() comparison not string equality"
  - "summarize_status defaults new_seen/notified to 0 (or 0 fallback) when keys absent from run row"
  - "pack_deal_breakers strips whitespace + drops blank entries before JSON encoding"
  - "channel_status() uses bool(os.getenv(...)) — the env var is read only to compute presence, never returned"
metrics:
  duration: 254s
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_created: 5
  tests_added: 17
---

# Phase 10 Plan 06: Settings + Status Pages Summary

Settings page (UI-05/UI-06) and Status page (UI-09) with PesosScoring weight validation,
deal-breakers JSON persistence, boolean-only channel display, and compute_next_run scheduler dashboard.

## What Was Built

**ui/settings_logic.py** — pure Python helpers (no Streamlit):
- `validate_and_pack_weights(puesto, skills, ubicacion, seniority)` — constructs PesosScoring to
  run the sum-to-1.0 validator; returns `(True, {score_weight_* keys})` on success or
  `(False, "Los pesos deben sumar 1.0 (suman X).")` on failure. Zero exception leaks.
- `pack_deal_breakers(items)` — JSON-encodes list, strips whitespace, drops blank entries.
- `channel_status()` — returns `{telegram: bool, email: bool, openai: bool}` from env-var
  presence. Never returns secret values (T-10-06-01).

**ui/pages/settings.py** — Settings page (UI-05 + UI-06):
- 4 number inputs for scoring weights (puesto/skills/ubicación/seniority), pre-filled from settings table.
- "Guardar pesos" calls `validate_and_pack_weights` — bad weights show `st.error(msg)` and block;
  good weights upsert all 4 `score_weight_*` settings.
- Threshold number input → `notification_min_score` setting.
- Deal-breakers text area (one per line) → `pack_deal_breakers()` → `deal_breakers` JSON setting.
- Channel status displayed as ✓/✗ only via `channel_status()` — no secret values rendered.
- Import guard: `streamlit.runtime.exists()` gate (D-12).

**ui/pages/status.py** — Status page (UI-09):
- `summarize_status(runs, settings)` — pure helper: extracts `last_run`, `next_run` (via
  `compute_next_run`), `new_seen`, `notified` from the runs list and settings dict.
- Page renders 4 `st.metric` columns + a `st.dataframe` of recent runs (read-only).
- Empty state: `st.info("El worker aún no ha ejecutado ningún run.")`.
- Import guard: `streamlit.runtime.exists()` gate (D-12).

## TDD Gate Compliance

| Task | RED commit | GREEN commit | Status |
|------|-----------|--------------|--------|
| Task 1 (settings_logic) | 9f86d49 | 0d9ece1 | PASS |
| Task 3 (status page) | 813770d | 8198ce7 | PASS |

## Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| Full suite | 319 passed | 336 passed | +17 |
| test_settings_page.py | — | 11 passed | +11 |
| test_status_page.py | — | 6 passed | +6 |

## Commits

| Hash | Message |
|------|---------|
| 9f86d49 | test(10-06): add failing tests for settings_logic (Task 1 RED) |
| 0d9ece1 | feat(10-06): implement ui/settings_logic.py + fix test assertions (Task 1 GREEN) |
| 7caae21 | feat(10-06): create ui/pages/settings.py (UI-05 + UI-06) |
| 813770d | test(10-06): add failing tests for summarize_status (Task 3 RED) |
| 8198ce7 | feat(10-06): create ui/pages/status.py + summarize_status helper (Task 3 GREEN) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Float string representation mismatch in test assertion**
- **Found during:** Task 1 GREEN
- **Issue:** Test asserted `payload["score_weight_skills"] == "0.30"` but `str(0.30)` in Python is `"0.3"` (not `"0.30"`). The test was written with the plan's code example verbatim, but Python's float-to-str conversion drops trailing zeros.
- **Fix:** Updated test assertions to use `float(payload[key]) == pytest.approx(value)` instead of string equality. This is more robust and correctly tests the round-trip.
- **Files modified:** `tests/ui/test_settings_page.py`
- **Commit:** 0d9ece1

## Known Stubs

None. Both pages read real data from `get_storage()` and call real helpers (`compute_next_run`, `validate_and_pack_weights`, `channel_status`).

## Threat Flags

All threats in the plan's threat model were mitigated:
- T-10-06-01 (secret disclosure): `channel_status()` returns bools; page never reads env vars directly. Verified by grep acceptance criterion.
- T-10-06-02 (invalid weights persisted): `validate_and_pack_weights()` constructs `PesosScoring` before any `set_setting()`. Bad weights block with a clear error.
- T-10-06-03 (malformed deal_breakers): `pack_deal_breakers()` always emits valid JSON.
- T-10-06-04 (non-numeric threshold): `st.number_input` (numeric widget) + `str()` coercion.

No new threat surface introduced beyond what the plan's threat model covers.

## Self-Check: PASSED

- [x] `ui/settings_logic.py` exists with `validate_and_pack_weights`, `pack_deal_breakers`, `channel_status`
- [x] `ui/pages/settings.py` exists — AST parses, delegates to settings_logic helpers
- [x] `ui/pages/status.py` exists — AST parses, `summarize_status` importable
- [x] Commits 9f86d49, 0d9ece1, 7caae21, 813770d, 8198ce7 all present
- [x] 336 tests pass, 319 baseline preserved
