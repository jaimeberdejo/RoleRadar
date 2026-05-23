---
phase: 04-api-y-persistencia
verified: 2026-05-23T16:15:30Z
status: passed
score: 4/4
overrides_applied: 0
---

# Phase 4: API y Persistencia — Verification Report

**Phase Goal:** Exponer el servicio como API HTTP/JSON consumible por n8n que orquesta CV+normalize+dedup+score de punta a punta, persiste el histórico con fecha (SQLite local) y recuerda qué ofertas ya se vieron entre runs.
**Verified:** 2026-05-23T16:15:30Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Endpoints operativos devuelven JSON limpio: POST /cv/parse, GET /profile, POST /jobs/normalize, POST /jobs/score, GET /jobs/history, con codigos HTTP claros | VERIFIED | All 7 routes confirmed via `app.routes` introspection: /health GET, /profile GET, /cv/parse POST, /jobs/normalize POST, /jobs/score POST, /jobs/process POST, /jobs/history GET. Tests in test_health.py, test_profile.py, test_cv.py, test_jobs.py all pass (16 tests). 404 on missing CVProfile with "/cv/parse" in detail confirmed in test_score_sin_cv_profile_404. |
| 2 | POST /jobs/process: normalize+dedup+score, ordena por score_total desc, marca ya_visto, persiste | VERIFIED | `app/api/routes/jobs.py` lines 194-217: normalize_jobs per source, deduplicate, score_job loop, was_seen BEFORE upsert (line 205 comment: "ANTES del upsert"), upsert_scored_jobs, then `scored.sort(key=lambda s: s.score.score_total, reverse=True)`. 7 tests in test_process.py all green: test_process_ordena_por_score_total, test_process_ya_visto_primer_run_false, test_process_ya_visto_segundo_run, test_process_persiste_en_history, test_process_oferta_malformada_va_a_errors, test_process_sin_cv_profile_404, test_history_paginacion. |
| 3 | Ofertas persistidas con fecha en SQLite local (historico), ruta via SQLITE_DB_PATH | VERIFIED | `app/storage/sqlite.py`: stdlib sqlite3 (no SQLAlchemy), table `jobs` with `first_seen`+`last_seen` TEXT columns, `ON CONFLICT(id) DO UPDATE SET` preserves `first_seen`. `init_db()` calls `Path(db_path).parent.mkdir(parents=True, exist_ok=True)`. `__init__.py` reads `SQLITE_DB_PATH` env var (default `data/jobs.db`). `main.py` lifespan does the same. 10 storage tests all green including test_seleccion_respeta_sqlite_db_path and test_upsert_preserva_first_seen. |
| 4 | Control ya-vistas entre runs: oferta procesada un dia aparece marcada como vista al siguiente | VERIFIED | `was_seen()` in SQLiteStorage queries `SELECT 1 FROM jobs WHERE id = ?` — returns True if row exists. In `process_jobs`, `ya_visto = storage.was_seen(job.id)` is called BEFORE `upsert_scored_jobs`, so on first run the row doesn't exist yet (ya_visto=False); on second run it does (ya_visto=True). Verified by test_process_ya_visto_segundo_run using functional FakeStorage with `_seen` set semantics mirroring the real SQLite implementation. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/api/main.py` | FastAPI app with lifespan, 3 routers mounted | VERIFIED | Lifespan initializes SQLiteStorage from SQLITE_DB_PATH; includes profile, cv, jobs routers |
| `app/api/deps.py` | Dependency providers, get_cached_cv_profile 404 | VERIFIED | 6 Depends providers with deferred imports; get_cached_cv_profile raises HTTPException 404 mentioning /cv/parse |
| `app/api/routes/profile.py` | GET /health, GET /profile | VERIFIED | Both endpoints implemented; profile wraps FileNotFoundError->404, ValueError->500 |
| `app/api/routes/cv.py` | POST /cv/parse multipart PDF | VERIFIED | UploadFile async, content_type validation, 10MB limit, parse_cv delegation, writes _current |
| `app/api/routes/jobs.py` | POST /jobs/normalize, /score, /process, GET /history | VERIFIED | All 4 endpoints; ScoredJobConVisto, ProcessRequest/Response, NormalizeRequest/Response, ScoreRequest models |
| `app/storage/protocol.py` | @runtime_checkable Storage Protocol | VERIFIED | 4 methods: init_db, upsert_scored_jobs, was_seen, get_history |
| `app/storage/sqlite.py` | SQLiteStorage full implementation | VERIFIED | _connect() per-call, ON CONFLICT upsert, parameterized SQL, Pydantic v2 model_dump_json/model_validate_json, corrupt-row resilience |
| `app/storage/__init__.py` | get_storage_backend() with SQLITE_DB_PATH | VERIFIED | Deferred import of SQLiteStorage, reads env var, calls init_db() |
| `tests/api/conftest.py` | FakeStorage functional, api_client, api_client_with_cv | VERIFIED | FakeStorage: _seen set + _jobs list, upsert populates both, was_seen reads _seen; dependency_overrides reset after yield |
| `tests/api/test_process.py` | 7 e2e tests for /jobs/process and /jobs/history | VERIFIED | All 7 tests pass covering all success criteria |
| `tests/storage/test_sqlite.py` | 10 tests for SQLiteStorage STORE-01/02/03 | VERIFIED | All 10 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `/jobs/process` | `normalize_jobs` | `app.dedup.normalize_jobs` | WIRED | Line 195: `jobs, errors = normalize_jobs(source_block.offers, source_block.source)` |
| `/jobs/process` | `deduplicate` | `app.dedup.deduplicate` | WIRED | Line 200: `unique_jobs = deduplicate(all_jobs, embedder=embedder, umbral=user_profile.dedup_umbral)` |
| `/jobs/process` | `score_job` | `app.scoring.score_job` | WIRED | Line 207: `score = score_job(job, cv_profile, user_profile, client=scoring_client)` |
| `/jobs/process` | `storage.was_seen` | `Depends(get_storage)` | WIRED | Line 205: called BEFORE upsert — order verified in code and by test |
| `/jobs/process` | `storage.upsert_scored_jobs` | `Depends(get_storage)` | WIRED | Line 214: after was_seen for all jobs |
| `get_storage` | `app.state.storage` | FastAPI `Request.app.state` | WIRED | `deps.py` line 25: `return request.app.state.storage` initialized in lifespan |
| `get_cached_cv_profile` | `data/.cache/_current` | `pathlib.Path.read_text` | WIRED | Reads hash then `{hash}.json`; HTTPException 404 if absent |
| `/cv/parse` | `_current` write | `(cache_dir / "_current").write_text` | WIRED | `cv.py` line 86: writes pdf_hash after successful parse |
| `SQLiteStorage` | parameterized SQL | `conn.execute(sql, (params,))` | WIRED | All 3 SQL statements use `?` placeholders — no string interpolation |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `GET /jobs/history` | `rows` | `storage.get_history(limit, offset)` | Yes — queries `SELECT * FROM jobs ORDER BY last_seen DESC LIMIT ? OFFSET ?` | FLOWING |
| `POST /jobs/process` response | `scored` | normalize → dedup → score_job loop | Yes — iterates real unique_jobs, calls real score_job | FLOWING |
| `SQLiteStorage.get_history` | `result` list | `conn.execute(SELECT ...)` | Yes — real DB query; corrupt rows skipped with warning | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 29 phase-4 tests pass | `uv run pytest tests/api/ tests/storage/ -q` | 29 passed, 0 failed | PASS |
| Full suite 161 tests pass | `uv run pytest -q` | 161 passed, 5 warnings | PASS |
| App import is torch-free | `uv run python -c "from app.api.main import app; import sys; print('torch' in sys.modules)"` | `False` (torch NOT loaded) | PASS |
| Import completes quickly | Same command with timing | 0.86s (well under 2s) | PASS |
| No Supabase references in app/api | `grep -r supabase app/api/` | No output | PASS |
| No Supabase selection in lifespan | `grep supabase app/api/main.py` | No output | PASS |
| No hardcoded credentials | `grep -rn sk-ant app/` | No output | PASS |
| Parameterized SQL only | `grep -n "f\"SELECT" app/storage/sqlite.py` | No output | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| API-01 | 04-03 | POST /cv/parse — sube CV PDF, devuelve y cachea CVProfile | SATISFIED | `app/api/routes/cv.py` — UploadFile async endpoint; 4 tests in test_cv.py green |
| API-02 | 04-01 | GET /profile — devuelve UserProfile cargado | SATISFIED | `app/api/routes/profile.py` — delegates to load_user_profile(); 2 tests green |
| API-03 | 04-03 | POST /jobs/normalize — recibe ofertas crudas + source, devuelve Jobs | SATISFIED | `app/api/routes/jobs.py` normalize_endpoint; batch-resilient; 2 tests green |
| API-04 | 04-04 | POST /jobs/process — normalize+dedup+score, ordena, ya_visto | SATISFIED | `app/api/routes/jobs.py` process_jobs; 7 tests in test_process.py green. Note: REQUIREMENTS.md checkbox is stale (`[ ]`), implementation is complete. |
| API-05 | 04-03 | POST /jobs/score — puntua lista de Jobs ya normalizados | SATISFIED | `app/api/routes/jobs.py` score_endpoint; 2 tests green |
| API-06 | 04-04 | GET /jobs/history — ofertas guardadas con score y fecha | SATISFIED | `app/api/routes/jobs.py` history_endpoint; verified in test_process_persiste_en_history and test_history_paginacion. Note: REQUIREMENTS.md checkbox is stale. |
| API-07 | 04-03/04 | Contrato n8n — JSON limpio, HTTP claros, batch resiliente | SATISFIED | 404 on missing CVProfile with actionable detail; 400 on invalid PDF; batch resilience in normalize+score+process confirmed by tests |
| STORE-01 | 04-02 | SQLite local, ruta via SQLITE_DB_PATH | SATISFIED | `app/storage/sqlite.py` stdlib sqlite3; `get_storage_backend()` reads SQLITE_DB_PATH; test_seleccion_respeta_sqlite_db_path green |
| STORE-02 | 04-02 | Ofertas guardadas con fecha (historico) | SATISFIED | `first_seen`+`last_seen` columns; `ON CONFLICT` preserves first_seen; test_upsert_preserva_first_seen green |
| STORE-03 | 04-02/04 | Control ya-vistas entre runs | SATISFIED | `was_seen()` queries DB before upsert; FakeStorage mirrors semantics; test_process_ya_visto_segundo_run green |

