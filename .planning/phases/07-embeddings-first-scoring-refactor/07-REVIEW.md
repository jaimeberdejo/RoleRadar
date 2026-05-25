---
phase: 07-embeddings-first-scoring-refactor
reviewed: 2026-05-25T00:00:00Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - app/scoring/scorer.py
  - app/scoring/puesto_match.py
  - app/scoring/skills_match.py
  - app/scoring/seniority.py
  - app/scoring/deal_breaker.py
  - app/scoring/llm.py
  - tests/scoring/test_scorer.py
  - tests/scoring/test_scorer_v2_guards.py
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: fixed
fixed_at: 2026-05-25T00:00:00Z
fix_report: 07-REVIEW-FIX.md
---

# Phase 7: Code Review Report — Embeddings-First Scoring Refactor

**Reviewed:** 2026-05-25
**Depth:** deep (cross-file analysis, call-chain tracing, edge-case probing)
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The Phase 7 refactor successfully achieves its core architectural goal: all four numeric
sub-scores are now computed deterministically without an OpenAI dependency, the embedder is
correctly injected (duck-typed, TYPE_CHECKING guard), the deferred `openai` import in
`scorer.py` is properly gated, and the deal-breaker override correctly fires last while
preserving `score_total` as an honest number. The heuristic rules from CLAUDE.md (ranking as
weight not filter, seniority never auto-skips, deal-breakers as the only hard filter) are
correctly implemented in logic.

Two BLOCKER issues were found through execution tracing:

1. `seniority.py` crashes with `ZeroDivisionError` when a job description mentions
   "0-2 years" or "0 years" (a real pattern for entry-level and internship listings).
   The regex correctly captures `0` as the lower bound, but the subsequent
   `anios_candidato / anos_requeridos` is not guarded against division by zero.

2. `conftest.py` imports `LLMEnrichment` from `app.scoring.llm` at module level (line 301),
   which pulls in `import instructor` and `from openai import OpenAI` at pytest collection
   time. This means `openai` and `instructor` must be installed to collect ANY test —
   including `test_deal_breaker.py` and `test_seniority.py` which have zero LLM
   dependency. This defeats the stated goal of a fully-functional no-LLM path and breaks
   CI environments without OpenAI installed.

Four WARNING issues cover: the `"sin_skills"` fallback in `_build_cv_text` producing
semantically wrong scores for empty CVProfiles, NaN propagation through cosine comparison
in `puesto_match.py` creating false positive matches, missing XML escaping on CV and
ranking data inserted into the LLM prompt, and a `test_llm.py` dead import of the
deprecated `LLMJobAssessment` schema.

---

## Critical Issues

### CR-01: ZeroDivisionError when job description contains "0 years"

**File:** `app/scoring/seniority.py:236`

**Issue:** `_parse_anos_requeridos` correctly parses the lower bound of ranges like
"0-2 years" (common for entry-level/internship listings) and "0+ years", returning
`0.0`. In `evaluar_seniority` step 3, the code then executes:

```python
ratio = anios_candidato / anos_requeridos  # ZeroDivisionError when anos_requeridos == 0.0
```

There is no guard for `anos_requeridos == 0`. When `anios_candidato` is not `None`
(i.e., the CV was parsed and has experience data) and the description contains "0-2
years experience" (a real pattern for junior roles and internships), `score_job` raises
an unhandled exception that propagates through `scorer.py` and crashes the batch
processor. This violates the CLAUDE.md requirement that "una oferta mal formada no
tumbe el batch entero".

Verified: `_RE_ANOS.search("0-2 years experience").group(1) == "0"` — the regex does
capture 0 in this real-world pattern.

**Fix:** Treat `anos_requeridos == 0` as "no meaningful requirement" and fall back to
the generous-no-signal path. Add immediately before the ratio computation at line 236:

```python
if anos_requeridos == 0.0:
    logger.debug(
        "evaluar_seniority: anos_requeridos=0 → treating as no signal "
        "(anios_candidato=%.1f)",
        anios_candidato,
    )
    return SeniorityResult(
        encaje_seniority=75,
        seniority_nota="Sin requisito de años explícito en la oferta (0 interpretado como sin requisito)",
        anos_requeridos=None,
    )
```

