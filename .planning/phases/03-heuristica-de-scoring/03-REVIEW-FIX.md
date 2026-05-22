---
phase: 03-heuristica-de-scoring
fixed_at: 2026-05-22T05:30:00Z
review_path: .planning/phases/03-heuristica-de-scoring/03-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 10
skipped: 1
status: partial
---

# Phase 03: Code Review Fix Report

**Fixed at:** 2026-05-22T05:30:00Z
**Source review:** `.planning/phases/03-heuristica-de-scoring/03-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 11
- Fixed: 10
- Skipped: 1 (IN-01 — out-of-bounds rango_puesto upper limit, advisory only)

## Fixed Issues

### CR-01: `rango_puesto=0` from LLM crashes `score_job`

**Files modified:** `app/scoring/ranking.py`, `app/models/schemas.py`, `tests/scoring/test_ranking.py`
**Commit:** `585d0b3`
**Applied fix:**
- `ranking.py`: added `min(maximo, max(suelo, score))` upper clamp so any positive `rango` is bounded by `maximo`. Added `ValueError` guard for `rango < 1` (also satisfies WR-02, see below).
- `schemas.py`: added `ge=1` to `LLMJobAssessment.rango_puesto` so instructor/Pydantic catches a zero or negative value from the LLM before it reaches the decay function.
- `test_ranking.py`: added `test_rango_no_positivo_lanza` parametrized over `[0, -1, -100]` (also satisfies IN-03 ranking coverage gap).

---

### CR-02: Silent data loss when both location and LLM deal-breakers fire

**Files modified:** `app/scoring/scorer.py`, `tests/scoring/test_scorer.py`
**Commit:** `12bc085`
**Applied fix:**
- `scorer.py`: replaced `deal_breaker_loc or assessment.deal_breaker_cual_texto` with list-join that collects both non-empty reasons: `"; ".join([p for p in (deal_breaker_loc, assessment.deal_breaker_cual_texto) if p])`.
- `test_scorer.py`: added `test_ambos_deal_breakers_reportados` asserting that `"Madrid"` (location) and `"exige 5+ años"` (LLM text) both appear in `deal_breaker_cual` (also satisfies IN-03 combined scenario gap).

---

### CR-03: Prompt injection via job description in XML-delimited prompt

**Files modified:** `app/scoring/llm.py`, `tests/scoring/test_llm.py`
**Commit:** `2f54fa3`
**Applied fix:**
- `llm.py`: added `_escape_for_prompt(text)` using stdlib `html.escape(text, quote=False)` (no new deps). Applied to `title`, `company`, `location`, and `description` fields inside `_format_job()`.
- `test_llm.py`: added `test_prompt_escapa_contenido_oferta` that creates a job with `</oferta>` in both company and description, and asserts the prompt contains `&lt;/oferta&gt;` (escaped) and `</oferta>` exactly once (the structural delimiter).

---

### WR-01: `LLMJobAssessment` allows inconsistent `deal_breaker_cual_texto` state

**Files modified:** `app/models/schemas.py`
**Commit:** `20b1203`
**Applied fix:**
- Added `@model_validator(mode="after")` `check_deal_breaker_consistency` on `LLMJobAssessment` that coerces `deal_breaker_cual_texto = None` when `deal_breaker_hit_texto=False`. Prevents the contradictory state from reaching `scorer.py` or downstream consumers.

---

### WR-02: `encaje_puesto_desde_rango` has no input guard for non-positive `rango`

**Files modified:** `app/scoring/ranking.py`
**Commit:** `585d0b3` (bundled with CR-01)
**Applied fix:**
- Added `if rango < 1: raise ValueError(...)` guard before the formula. The defensive check applies even when called outside the LLM path (pure utility function contract). Combined with the `ge=1` schema constraint from CR-01.

---

### WR-03: Docstring of `score_job` has step numbering mismatch

**Files modified:** `app/scoring/scorer.py`
**Commit:** `c0f5d8e`
**Applied fix:**
- Updated docstring from "6 pasos" to "7 pasos" and inserted "Paso 1: Cliente lazy" to align the step-by-step description with the 7 code-comment steps. Paso numbers now match exactly between docstring and code comments.

---

### WR-04: `_ciudad_aceptada` substring match can produce false positives

**Files modified:** `app/scoring/location.py`
**Commit:** `63ff36c`
**Applied fix:**
- Added `import re` and changed `_ciudad_aceptada` to use `re.search(r"\b" + re.escape(_normalize_city(c)) + r"\b", loc_norm)` for word-boundary matching.
- Verified "Oria" does NOT match "Victoria" and "Barcelona" DOES match "Barcelona, España". All 13 existing location tests pass unchanged.

---

### WR-05: `load_user_profile` default path relative to CWD

**Files modified:** `app/config/loader.py`, `tests/scoring/test_loader.py`
**Commit:** `d706f64`
**Applied fix:**
- `loader.py`: added `_PROJECT_ROOT = Path(__file__).parent.parent.parent` at module level. Changed signature to `path: str | Path | None = None`. When `path is None`, resolves to `_PROJECT_ROOT / "data" / "profile.yaml"` (CWD-independent).
- `test_loader.py`: updated `test_carga_perfil_real` to use `_PROJECT_ROOT / "data" / "profile.yaml"` explicitly and added `pytest.skip` guard when `data/profile.yaml` is absent (e.g., in CI/worktrees without untracked `data/`).

---

### IN-02: Score-step comment says `round(clamp(...))` but code does `clamp(round(...))`

**Files modified:** `app/scoring/scorer.py`
**Commit:** `b035755`
**Applied fix:**
- Corrected the inline comment from `round(clamp(...))` to `clamp(round(...), 0, 100)` to accurately describe the actual evaluation order: `max(0, min(100, round(raw)))`.

---

### IN-03: Test coverage gaps — no test for combined deal-breaker and rango<=0

**Files modified:** `tests/scoring/test_scorer.py`, `tests/scoring/test_ranking.py`
**Commit:** `12bc085` (combined deal-breaker test) and `585d0b3` (rango<=0 test)
**Applied fix:**
- `test_scorer.py`: `test_ambos_deal_breakers_reportados` covers the combined location+LLM deal-breaker scenario.
- `test_ranking.py`: `test_rango_no_positivo_lanza` covers `rango in [0, -1, -100]` raising `ValueError`.

---

## Skipped Issues

### IN-01: `LLMJobAssessment.rango_puesto` — no upper bound on ranking position

**File:** `app/models/schemas.py:183-186`
**Reason:** Advisory/low-risk. The decay function floors arbitrarily large `rango` values to `suelo=20` correctly — no crash, no incorrect output. Adding `le=len(ranking_puestos)` requires context unavailable at schema definition time. Documenting in REVIEW-FIX.md as a known informational item for future consideration.
**Original issue:** LLM could return `rango_puesto=999` for a 4-entry ranking; the `ge=1` added by CR-01 addresses the dangerous lower bound but not an upper bound. No crash path exists.

---

## Final Verification

- `uv run pytest`: **131 passed, 1 skipped** (skip is `test_carga_perfil_real` in worktree where untracked `data/` is absent — passes in main project)
- `uv run python -c "import sys; import app.scoring; assert 'torch' not in sys.modules"`: **passed** (torch-free)

---

_Fixed: 2026-05-22T05:30:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
