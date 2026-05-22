---
phase: 02-normalizacion-y-deduplicacion
verified: 2026-05-22T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 2: Normalización y Deduplicación — Verification Report

**Phase Goal:** Convertir ofertas crudas heterogéneas en Jobs normalizados con id estable y eliminar duplicados exactos y semánticos sin perder información.
**Verified:** 2026-05-22
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                           | Status     | Evidence                                                                                                                 |
|----|------------------------------------------------------------------------------------------------|------------|--------------------------------------------------------------------------------------------------------------------------|
| 1  | Dada una lista de ofertas crudas + source, devuelve Jobs normalizados con id estable idéntico entre runs | ✓ VERIFIED | `normalize_jobs` returns `(jobs, errors)`; `stable_job_id` is sha256(NFD-normalized company+title+location); confirmed deterministic and case/accent-insensitive via direct invocation |
| 2  | Una oferta mal formada no tumba el batch (procesa lo que puede, reporta errores)                | ✓ VERIFIED | Per-item `try/except Exception` in `normalize_jobs`; confirmed: 2 good + 1 bad = 2 jobs, 1 error with correct index/source/error fields |
| 3  | Detecta y colapsa duplicados exactos (hash) y semánticos (BGE-M3 cosine ≥ umbral)              | ✓ VERIFIED | `exact_group` groups by normalized company+title; `semantic_cluster` greedy cosine with `np.clip` float32 guard; `FakeEmbedder` with identity vectors forces semantic merge; `FakeEmbedder` with orthogonal vectors preserves 3 distinct jobs |
| 4  | Al deduplicar conserva la descripción más completa y guarda urls_alternativas                   | ✓ VERIFIED | `merge_group` selects `max(group, key=lambda j: len(j.description))`; accumulates discarded URLs via `model_copy(update={"urls_alternativas": ...})`; None URLs excluded; no mutation of canonical original |
| 5  | Tests de normalización por fuente y de dedup (obvios + semánticos) con embeddings mockeados     | ✓ VERIFIED | 73 tests in `tests/dedup/` (34 normalize, 31 unit dedup, 8 e2e); 86 total suite passes in 0.41s; zero BgeM3Embedder invocations in `test_dedup.py`; anti-torch invariant tested and confirmed passing |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                       | Expected                                    | Status     | Details                                                                 |
|-------------------------------|---------------------------------------------|------------|-------------------------------------------------------------------------|
| `app/dedup/__init__.py`        | `normalize_jobs` + `deduplicate` facade      | ✓ VERIFIED | Both functions present, wired, deferred imports inside `deduplicate()` body |
| `app/dedup/normalize.py`       | `normalize_field` + `stable_job_id`          | ✓ VERIFIED | NFD decomposition + Mn filter + casefold; sha256 64-hex; stdlib only   |
| `app/dedup/mappers.py`         | `MAPPER_REGISTRY`, `arbeitnow_mapper`, `generic_mapper` | ✓ VERIFIED | Registry present; arbeitnow maps HTML→stripped desc, Unix ts→ISO 8601, remote bool; generic covers employer/job_title/city/body/apply_url/is_remote variants; AJUSTABLE banners on all mappers |
| `app/dedup/embedder.py`        | `Embedder` Protocol, `BgeM3Embedder` (lazy), `FakeEmbedder` | ✓ VERIFIED | `sentence_transformers` import ONLY inside `_ensure_loaded()`; `BgeM3Embedder.__init__` sets `_model=None`; `FakeEmbedder` resolves dict→default→hash-sha256; all three classes present |
| `app/dedup/exact.py`           | `exact_group`                               | ✓ VERIFIED | Groups by `normalize_field(company) + "|" + normalize_field(title)`; handles empty list |
| `app/dedup/semantic.py`        | `build_embed_text` + `semantic_cluster`      | ✓ VERIFIED | Greedy cosine clustering; `E @ E.T` + `np.clip(-1, 1)` for float32 guard; degenerate gracefully with empty desc |
| `app/dedup/merger.py`          | `merge_group`                               | ✓ VERIFIED | `max(group, key=len(description))`; Pydantic v2 `model_copy(update=...)`; no mutation; None URLs excluded |
| `tests/dedup/__init__.py`      | Package init                                | ✓ VERIFIED | Exists as empty package init                                            |
| `tests/dedup/test_normalize.py`| 34 normalization tests (NORM-01..04, QA-02) | ✓ VERIFIED | All 34 pass; covers stable_job_id determinism, NFD, arbeitnow/generic mappers, batch resilience |
| `tests/dedup/test_dedup_units.py`| 31 unit tests (embedder, exact, semantic, merger) | ✓ VERIFIED | All 31 pass; includes anti-torch reload test; never calls `BgeM3Embedder.embed()` |
| `tests/dedup/test_dedup.py`    | 8 e2e tests (QA-03)                         | ✓ VERIFIED | All 8 pass; zero BgeM3Embedder mentions; FakeEmbedder injected via `embedder=` param |

