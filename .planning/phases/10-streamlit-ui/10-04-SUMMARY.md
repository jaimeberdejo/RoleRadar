---
phase: 10-streamlit-ui
plan: "04"
subsystem: ui
tags: [streamlit, cv, cache-first, search-config, settings, tdd]
dependency_graph:
  requires: [10-03]
  provides: [UI-01, UI-02]
  affects: [ui/pages/cv.py, ui/pages/search.py, ui/cv_logic.py]
tech_stack:
  added: []
  patterns:
    - cache-first CV resolution extracted into pure-Python helper (ui/cv_logic.py)
    - streamlit.runtime.exists() gate for import-safe page modules under pytest
    - TDD RED/GREEN cycle for both tasks
key_files:
  created:
    - ui/cv_logic.py
    - ui/pages/cv.py
    - ui/pages/search.py
    - tests/ui/test_cv_page.py
    - tests/ui/test_search_page.py
    - ui/pages/__init__.py
  modified: []
decisions:
  - "resolve_cv_profile in ui/cv_logic.py: pure Python, no Streamlit import — testable without runtime"
  - "Page render body of search.py wrapped in _render() and gated with streamlit.runtime.exists() so the helper save_search_settings is importable by pytest"
  - "remote_only persisted as 'true'/'false' string per T-10-04-03; date_posted constrained to selectbox"
  - "cv.py uses st.spinner for both cache-hit and cache-miss paths, then branches UI on was_cached flag"
metrics:
  duration: "~12 min"
  completed: "2026-05-25"
  tasks: 3
  files: 6
---

# Phase 10 Plan 04: CV Page + Search Config Page Summary

**One-liner:** Cache-first CV upload page (sha256 → load_cached_profile → no-reparse on hit) and persistent Search Config page (set_setting round-trip), both with unit-tested pure-Python helpers and 308 tests green.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for cv cache-first resolve_cv_profile | 0ec2b4f | tests/ui/test_cv_page.py |
| 1 (GREEN) | ui/cv_logic.py resolve_cv_profile implementation | 39ea41e | ui/cv_logic.py |
| 2 | Thin CV upload page ui/pages/cv.py (UI-01) | 0075114 | ui/pages/cv.py, ui/pages/__init__.py |
| 3 (RED) | Failing tests for search settings persistence | ee8d2ac | tests/ui/test_search_page.py |
| 3 (GREEN) | Search Config page ui/pages/search.py (UI-02) | a965b85 | ui/pages/search.py |

## Success Criteria Verification

- [x] ui/pages/cv.py + ui/pages/search.py created (+ ui/cv_logic.py extracted helper)
- [x] CV cache-hit path renders WITHOUT calling parse_cv (test_cache_hit_skips_parse asserts parse_cv.assert_not_called())
- [x] Search params persist via set_setting and load current values on render
- [x] This plan's tests (tests/ui/test_cv_page.py, test_search_page.py) GREEN — 4 tests
- [x] Pre-existing 304 tests still PASS (308 total = 304 + 4 new)
- [x] Each task committed individually

## TDD Gate Compliance

Plan executed with full TDD RED/GREEN cycle for Tasks 1 and 3:

- Task 1 RED: commit 0ec2b4f (test(10-04)) — tests fail with AttributeError (module not found)
- Task 1 GREEN: commit 39ea41e (feat(10-04)) — 2 tests pass
- Task 3 RED: commit ee8d2ac (test(10-04)) — tests fail with ModuleNotFoundError
- Task 3 GREEN: commit a965b85 (feat(10-04)) — 2 tests pass

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. Both pages are fully functional:
- cv.py: renders CVProfile fields from a real resolved profile
- search.py: persists and pre-fills real settings from the settings table

## Threat Surface Scan

No new security-relevant surface introduced beyond what the threat model documented:
- T-10-04-01 (path traversal via cache): mitigated — pdf_hash() produces sha256 hex; ui/pages/cv.py never names cache files directly
- T-10-04-02 (non-PDF upload): mitigated — type=["pdf"] on st.file_uploader in cv.py
- T-10-04-03 (malformed search settings): mitigated — date_posted constrained by selectbox; remote_only serialized deterministically

## Self-Check: PASSED

Files created:
- ui/cv_logic.py: EXISTS
- ui/pages/cv.py: EXISTS
- ui/pages/search.py: EXISTS
- tests/ui/test_cv_page.py: EXISTS
- tests/ui/test_search_page.py: EXISTS

Commits:
- 0ec2b4f: EXISTS
- 39ea41e: EXISTS
- 0075114: EXISTS
- ee8d2ac: EXISTS
- a965b85: EXISTS

Test results: 308 passed, 0 failed.