No new test exists for this path — add one:

```python
def test_zero_years_requirement_no_crash():
    r = evaluar_seniority("0-2 years experience preferred", 3.0)
    assert 0 < r.encaje_seniority <= 100  # must not raise ZeroDivisionError
```

---

### CR-02: conftest.py forces openai+instructor install for ALL tests

**File:** `tests/conftest.py:301`

**Issue:** The shared conftest imports `LLMEnrichment` from `app.scoring.llm` at module
level:

```python
from app.scoring.llm import LLMEnrichment  # noqa: E402 — after make_scoring_client
```

`app.scoring.llm` contains at its top level:

```python
import instructor
from openai import OpenAI
```

These are unconditional module-level imports. Because `conftest.py` is loaded by pytest
before any test file, this forces `openai` and `instructor` to be installed for the
entire test suite — including `test_deal_breaker.py` and `test_seniority.py` which have
zero LLM dependency and are designed to work without OpenAI.

This directly contradicts the architecture requirement: "all 4 numeric sub-scores must
be produced without an OpenAI call so the heuristic works even when `OPENAI_API_KEY` is
absent" (CONTEXT.md SCORE-12). The no-LLM path works at runtime, but the test suite
cannot verify it in an environment without the OpenAI SDK installed.

**Fix:** Move the LLM-specific fixtures and constants into a dedicated conftest or a
separate helper module, keeping the import deferred:

```python
# In tests/conftest.py — replace the module-level import:
# BEFORE:
# from app.scoring.llm import LLMEnrichment  # noqa: E402

# AFTER: keep EXPECTED_ENRICHMENT and make_enrichment_client deferred
def _get_llm_enrichment_class():
    from app.scoring.llm import LLMEnrichment  # deferred
    return LLMEnrichment

# Or move the LLM fixture block to tests/scoring/conftest.py
# so non-LLM tests collect without openai installed.
```

Alternatively, create `tests/scoring/conftest_llm.py` and import it only in LLM-related
test files.

---

## Warnings

### WR-01: _build_cv_text fallback "sin_skills" produces semantically wrong encaje_skills

**File:** `app/scoring/scorer.py:84`

**Issue:** When a `CVProfile` has no `skills_tecnicas`, no `experiencia` with
`tecnologias`, and no `dominios`, `_build_cv_text` returns the literal string
`"sin_skills"`. This string is then passed to `encaje_skills_por_coseno`, which
embeds it and computes cosine similarity against the job description.

The BGE-M3 embedding of the Spanish phrase "sin_skills" is semantically unrelated to
any technical job description, so the cosine similarity will be very low (≈ 0-15),
resulting in an `encaje_skills` score that incorrectly penalises every job offer as if
the candidate had no matching skills, when in reality the CV simply wasn't parsed yet.

The correct behavior — consistent with how `seniority.py` handles `anios_candidato=None`
— is to return a neutral score (50) rather than a misleadingly low one.

**Fix:** Return early with a neutral score when cv_text is the fallback sentinel:

In `scorer.py`, after `cv_text = _build_cv_text(cv_profile)`:

```python
if cv_text == "sin_skills":
    encaje_skills = 50  # neutral — CV not parsed or no skills extracted
    logger.warning(
        "score_job: CVProfile sin skills/tecnologías → encaje_skills=50 (neutral). "
        "Re-parsea el CV para obtener un score real."
    )
else:
    encaje_skills = encaje_skills_por_coseno(cv_text, job.description or "", embedder)
```

Or, more cleanly, have `_build_cv_text` return `None` and check for `None` in the caller.

---

### WR-02: NaN cosine bypasses umbral threshold in puesto_match.py (false positive match)

**File:** `app/scoring/puesto_match.py:138`

**Issue:** The threshold comparison `if best_cosine < umbral` evaluates to `False` when
`best_cosine` is `NaN` (IEEE 754: all comparisons with NaN return `False`). If the
embedder returns NaN in any vector component (possible when BGE-M3 normalises a
zero-norm embedding, e.g. for empty or whitespace-only input), `argmax` returns index 0
and `best_cosine = NaN`, which silently passes the threshold check and reports a match
at rank 1 instead of "fuera de ranking".

