---
phase: 05-observabilidad-robustez-docs
plan: 02
subsystem: api
tags: [fastapi, exception-handlers, logging, langfuse, tracing, error-handling, observability]

# Dependency graph
requires:
  - phase: 05-observabilidad-robustez-docs plan 01
    provides: app/obs/tracing.py (trace_llm no-op stub) and app/obs/logging_config.py (configure_logging)

provides:
  - app/errors.py: domain exception hierarchy (BuscadorError, CVParseError, NormalizationError, ScoringError, StorageError)
  - FastAPI exception handlers in app/api/main.py mapping each layer exception to clean JSON HTTP responses
  - configure_logging() called as first action in lifespan (OBS-01)
  - assess_job and extract_cv_profile wrapped with trace_llm (OBS-02 call site wiring)
  - llm_calls counter in process_jobs with llm_calls=%d in final logger.info (OBS-01)
  - tests/api/test_exception_handlers.py: 6 tests verifying each handler + anti-leak + batch resilience

affects:
  - 05-03 (README/n8n docs): exception envelope format is now the stable API contract for error responses

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Exception handler ordering: specific handlers (CVParseError, NormalizationError, ScoringError, StorageError) registered BEFORE generic Exception — FastAPI matches first"
    - "Anti information disclosure (T-05-03): generic handler logs stack trace with logger.exception, returns fixed 'Internal server error' string to client"
    - "trace_llm no-op wiring: wrap client.messages.create with 'with trace_llm(name, **meta):' — transparent when LANGFUSE env vars absent"
    - "TDD: RED commit (test(05-02)) + GREEN commit (feat(05-02)) on same task"

key-files:
  created:
    - app/errors.py
    - tests/api/test_exception_handlers.py
  modified:
    - app/api/main.py
    - app/api/routes/jobs.py
    - app/scoring/llm.py
    - app/cv/llm_client.py

key-decisions:
  - "StorageError maps to 503 (Service Unavailable) rather than 422 — storage failures are infrastructure failures, not input validation errors"
  - "Generic Exception handler message is always fixed 'Internal server error' — str(exc) is never serialized to the response body regardless of exception type"
  - "trace_llm wraps client.messages.create entirely (the return is inside the with block) — ensures the span covers the full LLM roundtrip"
  - "CVParseError test uses get_cached_cv_profile Depends override on /jobs/score rather than /cv/parse (which validates content_type before calling the dep)"
  - "llm_calls incremented after successful score_job (not before) — only counts actual LLM calls, not attempts"

patterns-established:
  - "Error envelope: {'error': {'type': ExcClassName, 'message': str(exc)}} — consistent across all domain exception handlers"
  - "Deferred import in lifespan: configure_logging imported inside lifespan body with # noqa: PLC0415 (same pattern as SQLiteStorage)"

requirements-completed: [OBS-01, OBS-02, OBS-03]

# Metrics
duration: 25min
completed: 2026-05-23
---

# Phase 5 Plan 02: Robustez y Observabilidad — Exception Handlers + Tracing Wiring Summary

**Domain exception hierarchy (app/errors.py) + FastAPI exception handlers with anti-leak 500 fallback + configure_logging() in lifespan + trace_llm wired on both LLM call sites + llm_calls counter in process_jobs**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-23T00:00:00Z
- **Completed:** 2026-05-23
- **Tasks:** 2 (Task 1: auto; Task 2: TDD with RED + GREEN commits)
- **Files modified:** 6 (4 modified + 2 created)

## Accomplishments

- Created `app/errors.py` with `BuscadorError` base class and 4 domain subclasses (CVParseError, NormalizationError, ScoringError, StorageError) with Spanish docstrings
- Registered 5 FastAPI exception handlers in `app/api/main.py` in correct order (specific before generic): CVParseError/NormalizationError/ScoringError → 422, StorageError → 503, Exception → 500 with fixed "Internal server error" (no stack trace to client)
- Called `configure_logging()` as first action in lifespan, ensuring all startup logs are structured
- Wrapped `assess_job` and `extract_cv_profile` LLM call sites with `trace_llm` context manager (no-op by default, Langfuse-ready)
- Added `llm_calls` counter to `process_jobs` loop; emitted in final `logger.info` as `llm_calls=%d`
- 6 new tests: each domain exception → correct status code, generic exception anti-leak assertion, batch resilience regression

