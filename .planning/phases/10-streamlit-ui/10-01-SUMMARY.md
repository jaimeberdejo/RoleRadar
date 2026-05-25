---
phase: 10-streamlit-ui
plan: "01"
subsystem: tests
tags: [tdd, red-guards, ui, wave-0]
dependency_graph:
  requires: []
  provides:
    - tests/ui package (RED guard suite for Wave 0)
    - Contract spec for app.profile_overlay.build_effective_profile
    - Contract spec for app.status_helpers.compute_next_run
    - Contract spec for app.pipeline.rescore_stored
    - Contract spec for get_history remote field
    - Contract spec for deal_breakers setting default
  affects:
    - .planning/phases/10-streamlit-ui/10-VALIDATION.md (Per-Task Map populated)
tech_stack:
  added: []
  patterns:
    - Deferred import pattern (import inside test body) for RED-but-collectible guards
    - tmp_path + FakeEmbedder pattern (mirrors tests/test_pipeline.py)
    - yaml.dump minimal profile.yaml to tmp_path (isolated from data/profile.yaml)
key_files:
  created:
    - tests/ui/__init__.py
    - tests/ui/test_profile_overlay.py
    - tests/ui/test_status_helpers.py
    - tests/ui/test_rescore.py
    - tests/ui/test_storage_remote_field.py
    - tests/ui/test_deal_breakers_setting.py
  modified:
    - .planning/phases/10-streamlit-ui/10-VALIDATION.md
decisions:
  - Deferred import pattern: top-level import would cause collection errors; deferred import inside test body produces FAILED (not collection ERROR), satisfying both "--collect-only no error" and "tests fail for right reason"
  - _import() helper function: wraps the deferred import so the guard line is grep-able at module level in the docstring comment, and test bodies stay clean
  - tmp_path profile.yaml: tests write a minimal valid YAML rather than depending on data/profile.yaml, ensuring isolation and controlled deal_breakers/pesos values
metrics:
  duration: "390s (~6 min)"
  completed_date: "2026-05-25T17:58:56Z"
  tasks_completed: 3
  files_created: 6
  files_modified: 1
---

# Phase 10 Plan 01: Wave 0 RED Guard Tests Summary

**One-liner:** 15 RED guard tests in 5 files lock the exact contracts for build_effective_profile overlay, rescore_stored no-fetch path, compute_next_run datetime math, get_history remote field, and deal_breakers setting default.

---

## What Was Built

Created `tests/ui/` package with 5 RED guard files totalling 15 tests. Each test imports the symbol it guards (deferred, inside the test body) and asserts the precise behavioral contract that Wave 1 (Plan 02) must satisfy. All 15 tests fail for the right reasons (ImportError, KeyError, AssertionError on missing implementation); the pre-existing 286 tests still pass and the full suite still collects (301 tests, no collection errors).

### Task 1: tests/ui package + overlay + status guards (commit 2cdd93e)

**tests/ui/__init__.py** — empty package init.

**tests/ui/test_profile_overlay.py** (5 RED guards for `build_effective_profile`, D-07, UI-05, UI-06):
- `test_overlay_applies_settings_pesos` — settings weights (0.40/0.30/0.20/0.10) override profile.yaml pesos
- `test_overlay_applies_deal_breakers_from_settings` — JSON deal_breakers from settings override yaml
- `test_overlay_keeps_identity_from_yaml` — ranking_puestos and datos_personales unchanged by settings
- `test_overlay_empty_deal_breakers_setting_falls_back_to_yaml` — absent key → yaml fallback
- `test_overlay_invalid_weights_raise` — sum != 1.0 raises ValueError (PesosScoring validator)

Failure mode: `ModuleNotFoundError: No module named 'app.profile_overlay'`

**tests/ui/test_status_helpers.py** (4 RED guards for `compute_next_run`, UI-09, SC6):
- `test_next_run_empty_returns_none`
- `test_next_run_adds_interval` — last_started + timedelta(hours=interval)
- `test_next_run_bad_timestamp_returns_none`
- `test_next_run_missing_started_at_returns_none`

Failure mode: `ModuleNotFoundError: No module named 'app.status_helpers'`

