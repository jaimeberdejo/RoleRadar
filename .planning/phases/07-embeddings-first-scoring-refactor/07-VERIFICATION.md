---
phase: 07-embeddings-first-scoring-refactor
verified: 2026-05-25T08:11:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 7: Embeddings-First Scoring Refactor — Verification Report

**Phase Goal:** The scorer produces all four numeric sub-scores (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority) and a full JobScore without any OpenAI call; when an OPENAI_API_KEY is present it adds honest prose reasons and itemized matched/missing skills as optional enrichment.
**Verified:** 2026-05-25T08:11:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | score_job(job, user_profile, cv_profile, embedder) with NO OPENAI_API_KEY returns a complete JobScore — all four numeric sub-scores present (not None), plus a recommendation. No import error on this path. | VERIFIED | G-02 guard test passes with `monkeypatch.delenv("OPENAI_API_KEY")`; `OPENAI_API_KEY="" python -c "import app.scoring.scorer; 'openai' in sys.modules"` returns False. scorer.py line 271: deferred import `if os.getenv("OPENAI_API_KEY"):` |
| 2 | encaje_skills computed by BGE-M3 cosine between CV text and job description; embedder missing → clear error, not silent zero. | VERIFIED | skills_match.py lines 116-120: `if embedder is None: raise ValueError("embedder es requerido...")`. scorer.py lines 216-228: "sin_skills" sentinel handled with neutral 50 instead of passing to embedder. ValueError raised immediately on None — confirmed by G-03 test pass. |
| 3 | rango_puesto + puesto_detectado resolved by BGE-M3 cosine between job title and ranking entries INCLUDING synonyms (not an LLM call). | VERIFIED | puesto_match.py lines 120-128: corpus built as `" ".join([entry.titulo, *entry.sinonimos])` for each ranking entry. Embed call is batch: [title] + corpus_texts. No LLM import in this path. G-05 guard test confirms rango_puesto=1 when cosine=1.0 against ranking entry #1. |
| 4 | deal_breaker_hit detected by deterministic keyword/substring matching; forces recommendation=skip regardless of numeric score; works with OpenAI absent. | VERIFIED | deal_breaker.py: stdlib-only (unicodedata, dataclasses, logging). No openai/instructor import. scorer.py lines 261-265: `deal_breaker_hit = bool(deal_breaker_loc or db_result.hit)` then `if deal_breaker_hit: recommendation = Recommendation.skip` — override fires LAST (PASO 7) after numeric scoring. G-04 guard test passes with OPENAI_API_KEY unset. |
| 5 | When OPENAI_API_KEY present: reasons_for/reasons_against/matched_skills/missing_requirements populated (via enrich_job, mocked in tests); when absent: rule-based fallback strings present (never empty). | VERIFIED | scorer.py lines 271-290: branch on `os.getenv("OPENAI_API_KEY")`. _fallback_reasons() at lines 88-156 guarantees non-empty lists: lines 138-142 enforce "Evalúa manualmente esta oferta" sentinel if both lists empty. llm.py exposes enrich_job() returning LLMEnrichment. test_scorer.py exercises mocked enrichment path. |
| 6 | Full suite passes with LLM + embeddings mocked; at least one test exercises the complete "no API key" path end-to-end. No torch leak at collection time. | VERIFIED | `uv run pytest tests/scoring -q` → 120 passed, 0 failed. `OPENAI_API_KEY="" uv run pytest tests/scoring/test_scorer_v2_guards.py` → 5 passed. `python -c "import tests.scoring.test_scorer_v2_guards" | grep torch` → no output. |