## Task Commits

Each task was committed atomically:

1. **Task 1: Domain exceptions + trace_llm wiring + llm_calls counter** - `d363925` (feat)
2. **Task 2 RED: Failing exception handler tests** - `4174c67` (test)
3. **Task 2 GREEN: Exception handlers + configure_logging** - `1c456ef` (feat)

**Plan metadata:** see final docs commit

_Note: Task 2 followed TDD: RED commit (failing tests) then GREEN commit (implementation)._

## Files Created/Modified

- `app/errors.py` — BuscadorError base + CVParseError, NormalizationError, ScoringError, StorageError
- `app/api/main.py` — configure_logging() in lifespan; 5 exception handlers (4 specific + 1 generic fallback)
- `app/api/routes/jobs.py` — llm_calls counter initialized before loop, incremented per successful score_job, included in final log
- `app/scoring/llm.py` — trace_llm import + with trace_llm("assess_job", job_id=job.id, model=model): wrapping client.messages.create
- `app/cv/llm_client.py` — trace_llm import + with trace_llm("extract_cv_profile", model=model): wrapping client.messages.create
- `tests/api/test_exception_handlers.py` — 6 tests: CVParseError/NormalizationError/ScoringError → 422, StorageError → 503, generic exception anti-leak, batch resilience regression

## Decisions Made

- StorageError maps to 503 (not 422) — storage failures are infrastructure failures, not client input validation errors.
- Generic Exception handler always returns fixed "Internal server error" string — str(exc) is never serialized to the response body (T-05-03 anti information disclosure).
- CVParseError test injects via `get_cached_cv_profile` Depends on `/jobs/score` rather than `/cv/parse`, because `/cv/parse` validates `content_type` before calling the Depends, making injection harder.
- `trace_llm` wraps the entire `client.messages.create` call (return is inside the `with` block) to cover the full LLM roundtrip.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected batch resilience test payload**

- **Found during:** Task 2 GREEN (exception handlers)
- **Issue:** Initial test payload `{"employer": "INVALID — missing required fields"}` was silently accepted by the generic mapper (it uses best-effort field mapping and doesn't raise for missing fields), producing `errors=[]` instead of `errors[len>0]`.
- **Fix:** Changed to `{"company_name": 12345, "title": None}` — int in a string field causes `TypeError` in `normalize_field()` inside the mapper, which is caught batch-resiliently and goes to `errors[]`. This matches the canonical `sample_malformed_payload` fixture in `tests/conftest.py`.
- **Files modified:** `tests/api/test_exception_handlers.py`
- **Verification:** Test passes with `assert len(body["errors"]) > 0`.
- **Committed in:** `1c456ef` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test payload assumption)
**Impact on plan:** Minor test payload correction — no business logic change. The fix aligns the test with the canonical malformed payload pattern already established in the project.

## Issues Encountered

None — other than the test payload issue above, all implementation proceeded exactly as planned.

## Threat Surface Scan

| Flag | File | Description |
|------|------|-------------|
| T-05-03 covered | app/api/main.py | Generic exception handler returns fixed "Internal server error" — verified by test_generic_exception_returns_500_without_stack_trace |

## Known Stubs

None — all wiring is functional. `trace_llm` is intentionally a no-op when `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` are absent (by design, OBS-02 is the stub phase; OBS-04 is the full wiring).

## Next Phase Readiness

- OBS-01, OBS-02, OBS-03 all complete — logging, tracing stubs, and error handling are wired
- 05-03 (README + n8n integration docs) can proceed; the exception envelope format (`{"error": {"type": ..., "message": ...}}`) is the stable contract to document
- All 176 tests green (170 baseline + 6 new)

---
*Phase: 05-observabilidad-robustez-docs*
*Completed: 2026-05-23*