### Key Link Verification

| From                        | To                                 | Via                                      | Status     | Details                                                                       |
|-----------------------------|------------------------------------|------------------------------------------|------------|-------------------------------------------------------------------------------|
| `normalize_jobs`            | `MAPPER_REGISTRY`                  | `MAPPER_REGISTRY.get(source) or MAPPER_REGISTRY["generic"]` | ✓ WIRED | Unknown source falls back to generic mapper; confirmed by test `test_normalize_jobs_unknown_source_uses_generic` |
| `normalize_jobs`            | per-item `try/except`              | batch loop in `__init__.py`              | ✓ WIRED | Malformed offer appended to `errors` list; direct invocation confirms index/source/error fields |
| `deduplicate`               | `exact_group → merge_group → semantic_cluster → merge_group` | deferred imports inside function body | ✓ WIRED | Two-level flow confirmed by e2e tests; deferred import verified: `import app.dedup` does not pull torch |
| `deduplicate`               | `BgeM3Embedder` (lazy fallback)    | `if embedder is None: embedder = BgeM3Embedder()` | ✓ WIRED | Production path lazy; tests always inject FakeEmbedder and never hit this branch |
| `merge_group`               | `Job.urls_alternativas`            | `model_copy(update={"urls_alternativas": ...})` | ✓ WIRED | Confirmed: canonical description preserved; discarded URL appears in urls_alternativas; original Job not mutated |
| `stable_job_id`             | sha256 of normalized key           | `normalize_field(company) + "|" + normalize_field(title) + "|" + normalize_field(location)` | ✓ WIRED | 64-hex confirmed; case/accent-invariant confirmed |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces library/service functions (no components rendering dynamic data from an API). The data flow is: raw_offers (caller-supplied) → `normalize_jobs` → `Job` objects → `deduplicate` → deduplicated `Job` list. All paths traced and confirmed live.

### Behavioral Spot-Checks

| Behavior                                               | Command (condensed)                                   | Result                                  | Status  |
|--------------------------------------------------------|-------------------------------------------------------|-----------------------------------------|---------|
| `stable_job_id` is deterministic and 64-hex            | `python -c "from app.dedup.normalize import stable_job_id; ..."` | deterministic=True, length=64, case-insensitive=True | ✓ PASS |
| `normalize_jobs` batch resilience                      | `python -c "from app.dedup import normalize_jobs; ..."` | 2 jobs, 1 error, error has index/source/error | ✓ PASS |
| `deduplicate` exact dup: keeps longest desc + urls_alternativas | `python -c "from app.dedup import deduplicate; ..."` | 1 job, longest desc=True, urls_alternativas=['http://x.com/1'] | ✓ PASS |
| Anti-torch invariant: `import app.dedup` does not pull torch | `python -c "import app.dedup; print('torch' in sys.modules)"` | False | ✓ PASS |
| Full test suite                                        | `uv run pytest --tb=short`                            | 86 passed, 0 failed, 0.41s              | ✓ PASS |

### Requirements Coverage

