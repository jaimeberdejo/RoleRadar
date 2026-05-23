---
phase: 03-heuristica-de-scoring
plan: "01"
subsystem: scoring
tags: [schemas, pydantic, testing, fixtures, llm-assessment]
dependency_graph:
  requires: []
  provides:
    - app.models.schemas.LLMJobAssessment
    - app.models.schemas.PesosScoring.check_sum
    - tests.scoring (package)
    - tests.conftest.EXPECTED_ASSESSMENT
    - tests.conftest.make_scoring_client
    - tests.conftest.mock_scoring_client
    - tests.conftest.sample_cv_profile
    - tests.conftest.sample_user_profile
    - tests.conftest.sample_job_remote
    - tests.conftest.sample_job_onsite_barcelona
    - tests.conftest.sample_job_onsite_madrid
    - tests.conftest.sample_job_fuera_ranking
  affects:
    - app/models/schemas.py
    - tests/conftest.py
tech_stack:
  added: []
  patterns:
    - Pydantic v2 model_validator(mode="after") for float-tolerant sum validation
    - LLMJobAssessment with razonamiento first field (chain-of-thought forcing)
    - MagicMock pattern for LLM client injection in scoring tests
key_files:
  created:
    - tests/scoring/__init__.py
  modified:
    - app/models/schemas.py
    - tests/conftest.py
decisions:
  - "razonamiento field placed first in LLMJobAssessment to force chain-of-thought before scores (SCORE-07)"
  - "LLMJobAssessment deliberately excludes score_total/encaje_puesto/encaje_ubicacion/recommendation to enforce deterministic ownership (T-03-02)"
  - "PesosScoring uses abs(total-1.0) < 1e-6 instead of == 1.0 to handle IEEE 754 float precision (0.35+0.30+0.20+0.15 = 0.9999999999999999)"
  - "deal_breaker_cual_texto field name (not deal_breaker_cual) to avoid naming conflict with JobScore.deal_breaker_cual"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
  files_created: 1
---

# Phase 03 Plan 01: LLMJobAssessment Schema + PesosScoring Validator + Scoring Fixtures Summary

Wave 0 of the scoring phase: LLMJobAssessment schema with chain-of-thought field ordering, float-tolerant PesosScoring validator, and test infrastructure covering remote/onsite-BCN/onsite-MAD/out-of-ranking job fixtures.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | LLMJobAssessment + PesosScoring.check_sum | a7a3f97 | app/models/schemas.py |
| 2 | tests/scoring/ + scoring fixtures in conftest | 0d93098 | tests/scoring/__init__.py, tests/conftest.py |

## What Was Built

### Task 1: LLMJobAssessment + PesosScoring.check_sum

Added `LLMJobAssessment` to `app/models/schemas.py` with 11 fields. The schema represents exclusively what the LLM evaluates — fields requiring free-text comprehension. Deterministic fields (`score_total`, `encaje_puesto`, `encaje_ubicacion`, `recommendation`) are architecturally absent, making it impossible for the LLM to influence scores that belong to the deterministic layer.

Field ordering is intentional: `razonamiento` is first, forcing the LLM to articulate its reasoning before producing numeric scores. This is the chain-of-thought pattern recommended for honest scoring (SCORE-07).

Also added `@model_validator(mode="after")` to `PesosScoring` using `abs(total - 1.0) < 1e-6` instead of `== 1.0`. IEEE 754 float arithmetic causes `0.35 + 0.30 + 0.20 + 0.15` to evaluate to `0.9999999999999999`, so equality comparison would incorrectly reject valid default weights.

### Task 2: tests/scoring/ + Scoring Fixtures

Created `tests/scoring/__init__.py` (empty package). Extended `tests/conftest.py` with:

- `EXPECTED_ASSESSMENT`: module-level `LLMJobAssessment` constant with rango_puesto=1, AI Engineer, realistic skills/seniority scores, and honest reasons_against (Kubernetes not in CV).
- `make_scoring_client(assessment)`: helper returning a `MagicMock` with `.messages.create.return_value = assessment`. Identical pattern to existing `mock_llm_client`.
- `mock_scoring_client` fixture (function scope) returning `make_scoring_client(EXPECTED_ASSESSMENT)`.
- `sample_cv_profile`: Python/LLMs/FastAPI, 2y AI Engineer at Acme Corp.
- `sample_user_profile`: full coherent profile matching `data/profile.yaml` — Barcelona, remote preferred, 4 real ranking positions with synonyms, deal_breakers, PesosScoring defaults.
- 4 `Job` fixtures covering all scoring location branches:
  - `sample_job_remote`: AI Engineer, remote — tests the remote→high encaje_ubicacion branch.
  - `sample_job_onsite_barcelona`: AI Engineer, onsite+BCN — tests onsite-accepted-city branch.
  - `sample_job_onsite_madrid`: AI Engineer, onsite+MAD — tests onsite-not-accepted + deal-breaker candidate.
  - `sample_job_fuera_ranking`: Frontend Designer, remote — tests rango_puesto=None → suelo branch.

## Verification

All 87 pre-existing tests pass after changes (no regression). LLMJobAssessment and make_scoring_client verified programmatically.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — this plan creates schema and fixture infrastructure only, no data-rendering components.

## Threat Flags

None — no new network endpoints, auth paths, or trust boundaries introduced.

## Self-Check: PASSED

- `app/models/schemas.py` — verified (LLMJobAssessment importable, razonamiento first, no prohibited fields, PesosScoring rejects invalid sums)
- `tests/scoring/__init__.py` — verified (file exists)
- `tests/conftest.py` — verified (EXPECTED_ASSESSMENT, make_scoring_client, all 6 fixtures importable)
- Commits a7a3f97, 0d93098 — verified in git log
- 87 tests pass — verified
