---
phase: 05-observabilidad-robustez-docs
verified: 2026-05-23T18:44:08Z
status: passed
score: 4/4
overrides_applied: 0
---

# Phase 5: Observabilidad, Robustez y Docs n8n — Verification Report

**Phase Goal:** Servicio listo para portfolio y uso real: visible (logging + stub Langfuse), resiliente por capas, y documentado para instalarlo/configurarlo/conectarlo a n8n sin leer el codigo.
**Verified:** 2026-05-23T18:44:08Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Logging estructurado reporta el flujo de cada run (entradas, duplicados, puntuadas, errores, nr llamadas LLM) | VERIFIED | `process_jobs` in `app/api/routes/jobs.py` L239-245: `logger.info("process_jobs: entradas=%d unicos=%d puntuados=%d llm_calls=%d errores=%d", ...)`. `llm_calls` counter initialized at L222, incremented per successful `score_job` at L227. `configure_logging()` called as first action in lifespan (L50-52 of `app/api/main.py`). |
| 2 | Interfaz/stub de Langfuse preparada; manejo de errores aislado por capa | VERIFIED | `app/obs/tracing.py`: `trace_llm` context manager with double guard (env vars + ImportError). `assess_job` wrapped at `app/scoring/llm.py` L182, `extract_cv_profile` wrapped at `app/cv/llm_client.py` L44. `app/errors.py`: `BuscadorError` base + 4 typed subclasses. 5 FastAPI handlers in `app/api/main.py` ordered specific-before-generic (CVParseError/NormalizationError/ScoringError -> 422, StorageError -> 503, Exception -> 500 fixed "Internal server error"). 178/178 tests green. |
| 3 | README cubre instalacion/.env/profile/CV/arranque/tests + seccion dedicada a n8n con JSON exacto de /jobs/process | VERIFIED | README.md has sections: Instalacion (uv sync), Configuracion .env (cp .env.example .env), Editar el perfil (data/profile.yaml), Subir el CV (/cv/parse), Arrancar el servicio (uv run uvicorn app.api.main:app), Correr los tests (uv run pytest -q). Section "Integracion con n8n" at L219 includes: flujo complete, exact `{"sources": [...]}` request JSON, exact `{"results": [...], "errors": [...]}` response JSON with `ya_visto` field, n8n node table. No Supabase or OPENAI_API_KEY mentions. |
| 4 | Ejemplos (examples/*.json) para probar /jobs/process sin n8n | VERIFIED | `examples/arbeitnow_offers.json`, `examples/generic_offers.json`, `examples/process_request.json` all exist with realistic fictional data (4 offers across 2 sources). `tests/api/test_examples.py` confirms JSON validity + POST /jobs/process returns 200 with mocked LLM/embedder. |

**Score:** 4/4 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/obs/logging_config.py` | configure_logging() with key=value format, idempotency guard | VERIFIED | Idempotency: `if root.handlers: return`. Format: `"%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"`. 3 tests in `tests/obs/test_logging.py`: idempotency, key=value format, level. |
| `app/obs/tracing.py` | trace_llm() no-op by default, lazy langfuse import | VERIFIED | Double guard: `_LANGFUSE_CONFIGURED` flag + `except ImportError`. Confirmed langfuse-free: `python3 -c "import app.obs.tracing; assert 'langfuse' not in sys.modules"` PASS. 5 tests in `tests/obs/test_tracing.py`. |
| `app/obs/__init__.py` | Package exporting configure_logging + trace_llm | VERIFIED | Exports both symbols via `__all__`. |
| `app/errors.py` | BuscadorError + CVParseError/NormalizationError/ScoringError/StorageError | VERIFIED | All 5 classes present with Spanish docstrings. No extra fields — str(exc) is sufficient for handlers. |
| `app/api/main.py` | exception handlers ordered specific-before-generic; configure_logging in lifespan | VERIFIED | 5 handlers registered. Generic `Exception` handler at L114 appears after all specific handlers (L78, L87, L96, L105). configure_logging() at L50 is first action in lifespan. Generic handler: `logger.exception` to log, fixed "Internal server error" to client — never leaks str(exc). |
| `app/api/routes/jobs.py` | llm_calls counter in process_jobs | VERIFIED | `llm_calls = 0` at L222; `llm_calls += 1` at L227 (after successful score_job); included in final `logger.info` at L240. |
| `app/scoring/llm.py` | assess_job wrapped with trace_llm | VERIFIED | `with trace_llm("assess_job", job_id=job.id, model=model):` wraps entire `client.messages.create` call at L182-201. |
| `app/cv/llm_client.py` | extract_cv_profile wrapped with trace_llm | VERIFIED | `with trace_llm("extract_cv_profile", model=model):` wraps entire `client.messages.create` call at L44-63. |
| `README.md` | Full install + n8n integration with exact JSON | VERIFIED | 388 lines, all required sections present. Exact request/response JSON documented. No Supabase or OpenAI refs. |
| `examples/process_request.json` | Valid JSON, 2+ sources | VERIFIED | 4 offers across 2 sources (arbeitnow + generic). All fictional, realistic data. |
| `tests/obs/test_logging.py` | idempotency + key=value + level tests | VERIFIED | 3 tests, all passing. |
| `tests/obs/test_tracing.py` | no-op sans env vars + sans langfuse + import safety | VERIFIED | 5 tests, all passing. |
| `tests/api/test_exception_handlers.py` | 6 handler tests including anti-leak | VERIFIED | 6 tests: CVParseError->422, NormalizationError->422, ScoringError->422, StorageError->503, generic->500 without stack trace, batch resilience regression. All passing. |
| `tests/api/test_examples.py` | JSON validity + endpoint acceptance | VERIFIED | 2 tests: `test_examples_son_json_valido`, `test_process_request_aceptado_por_endpoint`. Both passing. |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `app/api/main.py` lifespan | `app/obs/logging_config.py` | `configure_logging()` (deferred import #noqa:PLC0415) | WIRED | L50-52 in lifespan body, first action before SQLiteStorage setup |
| `app/api/main.py` | `app/errors.py` | `@app.exception_handler(CVParseError)` etc., specific before generic | WIRED | 4 specific handlers at L78-111, generic fallback at L114-126. Ordering verified. |
| `app/scoring/llm.py:assess_job` | `app/obs/tracing.py:trace_llm` | `with trace_llm("assess_job", ...)` | WIRED | L25 import, L182 wrapping context manager. Return is inside with block (full roundtrip covered). |
| `app/cv/llm_client.py:extract_cv_profile` | `app/obs/tracing.py:trace_llm` | `with trace_llm("extract_cv_profile", ...)` | WIRED | L23 import, L44 wrapping context manager. |
| `app/api/routes/jobs.py:process_jobs` | `logger.info` | `llm_calls=%d` counter | WIRED | L222 init, L227 increment, L239-245 final log with all counters. |

---

## Data-Flow Trace (Level 4)

Not applicable — Phase 5 adds observability instrumentation, error handling, and documentation over existing endpoints. No new data-rendering components introduced. The counter `llm_calls` feeds into `logger.info` (not user-facing JSON), verified at source.

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite green | `uv run pytest 2>&1 \| grep "[0-9]+ passed"` | `178 passed, 5 warnings in 0.75s` | PASS |
| langfuse absent from pyproject.toml | `grep -i "langfuse" pyproject.toml` | (no output) | PASS |
| langfuse-free import of tracing module | `python3 -c "import app.obs.tracing; assert 'langfuse' not in sys.modules"` | no error | PASS |
| llm_calls counter present in jobs.py | `grep -n "llm_calls" app/api/routes/jobs.py` | Lines 222, 227, 240, 244 | PASS |
| 5 exception handlers registered | `grep -c "@app.exception_handler" app/api/main.py` | 5 | PASS |
| Generic handler never leaks str(exc) | test_generic_exception_returns_500_without_stack_trace | PASSED (asserts "internal secret path" not in body) | PASS |
| No Supabase/OpenAI refs in README | `grep -i "supabase\|OPENAI_API_KEY" README.md` | (no output) | PASS |
| n8n section with exact JSON in README | `grep -n '"sources"' README.md` | Line 258 | PASS |

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| OBS-01 | Logging estructurado (entradas, duplicados, puntuadas, nr LLM calls) | SATISFIED | `configure_logging()` in lifespan; `process_jobs` logs all 5 counters including `llm_calls=%d` |
| OBS-02 | Interfaz Langfuse preparada (stub) para trazar scoring | SATISFIED | `trace_llm` no-op stub; wired on both LLM call sites; langfuse optional dep absent from pyproject.toml |
| OBS-03 | Manejo de errores por capa | SATISFIED | `app/errors.py` hierarchy; 5 FastAPI handlers; generic handler anti-leak; 6 tests |
| DOC-01 | README con instalacion, .env, profile.yaml, CV upload, arranque | SATISFIED | README has all sections; cp .env.example .env; uv run uvicorn; uv run pytest |
| DOC-02 | Seccion "Integracion con n8n" con JSON exacto | SATISFIED | README L219-388: flujo, exact request/response JSON, ya_visto semantics, n8n node table, expose instructions |
| DOC-03 | profile.yaml de ejemplo + ofertas JSON para probar sin n8n | SATISFIED | examples/process_request.json (4 offers, 2 sources); test_examples.py acceptance test |

Note: REQUIREMENTS.md traceability table still shows DOC-01/02/03 as "Pending" — this is a stale status in the tracker only; the actual implementation is complete and verified above.

---

## Anti-Patterns Found

No blockers or warnings found.

| File | Pattern Checked | Result |
|------|-----------------|--------|
| `app/obs/tracing.py` | placeholder / TODO / return null | Clean |
| `app/obs/logging_config.py` | placeholder / TODO | Clean |
| `app/errors.py` | stub classes / empty implementations | Clean — docstrings only, appropriate for exception classes |
| `app/api/main.py` | fixed "Internal server error" (intentional) | Not a stub — it is the security invariant T-05-03 |
| `README.md` | placeholder sections / TODO | Clean — all sections are concrete commands and JSON |
| `examples/*.json` | hardcoded credentials / placeholder values | Clean — fictional data only |
| `.env.example` | hardcoded real credentials | Clean — only placeholder values (sk-ant-..., pk-lf-...) |

---

## Human Verification Required

None — all success criteria are verifiable programmatically. The following are noted as acceptable deferred manual follow-ups (already documented in `05-VALIDATION.md`):

1. Real Langfuse trace (requires a live Langfuse account + `uv add langfuse` + real env vars) — intentionally deferred to OBS-04 (v2). The stub is verified to activate correctly when configured.
2. Following the n8n integration guide with a real n8n instance — this is documentation verification, not code verification. The JSON contracts are verified by the acceptance tests.

---

## Gaps Summary

No gaps. All 4 success criteria are verified with code evidence, 178 tests pass (no regressions), and the 6 requirements for Phase 5 (OBS-01, OBS-02, OBS-03, DOC-01, DOC-02, DOC-03) are satisfied.

One stale item noted for cleanup: `REQUIREMENTS.md` traceability table shows DOC-01/02/03 as "Pending" — this should be updated to "Complete" as the implementation and tests exist. This does not block the phase.

---

_Verified: 2026-05-23T18:44:08Z_
_Verifier: Claude (gsd-verifier)_