| Requirement | Description                                                                    | Status      | Evidence                                                                  |
|-------------|--------------------------------------------------------------------------------|-------------|---------------------------------------------------------------------------|
| NORM-01     | Accepts raw heterogeneous offers + source, returns normalized Jobs              | ✓ SATISFIED | `normalize_jobs(raw_offers, source) -> (list[Job], list[dict])`           |
| NORM-02     | Each Job gets stable id (hash of company + normalized title + location)         | ✓ SATISFIED | `stable_job_id` sha256 64-hex; deterministic; 64-char confirmed           |
| NORM-03     | Source parsing isolated in clearly-marked, adjustable mapper functions          | ✓ SATISFIED | `MAPPER_REGISTRY`; `arbeitnow_mapper` + `generic_mapper`; 8 AJUSTABLE banners; stub comments for jsearch/flybyapis |
| NORM-04     | Malformed offer doesn't crash batch — reports what failed                       | ✓ SATISFIED | Per-item try/except; errors list with index/source/error; confirmed live  |
| DEDUP-01    | Exact dedup by hash (normalized company + title)                                | ✓ SATISFIED | `exact_group` groups by NFD-normalized key; accent-invariant             |
| DEDUP-02    | Semantic dedup with BGE-M3 embeddings (title + company + first N words), cosine ≥ threshold | ✓ SATISFIED | `semantic_cluster` greedy cosine; `BgeM3Embedder` lazy-loaded in prod; `FakeEmbedder` in tests; `build_embed_text` constructs correct text |
| DEDUP-03    | Dedup preserves most complete description and saves alternative URLs            | ✓ SATISFIED | `merge_group`: `max(group, key=len(desc))`; `model_copy(update={"urls_alternativas": ...})` |
| QA-02       | Normalization tests per source                                                  | ✓ SATISFIED | 34 tests in `test_normalize.py`; arbeitnow + generic mappers exercised   |
| QA-03       | Dedup tests (exact + semantic duplicates; mocked embeddings)                    | ✓ SATISFIED | 8 e2e tests in `test_dedup.py`; 31 unit tests in `test_dedup_units.py`; FakeEmbedder always injected |

### Anti-Patterns Found

No blockers or warnings. Scan results:

- No TODO/FIXME/PLACEHOLDER/placeholder/coming soon/not implemented strings in `app/dedup/`
- No hardcoded credentials (ANTHROPIC_API_KEY, password, secret, token) in `app/dedup/`
- No `return null` / `return {}` / `return []` stubs — the only `return []` instances are legitimate empty-list guards (e.g., `if not jobs: return []`)
- AJUSTABLE comments in `mappers.py` are intentional documentation per NORM-03 (mark mappers as user-adjustable), not implementation gaps

**Note on `BgeM3Embedder` references in `test_dedup_units.py`:** The test file references `BgeM3Embedder` in one structural check (`test_bge_m3_tiene_metodo_embed_sin_instanciar_modelo`) that instantiates the class but explicitly does NOT call `.embed()`. This is safe — `BgeM3Embedder.__init__` sets `self._model = None` with no model download. The comment in the test confirms this intent. The plan's grep gate ("zero BgeM3Embedder in test file") was scoped to `test_dedup.py` (the QA-03 facade test), not `test_dedup_units.py` (the structural unit test). Both files pass.

### Human Verification Required

None. All success criteria are verifiable programmatically through the test suite and direct invocation.

**Note on BGE-M3 semantic quality (deferred manual follow-up):** Real semantic matching quality requires downloading the ~2.3 GB BAAI/bge-m3 model and running against real job offer data. This is documented in `02-VALIDATION.md` and is an intentional deferred validation step, not a gap in the implementation. The wiring is correct and tested; the model-quality check is a manual follow-up acceptable by design.

### Gaps Summary

No gaps. All 5 must-have truths are verified, all 9 requirements (NORM-01..04, DEDUP-01..03, QA-02, QA-03) are satisfied, and the full 86-test suite passes in 0.41s with zero failures.

---

_Verified: 2026-05-22T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
