---
phase: "07-embeddings-first-scoring-refactor"
plan: "04"
subsystem: "scoring"
tags: ["deal-breaker", "deterministic", "keyword-match", "nfd-normalization", "tdd"]
dependency_graph:
  requires:
    - "app/models/schemas.py (UserProfile.deal_breakers)"
  provides:
    - "app/scoring/deal_breaker.py — detectar_deal_breaker() + DealBreakerResult"
  affects:
    - "app/scoring/scorer.py (Wave 2 — will call detectar_deal_breaker to set recommendation=skip)"
tech_stack:
  added: []
  patterns:
    - "NFD + casefold normalization (stdlib unicodedata) — mirrors scoring/location.py convention"
    - "TDD RED/GREEN with pytest (16 unit tests)"
    - "Dataclass for structured return type (DealBreakerResult)"
key_files:
  created:
    - app/scoring/deal_breaker.py
    - tests/scoring/test_deal_breaker.py
  modified: []
decisions:
  - "Substring match (not word-boundary regex): deal_breakers are natural-language phrases containing +, numbers, spaces — escaping \\b for these is fragile. Normalized substring is simpler and sufficient."
  - "NFD helper replicated (not imported from location.py): avoids cross-module coupling and the transitive torch import chain (Pitfall 7)."
  - "Multiple hits joined with '; ': consistent with scorer.py CR-02 multi-value pattern."
  - "DealBreakerResult dataclass (not NamedTuple): mutable and explicit field names for scorer.py consumer readability."
  - "test_no_app_dedup_import checks import lines only (not full source text): prevents false positive when docstring mentions 'app.dedup' in explanatory comments."
metrics:
  duration: "~8 minutes"
  completed: "2026-05-25"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
  tests_added: 16
  tests_total: 179
---

# Phase 7 Plan 04: Deal-breaker Deterministic Keyword Matcher Summary

**One-liner:** Pure-Python NFD-normalized substring matcher that detects deal_breaker hits from UserProfile.deal_breakers against job text with no LLM or embeddings required.

## What Was Built

`app/scoring/deal_breaker.py` — a standalone deterministic module that implements SCORE-13: detect deal_breaker hits without any OpenAI/LLM call.

**Public API:**
- `DealBreakerResult(hit: bool, cual: str | None)` — dataclass carrying the detection result
- `detectar_deal_breaker(job_text: str, deal_breakers: list[str]) -> DealBreakerResult` — the matcher

**Algorithm:**
1. Guard: empty `job_text` or empty `deal_breakers` → immediate `hit=False, cual=None`
2. Normalize job_text once via `_normalizar()` (NFD + casefold)
3. For each deal_breaker in the list: normalize and check if `db_norm in job_norm`
4. Collect all matches; join with `"; "` if multiple; log at INFO on hit

**Normalization detail:** `unicodedata.normalize("NFD", text.lower().strip())` then filter `category(c) != "Mn"` — identical convention to `scoring/location.py._normalize_city`. Replicated (not imported) to avoid cross-module coupling.

## TDD Gate Compliance

1. RED commit `31f74e5` — 16 failing tests (ModuleNotFoundError on missing module)
2. GREEN commit `ceabbf2` — implementation + test fix; 179 tests pass

## Test Coverage

16 tests in `tests/scoring/test_deal_breaker.py`:
- Basic hit/no-hit
- Case-insensitive matching
- English text does not match Spanish deal_breaker
- Empty job_text → no hit
- Empty deal_breakers list → no hit
- Whitespace-only job_text → no hit
- Multiple hits → joined with `"; "`
- Multiple deal_breakers, only one fires → only that one in `cual`
- Accented char in job text matches unaccented deal_breaker
- Accented char in deal_breaker matches unaccented job text
- Spanish tilde normalization (`años` ↔ `anos`)
- Return type is always `DealBreakerResult`
- No-hit result has `cual=None` (not empty string)
- No `app.dedup` import statements in source (torch avoidance)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_no_app_dedup_import false-positive in full test suite**
- **Found during:** Task 1, GREEN phase — test passed in isolation but failed when running full suite
- **Issue:** The test checked `"app.dedup" not in source` against the entire module source, which includes the docstring comment "No importa app.dedup (torch/BGE-M3 avoidance...)". This caused a false positive when the string appeared in the docstring.
- **Fix:** Changed the test to only inspect lines starting with `import` or `from`, skipping docstrings/comments. This is the correct intent: verify no import *statement* references app.dedup.
- **Files modified:** `tests/scoring/test_deal_breaker.py`
- **Commit:** ceabbf2

## Integration Note for Wave 2 (scorer.py)

The scorer should call `detectar_deal_breaker` as:
```python
job_text = f"{job.title} {job.description}"
db_result = detectar_deal_breaker(job_text, user_profile.deal_breakers)
if db_result.hit:
    recommendation = Recommendation.skip
    deal_breaker_hit = True
    deal_breaker_cual = db_result.cual
```
The deal-breaker override must come *after* numeric score computation (last-override pattern from CONTEXT.md) so `score_total` remains honest.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Module is pure in-memory computation.

## Self-Check: PASSED

- `app/scoring/deal_breaker.py` exists: FOUND
- `tests/scoring/test_deal_breaker.py` exists: FOUND
- Commit `31f74e5` (RED): FOUND
- Commit `ceabbf2` (GREEN): FOUND
- 179 tests pass, 0 failures
