---
phase: 05-observabilidad-robustez-docs
plan: "01"
subsystem: observabilidad
tags: [observability, logging, tracing, langfuse-stub, stdlib, no-op]
dependency_graph:
  requires: []
  provides: [app.obs.configure_logging, app.obs.trace_llm]
  affects: [app.api.main (lifespan), app.scoring.llm, app.cv.llm_client]
tech_stack:
  added: []
  patterns:
    - stdlib logging with idempotency guard (if root.handlers: return)
    - lazy/optional import pattern (# noqa: PLC0415) for langfuse
    - double guard: env vars first, ImportError second
key_files:
  created:
    - app/obs/__init__.py
    - app/obs/logging_config.py
    - app/obs/tracing.py
    - tests/obs/__init__.py
    - tests/obs/test_logging.py
    - tests/obs/test_tracing.py
  modified: []
decisions:
  - "stdlib logging only (no structlog/loguru): zero new deps, grep-able key=value format"
  - "idempotency guard on root.handlers (not stdout-specific): matches RESEARCH Pattern 3 exactly"
  - "tracing.py pre-created during Task 2 to unblock app/obs/__init__.py import chain (Rule 3)"
  - "test fixture clears handlers inline (not in setup) to avoid pytest LogCaptureHandler race"
metrics:
  duration: "5m 18s"
  completed: "2026-05-23T18:24:25Z"
  tasks_completed: 3
  files_changed: 6
---

# Phase 05 Plan 01: Observability Modules (app/obs/) Summary

**One-liner:** stdlib logging with key=value format + Langfuse 4.x no-op stub using double guard (env vars + ImportError), both langfuse-free by default.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create app/obs/ and tests/obs/ packages | f215af4 | app/obs/__init__.py, tests/obs/__init__.py |
| 2 | configure_logging() + test idempotency (OBS-01) | f2bce15 | app/obs/logging_config.py, tests/obs/test_logging.py |
| 2 RED | Failing tests for configure_logging | 02cf15f | tests/obs/test_logging.py |
| 3 | trace_llm() no-op stub + tests (OBS-02) | 4e86736 | app/obs/tracing.py |
| 3 RED/GREEN | Tests for trace_llm no-op | 7dcd32a | tests/obs/test_tracing.py |

## Verification Results

- `uv run python -m pytest tests/obs/ -v`: 8 passed, 0 failed
- `uv run python -m pytest -v`: 170 passed (162 baseline + 8 new), 0 regressions
- `python -c "import app.obs.tracing, sys; assert 'langfuse' not in sys.modules"`: PASS
- `grep -v '^#' pyproject.toml | grep -ci langfuse`: 0 (langfuse absent from deps)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tracing.py pre-created during Task 2**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** `app/obs/__init__.py` imports both `configure_logging` and `trace_llm`. When the test for Task 2 attempted `from app.obs.logging_config import configure_logging`, Python first imported `app/obs/__init__.py`, which failed because `app.obs.tracing` didn't exist yet (`ModuleNotFoundError: No module named 'app.obs.tracing'`).
- **Fix:** Created the full `app/obs/tracing.py` implementation during Task 2's GREEN phase. This unblocked the import chain and allowed Task 3 to start from a GREEN baseline.
- **Files modified:** `app/obs/tracing.py` (created)
- **Commit:** f2bce15 (included in Task 2 GREEN commit)

**2. [Rule 1 - Bug] Test fixture approach adapted for pytest LogCaptureHandler**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** The fixture `clean_root` cleared `root.handlers` in the setup phase, but pytest's internal `_pytest.logging` plugin re-adds `LogCaptureHandler` instances between fixture setup and test body execution. This caused `configure_logging()`'s `if root.handlers: return` guard to trigger immediately (no-op), so no handler was added.
- **Fix:** Moved the `root.handlers[:] = []` clear into the test body itself (immediately before calling `configure_logging()`), ensuring it runs after pytest's log capture setup.
- **Files modified:** `tests/obs/test_logging.py`
- **Impact:** Tests pass correctly; the idempotency guard remains `if root.handlers: return` exactly as specified.

## Known Stubs

None — both modules are fully implemented for their scope:
- `configure_logging()`: complete stdlib logging setup (OBS-01 partial — lifespan wiring and llm_calls counter are Plan 02)
- `trace_llm()`: complete no-op stub with double guard (OBS-02 stub — full Langfuse 4.x wiring when installed)

## Threat Flags

No new threat surface introduced. STRIDE T-05-01 (Information Disclosure via Langfuse creds) is mitigated: credentials read exclusively from `os.environ`, never hardcoded. Verified by acceptance criterion grep.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| Task 2 RED | 02cf15f | test(05-01): failing tests for configure_logging |
| Task 2 GREEN | f2bce15 | feat(05-01): implement configure_logging |
| Task 3 RED | 7dcd32a | test(05-01): tests for trace_llm no-op |
| Task 3 GREEN | 4e86736 | feat(05-01): implement trace_llm stub |

Note: Task 3 RED tests passed immediately because `tracing.py` was pre-created as a Rule 3 deviation during Task 2. The TDD gate commits exist and are ordered correctly (test before feat).

## Self-Check: PASSED

- [x] `app/obs/__init__.py` exists: FOUND
- [x] `app/obs/logging_config.py` exists: FOUND
- [x] `app/obs/tracing.py` exists: FOUND
- [x] `tests/obs/__init__.py` exists: FOUND
- [x] `tests/obs/test_logging.py` exists: FOUND
- [x] `tests/obs/test_tracing.py` exists: FOUND
- [x] Commit f215af4 exists: FOUND
- [x] Commit 02cf15f exists: FOUND
- [x] Commit f2bce15 exists: FOUND
- [x] Commit 7dcd32a exists: FOUND
- [x] Commit 4e86736 exists: FOUND
- [x] 170 tests passing (162 baseline + 8 new): VERIFIED
