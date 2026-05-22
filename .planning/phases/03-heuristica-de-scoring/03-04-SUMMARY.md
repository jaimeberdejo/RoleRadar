---
phase: 03-heuristica-de-scoring
plan: "04"
subsystem: scoring
tags: [anthropic, instructor, pydantic, llm, scoring, heuristic, tdd]

# Dependency graph
requires:
  - phase: 03-01
    provides: "UserProfile, CVProfile, LLMJobAssessment, JobScore schemas in app/models/schemas.py"
  - phase: 03-02
    provides: "encaje_puesto_desde_rango (ranking.py) + evaluar_ubicacion (location.py) deterministic layers"
  - phase: 03-03
    provides: "conftest.py fixtures: make_scoring_client, EXPECTED_ASSESSMENT, sample_cv_profile, sample_user_profile, Job fixtures"
  - phase: 01-parseo-de-cv
    provides: "app/cv/llm_client.py exact pattern (build_instructor_client + client.messages.create(response_model=...))"
provides:
  - "app/scoring/llm.py: build_instructor_client() + assess_job() LLM evaluation layer"
  - "app/scoring/scorer.py: score_job() 6-step orchestrator assembling full JobScore"
  - "app/scoring/__init__.py: public facade score_job, no app.dedup import"
  - "tests/scoring/test_llm.py: 4 tests verifying SCORE-07/SCORE-08"
  - "tests/scoring/test_scorer.py: QA-04 exhaustive suite (7 tests)"
affects: [04-endpoints-fastapi, 05-integracion]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "LLM judge with fixed system prompt (anti-inflation) + chain-of-thought field razonamiento"
    - "Prompt injection mitigation: offer text in XML-delimited <oferta> section, system prompt fixed string"
    - "6-step scoring orchestrator with deal-breaker override LAST (score_total stays honest)"
    - "Injectable LLM client pattern (client=None lazy factory, tests inject MagicMock)"
    - "Weighted sum score_total: round(clamp(encaje_puesto*p.puesto + skills*p.skills + ubicacion*p.ubicacion + seniority*p.seniority))"

key-files:
  created:
    - app/scoring/llm.py
    - app/scoring/scorer.py
    - app/scoring/__init__.py
    - tests/scoring/test_llm.py
    - tests/scoring/test_scorer.py
  modified: []

key-decisions:
  - "deal-breaker override is step 7 (LAST): score_total reflects true offer quality even when deal-broken; only recommendation→skip"
  - "system prompt is a fixed string without f-string interpolation of external content (T-03-08 anti prompt-injection)"
  - "offer text goes in XML-delimited <oferta> section of user message, not system prompt"
  - "_format_cv/_format_ranking/_format_job render readable text (not model_dump_json) for better LLM judgment (RESEARCH Open Q 2)"
  - "app/scoring/__init__.py must NOT import app.dedup to avoid BGE-M3/torch in scoring tests (Pitfall 7)"
  - "encaje_ubicacion computed deterministically before LLM call; LLM only handles skills/seniority/puesto/deal-breaker-texto"

patterns-established:
  - "Pattern: assess_job = single LLM entry point for scoring; Fase 5 wraps it with Langfuse"
  - "Pattern: _banda(score) pure function for recommendation bands; deal-breaker overrides after"
  - "Pattern: TDD with injectable MagicMock client — no patch(), no real API calls"

requirements-completed: [SCORE-01, SCORE-04, SCORE-05, SCORE-06, SCORE-07, SCORE-08, QA-04]

# Metrics
duration: 5min
completed: 2026-05-22
---

# Phase 3 Plan 04: LLM Assessment Layer + Scoring Orchestrator Summary

**Hybrid scoring heuristic: assess_job() using Instructor+Anthropic with fixed honest system prompt + score_job() 6-step orchestrator combining deterministic layers (location, ranking decay, weighted sum, bands) with LLM judgment (skills, seniority, puesto, deal-breakers), deal-breaker override applied last to preserve honest score_total**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-22T02:08:34Z
- **Completed:** 2026-05-22T02:13:07Z
- **Tasks:** 2
- **Files modified:** 5 created

## Accomplishments