This is a latent correctness bug: `FakeEmbedder` always returns valid vectors in tests,
so it is not currently caught. Real `BgeM3Embedder` on pathological inputs could trigger it.

**Fix:** Add a NaN check before the threshold comparison:

```python
import math

if math.isnan(best_cosine) or best_cosine < umbral:
    logger.debug(
        "match_puesto_por_coseno: %r → fuera de ranking "
        "(best_cosine=%s < umbral=%.3f)",
        title,
        best_cosine,
        umbral,
    )
    return ("fuera de ranking", None)
```

Apply the same guard to `encaje_skills_por_coseno` in `skills_match.py:151`:

```python
if math.isnan(cosine):
    logger.warning("encaje_skills_por_coseno: cosine is NaN — returning 0 (neutral)")
    return 0
score: int = int(round(max(0.0, min(1.0, cosine)) * 100))
```

---

### WR-03: CV data and ranking data are not XML-escaped in the LLM prompt

**File:** `app/scoring/llm.py:170-221` (`_format_cv`, `_format_ranking`, `_build_prompt`)

**Issue:** `_format_job` correctly escapes job fields via `_escape_for_prompt`. However,
`_format_cv` and `_format_ranking` do NOT escape their output before it is inserted into
`<cv>…</cv>` and `<ranking_puestos>…</ranking_puestos>` XML tags in `_build_prompt`.

A CV entry with a company name or role containing `</cv>` (e.g., from a maliciously
crafted or corrupted PDF) can close the `<cv>` XML tag early and inject content into the
surrounding structure, weakening the prompt isolation. Ranking `titulo` or `sinonimos`
values from a manipulated `profile.yaml` have the same vulnerability.

The docstring says the escaping covers "prompt injection" but the implementation only
escapes job data. The model-server trust boundary for CV data (comes from user's own PDF)
and ranking data (comes from `profile.yaml`) is lower than for job descriptions, but the
structural risk is the same if those files are ever sourced externally.

**Fix:** Apply `_escape_for_prompt` to all field values before interpolation in
`_format_cv` and `_format_ranking`:

```python
# In _format_cv, change lines like:
linea = f"  - {exp.empresa} | {exp.rol}"
# to:
linea = f"  - {_escape_for_prompt(exp.empresa)} | {_escape_for_prompt(exp.rol)}"

# Similarly in _format_ranking:
linea = f"{i}. {_escape_for_prompt(puesto.titulo)}"
if puesto.sinonimos:
    linea += f" (sinónimos: {', '.join(_escape_for_prompt(s) for s in puesto.sinonimos)})"
```

---

### WR-04: test_puesto_match.py and test_skills_match.py import FakeEmbedder at module level

**File:** `tests/scoring/test_puesto_match.py:25`, `tests/scoring/test_skills_match.py:22`

**Issue:** Both test files import `FakeEmbedder` at module level:

```python
from app.dedup.embedder import FakeEmbedder
```

The project's stated rule (Pitfall 7, enforced in `test_scorer.py` and
`test_scorer_v2_guards.py` via deferred imports) is that `FakeEmbedder` must only be
imported inside test function bodies to prevent `torch` / `sentence-transformers` from
loading at collection time. These two test files break that contract consistently.

The test files themselves even include a `TestPuestoMatchImportSafety.test_import_does_not_load_torch`
test that will *pass* (because `torch` may already have been imported before those
tests run in a given session), but the collection-time import still violates the
architectural rule and can cause CI failures in minimal environments.

**Fix:** Move the `FakeEmbedder` import inside each test method or use a module-level
fixture that defers the import:

```python
# Replace module-level:
# from app.dedup.embedder import FakeEmbedder

# With a helper used in each test:
def _fake_embedder(**kwargs):
    from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7
    return FakeEmbedder(**kwargs)
```

---

## Info

### IN-01: test_llm.py imports unused LLMJobAssessment (deprecated v1 schema)