**Score:** 6/6 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/scoring/scorer.py` | Orchestrates 8-step pipeline; deferred openai import | VERIFIED | 340 lines. Signature: `score_job(job, user_profile, cv_profile, embedder, *, client=None)`. TYPE_CHECKING guard for Embedder. Deferred import at line 272. |
| `app/scoring/puesto_match.py` | BGE-M3 cosine match against ranking+synonyms corpus | VERIFIED | 165 lines. Corpus built from titulo+sinonimos (line 121). NaN guard at line 142. UMBRAL=0.55. |
| `app/scoring/skills_match.py` | BGE-M3 cosine between CV text and job description | VERIFIED | 171 lines. embedder=None raises ValueError. NaN guard at line 154. |
| `app/scoring/seniority.py` | Deterministic seniority from regex + level keywords | VERIFIED | 280 lines. ZeroDivisionError fix at lines 236-248: `if anos_requeridos == 0.0:` early return. |
| `app/scoring/deal_breaker.py` | Stdlib-only NFD+casefold substring match | VERIFIED | 159 lines. No external imports. Multiple hits joined with "; ". |
| `app/scoring/llm.py` | enrich_job() as optional enrichment; module-level openai import is internal to this module only | VERIFIED | 276 lines. _escape_for_prompt applied to all CV and ranking fields (WR-03 fixed). |
| `tests/scoring/test_scorer_v2_guards.py` | 5 guard tests covering new contract end-to-end | VERIFIED | 322 lines. 5 tests (G-01 through G-05). All pass. FakeEmbedder imported inside each test body. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| scorer.py | puesto_match.py | `match_puesto_por_coseno(job.title, user_profile.ranking_puestos, embedder)` | WIRED | Line 207-210 in scorer.py. Embedder forwarded correctly. |
| scorer.py | skills_match.py | `encaje_skills_por_coseno(cv_text, job.description, embedder)` | WIRED | Lines 216-228 in scorer.py. "sin_skills" path short-circuits before embedder call. |
| scorer.py | seniority.py | `evaluar_seniority(job.description, cv_profile.anios_experiencia_total)` | WIRED | Lines 233-236 in scorer.py. |
| scorer.py | deal_breaker.py | `detectar_deal_breaker(job_text, user_profile.deal_breakers)` | WIRED | Lines 241-242 in scorer.py. |
| scorer.py | llm.py (optional) | `if os.getenv("OPENAI_API_KEY"): from app.scoring.llm import build_instructor_client, enrich_job` | WIRED | Lines 271-279 in scorer.py. Deferred import — not loaded when key absent. |
| puesto_match.py | corpus (title+synonyms) | `" ".join([entry.titulo, *entry.sinonimos]).strip()` | WIRED | Line 121 in puesto_match.py. SC-3 explicitly satisfied. |
| scorer.py | _fallback_reasons() | Called in else branch when OPENAI_API_KEY absent | WIRED | Lines 281-290 in scorer.py. Returns non-empty reasons_for and reasons_against. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| scorer.py | encaje_puesto | encaje_puesto_desde_rango(rango_puesto) ← match_puesto_por_coseno() ← embedder.embed() | Yes — computed from cosine similarity | FLOWING |
| scorer.py | encaje_skills | encaje_skills_por_coseno() ← embedder.embed() or neutral 50 sentinel | Yes — cosine or neutral fallback | FLOWING |
| scorer.py | encaje_ubicacion | evaluar_ubicacion(job, user_profile) | Yes — deterministic logic | FLOWING |
| scorer.py | encaje_seniority | evaluar_seniority(job.description, cv_profile.anios_experiencia_total) | Yes — regex parse + ratio | FLOWING |
| scorer.py | score_total | weighted sum of four sub-scores via user_profile.pesos | Yes — deterministic arithmetic | FLOWING |
| scorer.py | reasons_for/against | _fallback_reasons() or enrich_job() depending on API key | Yes — never empty (guaranteed by fallback) | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| scorer.py does not import openai at module level | `OPENAI_API_KEY="" python -c "import app.scoring.scorer, sys; print('openai loaded:', 'openai' in sys.modules)"` | `openai loaded: False` | PASS |
| All 5 guard tests pass with no API key | `OPENAI_API_KEY="" uv run pytest tests/scoring/test_scorer_v2_guards.py` | 5 passed, 0 failed | PASS |
| Full scoring test suite passes | `uv run pytest tests/scoring -q` | 120 passed, 0 failed | PASS |
| 72 deterministic tests run without openai installed | `OPENAI_API_KEY="" uv run pytest tests/scoring/test_deal_breaker.py tests/scoring/test_seniority.py tests/scoring/test_ranking.py tests/scoring/test_location.py` | 72 passed | PASS |
| seniority.py handles "0-2 years" without ZeroDivisionError (CR-01 fix) | `python -c "from app.scoring.seniority import evaluar_seniority; r = evaluar_seniority('0-2 years experience preferred', 3.0); print(r.encaje_seniority)"` | `75` | PASS |
| conftest.py does not import openai at collection time (CR-02 fix) | `python -c "import tests.conftest, sys; print('openai:', 'openai' in sys.modules)"` | `openai: False` | PASS |
| torch not imported at test collection | `python -c "import tests.scoring.test_scorer_v2_guards" 2>&1 \| grep torch` | no output | PASS |

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|---------|
| SCORE-09 | All numeric sub-scores computed without OpenAI call | SATISFIED | scorer.py steps 1-6 are all deterministic. LLM only in step 8 guarded by `os.getenv`. |
| SCORE-10 | encaje_skills via BGE-M3 cosine (CV ↔ job description) | SATISFIED | skills_match.py `encaje_skills_por_coseno()` with embedder injection. scorer.py PASO 3. |
| SCORE-11 | rango_puesto/puesto_detectado via BGE-M3 cosine title↔ranking(+synonyms) | SATISFIED | puesto_match.py corpus includes titulo+sinonimos (line 121). Not an LLM call. |
| SCORE-12 | encaje_seniority deterministic (years/level detection vs CVProfile; None=neutral) | SATISFIED | seniority.py regex + level keywords. anios_candidato=None → 50 (line 205-213). |
| SCORE-13 | deal_breaker_hit deterministic keyword/substring match | SATISFIED | deal_breaker.py stdlib-only. scorer.py PASO 7 override. |
| SCORE-14 | OpenAI is optional enrichment only — never imported at startup | SATISFIED | scorer.py deferred import under `os.getenv("OPENAI_API_KEY")`. Confirmed by runtime check. |
| SCORE-15 | Rule-based fallback reasons when no key — never empty | SATISFIED | _fallback_reasons() guarantees non-empty lists (lines 138-142 sentinel). |
| QA-05 | Tests of local-first scorer (numeric scores deterministic and testable without LLM) | SATISFIED | 120 tests pass in tests/scoring. LLM mocked via make_enrichment_client(). |
| QA-07 | Test of "no OPENAI_API_KEY" path (no import error, scores present) | SATISFIED | G-02 guard test: monkeypatches away key, asserts all 4 sub-scores are ints in [0,100]. |

---

### Anti-Patterns Found

All REVIEW.md blockers (CR-01, CR-02) and warnings (WR-01, WR-02, WR-03, WR-04) were fixed in 07-REVIEW-FIX.md. Verified below:

| File | Fix | Pattern Checked | Status |
|------|-----|-----------------|--------|
| app/scoring/seniority.py | CR-01 | ZeroDivisionError on `0 years` | FIXED — line 236: `if anos_requeridos == 0.0:` early return with 75 |
| tests/conftest.py | CR-02 | Module-level `from app.scoring.llm import LLMEnrichment` | FIXED — `_LazyEnrichment` proxy defers import until first attribute access (lines 322-336) |
| app/scoring/scorer.py | WR-01 | "sin_skills" sentinel yielding wrong score | FIXED — lines 216-228: early return with `encaje_skills = 50` (neutral) |
| app/scoring/puesto_match.py | WR-02 | NaN cosine bypassing umbral | FIXED — line 142: `if math.isnan(best_cosine) or best_cosine < umbral` |
| app/scoring/skills_match.py | WR-02 | NaN cosine crashing `int(round(NaN))` | FIXED — line 154: `if math.isnan(cosine): return 0` |
| app/scoring/llm.py | WR-03 | CV/ranking fields not XML-escaped | FIXED — `_escape_for_prompt()` applied to all string fields in `_format_cv` and `_format_ranking` |
| tests/scoring/test_puesto_match.py | WR-04 | FakeEmbedder at module level | FIXED — deferred inside each test body with `# deferred — Pitfall 7 (WR-04)` |
| tests/scoring/test_skills_match.py | WR-04 | FakeEmbedder at module level | FIXED — deferred inside each test body with `# deferred — Pitfall 7 (WR-04)` |

INFO items deferred as intended (IN-01, IN-02, IN-03 — cosmetic, no runtime impact).

---

### Human Verification Required

None. All observable truths are verifiable programmatically and all tests pass.

---

## Summary

Phase 7 goal is fully achieved. The scorer is local-first: all four numeric sub-scores (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority) are computed deterministically without any OpenAI call. When OPENAI_API_KEY is absent, the complete JobScore is returned with rule-based fallback strings for reasons/skills — never empty. When present, enrich_job() provides prose enrichment as optional layering. The embedder is properly injected (duck-typed, TYPE_CHECKING guard), openai is never imported at module level in scorer.py or conftest.py, and embedder=None raises a clear ValueError immediately. All code-review blockers from 07-REVIEW.md are confirmed fixed in the actual codebase.

120 scoring tests pass (0 failures). 5/5 guard tests (G-01 through G-05) pass with OPENAI_API_KEY unset. 72 deterministic tests pass in a zero-LLM environment. No torch leak at collection time.

---

_Verified: 2026-05-25T08:11:00Z_
_Verifier: Claude (gsd-verifier)_