- `app/scoring/llm.py`: `build_instructor_client()` injectable factory + `assess_job()` calling the LLM with `response_model=LLMJobAssessment`, model from `ANTHROPIC_MODEL_SCORING` env (default `claude-sonnet-4-6`), `max_retries=2`; system prompt fixed string prohibiting score inflation; offer in XML `<oferta>` section (anti prompt-injection T-03-08); `_format_cv/_format_ranking/_format_job` helpers render readable text for LLM judgment
- `app/scoring/scorer.py`: `score_job()` 6-step orchestrator — evaluar_ubicacion (deterministic) → assess_job (LLM) → encaje_puesto_desde_rango (decay) → score_total weighted sum → recommendation bands → deal-breaker override LAST; assembles full `JobScore` with all fields from assessment propagated unchanged
- `app/scoring/__init__.py`: public facade `score_job`, no `app.dedup` import (Pitfall 7)
- QA-04 exhaustive tests: 7 scorer tests + 4 LLM tests = 11 new tests; 40 scoring tests total (127 suite total); no regressions; all pass in 0.46s

## Task Commits

1. **Task 1: assess_job LLM layer (SCORE-07, SCORE-08)** - `8cea9cd` (feat)
2. **Task 2: scorer.py orchestrator + facade + QA-04** - `4b9106a` (feat)

**Plan metadata:** (pending final commit)

_Note: Both tasks used TDD — tests written first (RED), then implementation (GREEN)._

## Files Created/Modified

- `app/scoring/llm.py` - LLM evaluation layer: build_instructor_client() + assess_job() + prompt helpers
- `app/scoring/scorer.py` - 6-step scoring orchestrator: score_job() + _banda()
- `app/scoring/__init__.py` - Public facade: score_job, no app.dedup dependency
- `tests/scoring/test_llm.py` - 4 tests: response_model, model env, max_retries, prompt context (SCORE-08)
- `tests/scoring/test_scorer.py` - 7 tests: QA-04 exhaustive suite covering all heuristic cases

## Decisions Made

- **deal-breaker override LAST (step 7):** `score_total` reflects true quality even for deal-broken offers, enabling future analytics ("this offer would have been 85 if not for location"). Only `recommendation` is forced to `skip`, not the score.
- **Fixed system prompt (T-03-08):** system prompt is a string literal without f-string interpolation of any external content. The offer text goes in the user message `<oferta>` XML section. This prevents prompt injection via malicious job descriptions.
- **Readable text format over JSON:** `_format_cv()`, `_format_ranking()`, `_format_job()` render structured text (not `model_dump_json()`) per RESEARCH Open Q 2 — text format produces better LLM judgment results.
- **No dedup import in scoring:** `app/scoring/__init__.py` and `app/scoring/scorer.py` never import `app.dedup`. The scorer receives already-deduplicated `Job` objects from Fase 2. This keeps scoring tests fast (0.46s for 40 tests vs 30s+ if BGE-M3 loaded).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Threat Surface Scan

No new network endpoints or auth paths introduced in this plan. The security mitigations from the threat model were implemented as designed:
- T-03-08: system prompt fixed string, offer in XML-delimited `<oferta>` section
- T-03-09: `ANTHROPIC_API_KEY` never referenced in code (read by Anthropic SDK from env)
- T-03-01: `Field(ge=0, le=100)` in `LLMJobAssessment` + `max_retries=2` + `max(0, min(100, round(raw)))` clamp
- T-03-10: `recommendation` is 100% deterministic (bands + override); `LLMJobAssessment` has no `recommendation` field

## User Setup Required

None - tests use mock LLM (zero real API calls). Real scoring requires `ANTHROPIC_API_KEY` in `.env` (already documented in `.env.example`).

## Next Phase Readiness

- Phase 3 scoring heuristic complete: `score_job(job, cv_profile, user_profile) -> JobScore` ready to consume
- Fase 4 (endpoints): implement `/jobs/score` and `/jobs/process` using `score_job()` + persistence
- Fase 5 (integration): wrap `assess_job()` with Langfuse for observability (OBS-02, noted in docstring)
- `app.scoring` exposes clean public facade with no heavy model dependencies

## Self-Check

- app/scoring/llm.py: FOUND
- app/scoring/scorer.py: FOUND
- app/scoring/__init__.py: FOUND
- tests/scoring/test_llm.py: FOUND
- tests/scoring/test_scorer.py: FOUND

---
*Phase: 03-heuristica-de-scoring*
*Completed: 2026-05-22*