**File:** `tests/scoring/test_llm.py:24`

**Issue:** `LLMJobAssessment` is imported at line 24 but never referenced in any test
body. This is a dead import left over from the v1 scorer. The schema still exists in
`schemas.py` for backward compatibility, but importing it in `test_llm.py` is confusing
— it suggests the LLM module still uses it when `llm.py` v2.0 uses only `LLMEnrichment`.

**Fix:** Remove the unused import:

```python
# Remove from the imports block:
LLMJobAssessment,
```

---

### IN-02: CV_SKILLS_TEXT_MAX_TOKENS is mislabeled as "tokens" but is a character count

**File:** `app/scoring/skills_match.py:63`, `app/scoring/scorer.py:53`

**Issue:** Both `CV_SKILLS_TEXT_MAX_TOKENS` (in `skills_match.py`) and
`_CV_TEXT_MAX_CHARS` (in `scorer.py`) document the value as a character limit — which is
correct — but the exported constant in `skills_match.py` is named `_MAX_TOKENS`. The
name creates a misleading impression that it is measured in LLM tokens (it is not; it is
measured in characters). The docstring immediately clarifies this, but the name
propagates into test assertions (`assert CV_SKILLS_TEXT_MAX_TOKENS == 500`) which look
like token budget assertions.

**Fix:** Rename to `CV_SKILLS_TEXT_MAX_CHARS` and update the one test reference:

```python
# skills_match.py line 63:
CV_SKILLS_TEXT_MAX_CHARS: int = 500  # was CV_SKILLS_TEXT_MAX_TOKENS

# test_skills_match.py:
from app.scoring.skills_match import CV_SKILLS_TEXT_MAX_CHARS, encaje_skills_por_coseno
assert CV_SKILLS_TEXT_MAX_CHARS == 500
```

---

### IN-03: ranking.py does not guard against maximo < suelo misconfiguration

**File:** `app/scoring/ranking.py:59`

**Issue:** `encaje_puesto_desde_rango` accepts `maximo` and `suelo` as keyword
arguments. If a caller passes `maximo < suelo` (e.g. `maximo=10, suelo=20`), the
formula `min(maximo, max(suelo, score))` silently returns `maximo` for all rango values,
which is less than the stated `suelo`. The function contract says it returns "entre suelo
y maximo", but this is violated silently.

With the defaults (`paso=15, suelo=20, maximo=100`) this cannot happen, but if a user
adjusts pesos/decay parameters in `profile.yaml` and the loader ever exposes these
parameters, the silent mis-scoring would be hard to diagnose.

**Fix:** Add a guard at the start of the function:

```python
if maximo < suelo:
    raise ValueError(
        f"maximo ({maximo}) debe ser >= suelo ({suelo}) "
        f"para que el rango de encaje_puesto sea válido."
    )
```

---

## Findings Summary by Severity

| ID    | Severity | Component               | Title                                                    |
|-------|----------|-------------------------|----------------------------------------------------------|
| CR-01 | BLOCKER  | seniority.py            | ZeroDivisionError on "0 years" job descriptions          |
| CR-02 | BLOCKER  | tests/conftest.py       | Module-level LLMEnrichment import breaks no-LLM CI      |
| WR-01 | WARNING  | scorer.py               | "sin_skills" fallback produces wrong encaje_skills score  |
| WR-02 | WARNING  | puesto_match.py / skills_match.py | NaN cosine bypasses umbral (false positive match) |
| WR-03 | WARNING  | llm.py                  | CV/ranking fields not XML-escaped in LLM prompt          |
| WR-04 | WARNING  | test_puesto_match.py / test_skills_match.py | FakeEmbedder at module level breaks Pitfall 7 |
| IN-01 | INFO     | test_llm.py             | Dead import of deprecated LLMJobAssessment               |
| IN-02 | INFO     | skills_match.py / scorer.py | CV_SKILLS_TEXT_MAX_TOKENS misleading name           |
| IN-03 | INFO     | ranking.py              | No guard against maximo < suelo misconfiguration         |

---

_Reviewed: 2026-05-25_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