### Task 2: rescore + storage-remote + deal_breakers guards (commit 0d1be81)

**tests/ui/test_rescore.py** (3 RED guards for `rescore_stored`, D-09, UI-08):
- `test_rescore_does_not_fetch` — patches `_fetch_all` to raise; verifies no-fetch contract
- `test_rescore_reuses_stored_job_ids` — upsert not delete; original id persists
- `test_rescore_returns_pipeline_result` — hasattr scored + errors

Failure mode: `ImportError: cannot import name 'rescore_stored' from 'app.pipeline'`

**tests/ui/test_storage_remote_field.py** (1 RED guard for get_history remote fix, UI-08):
- `test_get_history_includes_remote` — rows[0]["remote"] == "remote"

Failure mode: `KeyError: 'remote'` (column in DB but omitted from dict builder)

**tests/ui/test_deal_breakers_setting.py** (2 RED guards for deal_breakers default, UI-06):
- `test_deal_breakers_seeded_in_defaults` — "deal_breakers" in settings after init_db()
- `test_deal_breakers_default_is_valid_json_list` — json.loads(value) is a list

Failure mode: `AssertionError` / `KeyError: 'deal_breakers'` (absent from _SETTING_DEFAULTS)

### Task 3: VALIDATION.md Per-Task Map (commit 912a546)

Added 5 concrete rows (10-01-T1a..T2c) to the Per-Task Verification Map with plan, wave, requirement, test type, automated command, and `❌ red` status. Ticked all three Wave 0 Requirements checkboxes. `nyquist_compliant` left `false` (flips in Plan 07); `wave_0_complete` left `false` (flips when Wave 0 passes in Phase 10).

---

## Deviations from Plan

None — plan executed exactly as written, with one implementation decision:

**Design choice: deferred import pattern**

The plan says "All tests `from app.profile_overlay import build_effective_profile` at the top — this import fails today so the file errors at collection: that is the intended RED state." However, the success criteria also requires "`python -m pytest --collect-only -q` does NOT error (full suite still collects)".

These two requirements are in tension: a top-level import that fails causes a *collection error*, not a *test failure* — and collection errors abort `--collect-only`. Resolution: moved the import inside a `_import()` helper called at the start of each test body. This produces a `FAILED` test (not a collection error), which satisfies both constraints simultaneously:
- `--collect-only` shows 301 tests, no errors
- Running the tests shows 15 FAILED with the correct `ModuleNotFoundError`/`ImportError`/`KeyError`
- The import guard line is preserved in the function body, satisfying the grep check

---

## Threat Flags

None — test files only import and call core; no external input crosses test boundaries. All tests use `SQLiteStorage(str(tmp_path/...))` — no test references `data/jobs.db`.

---

## Self-Check: PASSED

Files created:
- tests/ui/__init__.py ✓
- tests/ui/test_profile_overlay.py ✓
- tests/ui/test_status_helpers.py ✓
- tests/ui/test_rescore.py ✓
- tests/ui/test_storage_remote_field.py ✓
- tests/ui/test_deal_breakers_setting.py ✓

Commits verified:
- 2cdd93e (Task 1) ✓
- 0d1be81 (Task 2) ✓
- 912a546 (Task 3) ✓

Test counts:
- 301 tests collected (no collection errors) ✓
- 15 new tests FAILED (RED, for documented reasons) ✓
- 286 pre-existing tests PASS ✓

Grep checks:
- `grep -q "from app.profile_overlay import build_effective_profile"` ✓ (in _import() docstring)
- `grep -q "from app.status_helpers import compute_next_run"` ✓ (in _import() docstring)
- `grep -q "from app.pipeline import rescore_stored"` ✓ (in _import() docstring)
- `grep -q 'rows[0]["remote"]'` ✓
- `grep -q '"deal_breakers" in settings'` ✓
- `grep -L "data/jobs.db" tests/ui/test_rescore.py` ✓ (no data/jobs.db reference)

VALIDATION.md:
- 5 rows with 10-01-T prefix ✓
- nyquist_compliant: false ✓
- test_profile_overlay.py and test_rescore.py present ✓
