---
phase: 07-embeddings-first-scoring-refactor
fixed_at: 2026-05-25T00:00:00Z
review_path: .planning/phases/07-embeddings-first-scoring-refactor/07-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
deferred: 3
---

# Phase 7: Code Review Fix Report

**Fixed at:** 2026-05-25
**Source review:** `.planning/phases/07-embeddings-first-scoring-refactor/07-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (CR + WR): 6
- Fixed: 6
- Skipped: 0
- Deferred (INFO): 3 (IN-01, IN-02, IN-03 — per instructions, see Deferred section)

**Final test suite:** 238 passed, 0 failures
**No-API-key path:** 72 deterministic tests pass with `OPENAI_API_KEY=""` — confirmed no LLM import at collection time

---

## Fixed Issues

### CR-01: ZeroDivisionError when job description contains "0 years"

**Files modified:** `app/scoring/seniority.py`, `tests/scoring/test_seniority.py`
**Commit:** `f7a720e`
**Applied fix:** Added an `if anos_requeridos == 0.0:` guard immediately before the
`anios_candidato / anos_requeridos` division in `evaluar_seniority` step 3. When the
parsed required years is 0 (e.g. "0-2 years experience preferred"), the function now
returns the same generous no-signal path as when no years are found (encaje_seniority=75,
anos_requeridos=None). Added three regression tests: `test_zero_years_requirement_no_crash`,
`test_zero_plus_years_no_crash`, and `test_zero_years_treated_as_no_signal_returns_75`.

---

### CR-02: conftest.py forces openai+instructor import for ALL tests

**Files modified:** `tests/conftest.py`
**Commit:** `24ba5ab`
**Applied fix:** Replaced the module-level `from app.scoring.llm import LLMEnrichment`
with a lazy proxy pattern. `EXPECTED_ENRICHMENT` is now a `_LazyEnrichment` instance that
defers the `LLMEnrichment` import (and transitively openai+instructor) until the first
attribute access. The public API (`EXPECTED_ENRICHMENT.reasons_for`, etc. and
`make_enrichment_client`) is fully backward-compatible with existing callers in
`test_scorer.py`. Verified that conftest.py collection does NOT import openai at module
level; the deferred import only fires when LLM-specific tests actually run.

---

### WR-01: "sin_skills" fallback produces semantically wrong encaje_skills

**Files modified:** `app/scoring/scorer.py`
**Commit:** `333fe9b`
**Applied fix:** Added an early-return check in `score_job` (PASO 3) after
`cv_text = _build_cv_text(cv_profile)`. When `cv_text == "sin_skills"` (the sentinel
returned when the CVProfile has no skills/technologies/domains), the function now sets
`encaje_skills = 50` (neutral) with a WARNING log, instead of passing the literal string
to `encaje_skills_por_coseno`. This is consistent with the `seniority.py` None→50 pattern
and avoids embedding a semantically unrelated string that would wrongly penalise every job.

---

### WR-02: NaN cosine bypasses umbral threshold (false positive match)

**Files modified:** `app/scoring/puesto_match.py`, `app/scoring/skills_match.py`
**Commit:** `39c62c4`
**Applied fix:** Added `import math` and NaN guards in both files:
- `puesto_match.py`: threshold check is now `if math.isnan(best_cosine) or best_cosine < umbral`
  — NaN is treated as below-threshold, returning `("fuera de ranking", None)`.
- `skills_match.py`: added `if math.isnan(cosine): return 0` before the
  `int(round(max(0.0, min(1.0, cosine)) * 100))` computation — prevents `ValueError`
  from `int(round(NaN))` that would crash the batch.

---

### WR-03: CV/ranking fields not XML-escaped in LLM prompt

**Files modified:** `app/scoring/llm.py`
**Commit:** `daceb9d`
**Applied fix:** Applied `_escape_for_prompt()` to all string field values in
`_format_cv` and `_format_ranking`. Specifically:
- `_format_cv`: escapes `exp.empresa`, `exp.rol`, `exp.duracion`, each technology,
  each skill, each domain, each logro, `form.titulo`, `form.institucion`.
- `_format_ranking`: escapes `puesto.titulo` and each synonym.
This matches the existing escaping already applied in `_format_job` (CR-03) and closes
the structural injection risk for CV and ranking data inserted into XML-delimited prompt
sections.

---

### WR-04: FakeEmbedder imported at module level in test files

**Files modified:** `tests/scoring/test_puesto_match.py`, `tests/scoring/test_skills_match.py`
**Commit:** `ca09166`
**Applied fix:** Removed the module-level `from app.dedup.embedder import FakeEmbedder`
from both test files. Each test method that needs `FakeEmbedder` now imports it inside
the function body with a comment `# deferred — Pitfall 7 (WR-04)`. This matches the
pattern used in `test_scorer.py` and `test_scorer_v2_guards.py` and prevents
torch/sentence-transformers from loading at pytest collection time.

---

## Deferred Issues (INFO — not fixed per instructions)

### IN-01: test_llm.py imports unused LLMJobAssessment

**File:** `tests/scoring/test_llm.py:24`
**Reason:** Deferred — trivial dead import, no runtime impact.

### IN-02: CV_SKILLS_TEXT_MAX_TOKENS is a character count, not a token count

**File:** `app/scoring/skills_match.py:63`
**Reason:** Deferred — cosmetic naming issue; the docstring already clarifies the unit.

### IN-03: ranking.py does not guard against maximo < suelo misconfiguration

**File:** `app/scoring/ranking.py:59`
**Reason:** Deferred — config invariant; not hit in practice with default values.

---

## Verification

**Full suite:** `uv run pytest` → 238 passed, 0 failures, 5 deprecation warnings (unrelated to this project)

**No-API-key path:** `OPENAI_API_KEY="" uv run pytest tests/scoring/test_deal_breaker.py tests/scoring/test_seniority.py tests/scoring/test_ranking.py tests/scoring/test_location.py` → 72 passed — no LLM or openai import triggered at collection or test execution time.

---

_Fixed: 2026-05-25_
_Fixer: Claude Sonnet 4.6 (gsd-code-fixer)_
_Iteration: 1_
