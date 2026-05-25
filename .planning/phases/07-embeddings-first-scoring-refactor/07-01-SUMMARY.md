---
phase: "07-embeddings-first-scoring-refactor"
plan: "01"
subsystem: "scoring/tests"
tags: ["tdd", "red-phase", "scorer", "embedder", "guard-tests"]
dependency_graph:
  requires: []
  provides: ["tests/scoring/test_scorer_v2_guards.py"]
  affects: ["app/scoring/scorer.py"]
tech_stack:
  added: []
  patterns: ["TDD RED phase", "FakeEmbedder deferred import (Pitfall 7)"]
key_files:
  created:
    - tests/scoring/test_scorer_v2_guards.py
  modified: []
decisions:
  - "FakeEmbedder imported inside each test body (not at module top) — prevents torch load at collection time (Pitfall 7)"
  - "G-01 uses try/except TypeError to give a clear failure message about the signature change"
  - "G-02 uses monkeypatch.delenv to simulate absent OPENAI_API_KEY (no env contamination between tests)"
  - "G-04 creates an inline Job fixture (not a conftest fixture) to keep the test self-contained with explicit deal-breaker text"
  - "G-05 uses FakeEmbedder.vectors dict to pin cosine=1.0 between job title and ranking entry #1 title only; all other texts fall through to hash-based fallback"
metrics:
  duration: "84 seconds"
  completed_date: "2026-05-25"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
requirements_covered:
  - SCORE-09
  - SCORE-10
  - SCORE-11
  - SCORE-12
  - SCORE-13
  - QA-05
  - QA-07
---

# Phase 7 Plan 01: RED Guard Tests for Deterministic Scorer Contract Summary

**One-liner:** 5 RED guard tests that lock the new `score_job(job, user_profile, cv_profile, embedder, *, client=None)` contract, verifying deterministic sub-scores, embedder injection, and keyword-based deal-breaker detection — all fail against the current LLM-delegating scorer.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write RED guard tests for the new deterministic scorer contract | add7f7e | tests/scoring/test_scorer_v2_guards.py |

## Deviations from Plan

None — plan executed exactly as written. The 5 tests were created following the exact structure, import rules, and assertion patterns specified in the plan.

## Test Results (RED Phase — Expected)

```
tests/scoring/test_scorer_v2_guards.py FFFFF   [100%]
5 failed, 5 warnings in 0.40s
```

All 5 tests fail with `FAILED` status (not `ERROR`). Failure root causes:

| Test | Failure Reason |
|------|---------------|
| G-01 | Old scorer passes `user_profile` as `cv_profile` to `evaluar_ubicacion` (wrong positional arg order), triggers `AttributeError: 'CVProfile' object has no attribute 'preferencias_ubicacion'` — caught by `pytest.fail()` |
| G-02 | Same signature mismatch — current scorer calls LLM, no OpenAI key → falls through to same `AttributeError` |
| G-03 | Old scorer accepts 4th positional arg as `client=`, calls `build_instructor_client(None)`, raises `ValueError` but message doesn't contain "embedder" |
| G-04 | Old scorer doesn't do keyword deal-breaker check deterministically; delegates to LLM |
| G-05 | Old scorer uses LLM for ranking match, not embedder cosine |

**No torch leak:** `python -c "import tests.scoring.test_scorer_v2_guards"` produces no torch/sentence-transformers output.

## Guard Test Inventory

| ID | Assertion | Against Current Scorer |
|----|-----------|----------------------|
| G-01 | `score_job(job, user_profile, cv_profile, embedder)` — 4th positional arg | FAIL |
| G-02 | No `OPENAI_API_KEY` + `FakeEmbedder` → full valid `JobScore` with all 4 int sub-scores | FAIL |
| G-03 | `embedder=None` → `ValueError/TypeError` with "embedder" in message | FAIL |
| G-04 | Deal-breaker keyword in job text → `deal_breaker_hit=True` + `skip` with no LLM | FAIL |
| G-05 | `FakeEmbedder` cosine=1.0 against ranking #1 → `rango_puesto=1` + `encaje_puesto=100` | FAIL |

## Known Stubs

None — this plan creates only test code; no production stubs.

## Threat Flags

None — test-only file, no new network endpoints or auth paths introduced. FakeEmbedder import is inside test bodies per T-07-02 mitigation.

## Self-Check: PASSED

- [x] `tests/scoring/test_scorer_v2_guards.py` exists (319 lines)
- [x] Commit `add7f7e` exists: `git log --oneline | grep add7f7e` → confirmed
- [x] 5 tests collected, 5 FAILED (not ERROR)
- [x] No torch imported at collection time
- [x] `min_lines: 60` satisfied (319 lines)
- [x] `pattern: "score_job.*embedder"` satisfied (all 5 tests call `score_job(..., fake_embedder)`)