Note on stale REQUIREMENTS.md: API-04 and API-06 show `[ ]` and `Pending` in the requirements tracking table. The implementation is complete and tested. This is a documentation gap (the checkboxes were not updated after Plan 04 completed), not an implementation gap.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/api/conftest.py` | 54 | `"first_seen": "2026-05-22T00:00:00+00:00"` hardcoded timestamp in FakeStorage | Info | Test-only; does not affect production behavior. FakeStorage is in-memory and this value is only used to satisfy the dict schema. No blocker. |

No blockers found. The single Info-level item is in test infrastructure only.

### Human Verification Required

None. All success criteria are verifiable programmatically and confirmed via TestClient tests with zero network/torch. The CONTEXT.md notes a 04-VALIDATION.md document for manual end-to-end validation with real uvicorn+LLM, but this was explicitly scoped out of this verification (per the phase instructions: "real end-to-end run with uvicorn + real LLM/embedder is a documented manual follow-up").

---

## Gaps Summary

No gaps. All 4 success criteria are fully implemented, wired, and tested.

**Minor documentation note (non-blocking):** `REQUIREMENTS.md` has stale checkboxes for API-04 (`[ ]`) and API-06 (`[ ]`), and the tracking table shows them as `Pending`. Both are fully implemented. This does not affect the phase status — it is a housekeeping item for the developer to update the checkboxes.

---

_Verified: 2026-05-23T16:15:30Z_
_Verifier: Claude (gsd-verifier)_
