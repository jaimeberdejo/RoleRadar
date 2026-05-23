---
phase: 03-heuristica-de-scoring
verified: 2026-05-22T05:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
human_verification:
---

# Phase 3: Heurística de Scoring (núcleo) Verification Report

**Phase Goal:** Puntuar cada oferta única contra el perfil REAL de Jaime con honestidad, combinando lógica determinista y juicio del LLM; ranking como peso graduado, deal-breakers filtro duro, resultado fiable y explicable.
**Verified:** 2026-05-22T05:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

This is the NÚCLEO phase. Verification was rigorous and goal-backward: every success
criterion and every CLAUDE.md heuristic rule was checked against actual code, then
confirmed with `uv run pytest` (full suite green) plus independent behavioral spot-checks
that compute the weighted sum, exercise the deal-breaker override, the ranking floor,
and the LLMJobAssessment field ownership directly.

### Observable Truths

| # | Truth (Success Criterion) | Status | Evidence |
|---|---------------------------|--------|----------|
| 1 | JobScore con score_total, recommendation y desglose; score_total = combinación ponderada con pesos configurables (35/30/20/15) | ✓ VERIFIED | `scorer.py:79-85` computes `round(clamp(encaje_puesto*p.puesto + skills*p.skills + ubicacion*p.ubicacion + seniority*p.seniority))` with weights from `user_profile.pesos`. `data/profile.yaml:44-47` = 0.35/0.30/0.20/0.15. `PesosScoring.check_sum` (schemas.py:78-83) validates sum=1.0 (float-tolerant). Spot-check Case A: rango1/skills80/ubic100/sen70 → exactly 90 (round(89.5)). `test_score_total_ponderado_exacto` asserts exact 90. |
| 2 | Ranking como peso graduado (decay configurable); fuera de ranking NO se descarta sola | ✓ VERIFIED | `ranking.py:55-58` `max(suelo, maximo-(rango-1)*paso)`; rango=None → suelo=20 (>0). Spot-check Case C: rango_puesto=None → encaje_puesto=20, recommendation=maybe (not skip). `test_ranking.py` 11 tests (exact 100/85/70/55/20, monotonic, floor>0, configurable). `test_fuera_de_ranking_no_descarta` confirms integration. |
| 3 | Ubicación/remoto y seniority evaluadas correctamente contra perfil/CV real | ✓ VERIFIED | `location.py:79-172` deterministic 8-branch map (remote→100, remote+onsite-pref→60, onsite/hybrid accepted city→90/80, not accepted+no relocate→10+dealbreaker, +relocate→40/50, unknown→50). NFD substring city match (`Barcelona, España` matches `Barcelona`). `test_location.py` 13 tests cover all branches + None-safety. Seniority: LLM provides `encaje_seniority`; `test_seniority_bajo_no_descarta` confirms low seniority lowers desglose + populates missing_requirements WITHOUT forcing skip. |
| 4 | Deal-breaker → skip (filtro duro); score honesto en reasons/missing; prompt incluye CVProfile+ranking+prefs+deal_breakers+oferta | ✓ VERIFIED | `scorer.py:90-97` deal-breaker override is the LAST step (step 7); forces `recommendation=skip` while `score_total` keeps its honest computed value. Spot-check Case B: Madrid onsite + high skills → recommendation=skip, deal_breaker_hit=True, score_total=76 (NOT zeroed). `test_deal_breaker_ubicacion_fuerza_skip` + `test_deal_breaker_texto_fuerza_skip` confirm both location and LLM-text deal-breakers. Prompt: `llm.py:103-126` `_build_prompt` includes CV (`_format_cv`), ranking+synonyms (`_format_ranking`), prefs, deal_breakers, offer in XML `<oferta>`. `test_assess_job_incluye_contexto_en_prompt` asserts all 5 present (SCORE-08). Honesty engineered: `razonamiento` field FIRST (chain-of-thought) + fixed anti-inflation system prompt (`llm.py:166-172`). |
| 5 | Tests exhaustivos de la heurística (LLM mockeado): ranking pesa, deal-breaker fuerza skip, ubicación correcta | ✓ VERIFIED | 40 scoring tests pass (`tests/scoring/`): test_ranking(11), test_location(13), test_loader(4), test_llm(4), test_scorer(7+1). LLM always mocked via `make_scoring_client` (MagicMock, `.messages.create.return_value`). Zero network: `env -u ANTHROPIC_API_KEY uv run pytest tests/scoring` → 40 passed in 0.37s. Full suite: 127 passed, 0 failures. |

**Score:** 5/5 truths verified

### CLAUDE.md Heuristic Rules (núcleo contract)

| Rule | Status | Evidence |
|------|--------|----------|
| 1. Ranking como peso, no filtro binario | ✓ VERIFIED | Decay function; out-of-ranking floor 20, not auto-discarded (see Truth 2). |
| 2. Ubicación y remoto | ✓ VERIFIED | Deterministic 8-branch map; remote+permitted→high, onsite outside accepted+no relocate→very low + deal-breaker (see Truth 3). |
| 3. Seniority lowers but does NOT auto-reject | ✓ VERIFIED | `test_seniority_bajo_no_descarta`: low seniority reflected, no skip forced (see Truth 3). |
| 4. Deal-breakers = hard filter | ✓ VERIFIED | Override LAST → recommendation=skip; honest score preserved (see Truth 4). |
| 5. score_total = weighted sum, configurable weights | ✓ VERIFIED | Exact weighted formula with profile.yaml weights (see Truth 1). |

### Deterministic-vs-LLM Ownership (architectural contract)

| Check | Status | Evidence |
|-------|--------|----------|
| LLMJobAssessment excludes score_total/encaje_puesto/encaje_ubicacion/recommendation | ✓ VERIFIED | Spot-check D: `forbidden & model_fields = set()` (empty). schemas.py:166-225 has no such fields. LLM cannot influence deterministic scores. |
| encaje_puesto computed by Python from LLM's rango | ✓ VERIFIED | `scorer.py:74` `encaje_puesto_desde_rango(assessment.rango_puesto)`. |
| encaje_ubicacion computed deterministically before LLM call | ✓ VERIFIED | `scorer.py:68` `evaluar_ubicacion` runs before `assess_job`. |
| recommendation 100% deterministic (bands + override) | ✓ VERIFIED | `scorer.py:88,96-97` + `_banda`. No LLM recommendation field. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/models/schemas.py` (LLMJobAssessment, PesosScoring.check_sum) | Schema with razonamiento-first, no deterministic fields; float-tolerant weight validator | ✓ VERIFIED | 11 fields, razonamiento first, ge/le clamps, check_sum uses abs<1e-6. |
| `app/config/loader.py` | load_user_profile YAML→UserProfile, clear errors | ✓ VERIFIED | yaml.safe_load (security), ValidationError→ValueError with detail, FileNotFoundError with path. |
| `app/scoring/ranking.py` | encaje_puesto_desde_rango decay | ✓ VERIFIED | Pure stdlib, floor>0, configurable. |
| `app/scoring/location.py` | evaluar_ubicacion deterministic | ✓ VERIFIED | 8 branches + NFD substring + None-safe; no app.dedup import. |
| `app/scoring/llm.py` | build_instructor_client + assess_job, prompt context | ✓ VERIFIED | response_model=LLMJobAssessment, model env, max_retries=2, fixed system prompt, offer in XML. |
| `app/scoring/scorer.py` | score_job 6/7-step orchestrator | ✓ VERIFIED | Location→LLM→decay→weighted sum→bands→deal-breaker override LAST; assembles full JobScore. |
| `app/scoring/__init__.py` | public facade, no app.dedup | ✓ VERIFIED | Exports score_job; torch-free import confirmed. |
| `tests/scoring/*` | Exhaustive, LLM-mocked | ✓ VERIFIED | 40 tests, zero network. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| scorer.py | location.py | `evaluar_ubicacion(job, user_profile)` | ✓ WIRED | scorer.py:31,68 |
| scorer.py | llm.py | `assess_job(job, cv, profile, client)` | ✓ WIRED | scorer.py:32,71 |
| scorer.py | ranking.py | `encaje_puesto_desde_rango(rango)` | ✓ WIRED | scorer.py:33,74 |
| scorer.py | UserProfile.pesos | weighted sum uses `user_profile.pesos.*` | ✓ WIRED | scorer.py:78-84 |
| llm.py | LLMJobAssessment | `response_model=LLMJobAssessment` | ✓ WIRED | llm.py:179; test asserts call kwargs |
| loader.py | PesosScoring.check_sum | model_validate triggers validator | ✓ WIRED | loader.py:51; test_loader rejects bad weights |

### Data-Flow Trace (Level 4)

Not applicable — Phase 3 produces backend scoring logic (functions returning Pydantic
models), not dynamic-data-rendering UI components. The data-flow equivalent (LLM mock →
assessment → deterministic combination → JobScore) was verified directly via behavioral
spot-checks A/B/C/D, all producing real computed values (not static/empty).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Weighted sum exact (rango1/skills80/ubic100/sen70) | score_job with injected mock | score_total=90 (round(89.5)), strong_fit, enc_puesto=100, enc_ubic=100 | ✓ PASS |
| Deal-breaker override preserves honest score | Madrid onsite + skills90/sen80 | score_total=76 (honest), recommendation=skip, deal_breaker_hit=True, cual mentions Madrid | ✓ PASS |
| Out-of-ranking floor, no auto-skip | rango_puesto=None | enc_puesto=20, recommendation=maybe | ✓ PASS |
| LLMJobAssessment has no deterministic fields | model_fields ∩ forbidden | empty set() | ✓ PASS |
| Zero-network test run | `env -u ANTHROPIC_API_KEY uv run pytest tests/scoring` | 40 passed in 0.37s | ✓ PASS |
| app.scoring torch-free import | import app.scoring, inspect sys.modules | no torch/sentence_transformers/app.dedup loaded | ✓ PASS |
| Full suite green | `uv run pytest -q` | 127 passed, 0 failed, 0.42s | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SCORE-01 | 03-04 | JobScore con score_total, recommendation, desglose | ✓ SATISFIED | Truth 1; test_score_job_devuelve_jobscore_completo |
| SCORE-02 | 03-02 | Ranking peso graduado, fuera-de-ranking no descarta | ✓ SATISFIED | Truth 2; test_ranking + test_fuera_de_ranking_no_descarta |
| SCORE-03 | 03-03 | Ubicación/remoto evaluadas | ✓ SATISFIED | Truth 3; test_location (13) |
| SCORE-04 | 03-04 | Seniority baja encaje, aparece en missing, no descarta | ✓ SATISFIED | Truth 3; test_seniority_bajo_no_descarta |
| SCORE-05 | 03-04 | Deal-breaker → skip (filtro duro) | ✓ SATISFIED | Truth 4; 2 deal-breaker tests |
| SCORE-06 | 03-02/04 | score_total ponderado, pesos configurables 35/30/20/15 | ✓ SATISFIED | Truth 1; profile.yaml + test_loader + test_score_total_ponderado_exacto |
| SCORE-07 | 03-04 | Score honesto (reasons/matched/missing sin inflar) | ✓ SATISFIED | Truth 4; razonamiento-first + anti-inflation prompt + test_honestidad_propagada |
| SCORE-08 | 03-04 | Prompt incluye CV+ranking+prefs+deal_breakers+oferta | ✓ SATISFIED | Truth 4; test_assess_job_incluye_contexto_en_prompt |
| QA-04 | 03-04 | Tests exhaustivos heurística, LLM mockeado | ✓ SATISFIED | Truth 5; 40 tests, zero network |

No orphaned requirements: REQUIREMENTS.md maps exactly SCORE-01..08 + QA-04 to Phase 3, all claimed by plans.

### Anti-Patterns Found

None. Clean scan (TODO/FIXME/placeholder/NotImplementedError/return-null) across all 5
scoring/config modules returned zero matches.

### Deferred / Manual Follow-Up (acceptable)

Real LLM judgment quality — accuracy of skills/seniority sub-scores and honesty of
reasons_against/missing_requirements against REAL offers — requires a live ANTHROPIC_API_KEY
and real offers, so it cannot be verified programmatically. This is explicitly documented as
a manual-only verification in `03-VALIDATION.md` ("Manual-Only Verifications" + sign-off note
that the deterministic layer is fully automated). The instructions for this verification
explicitly state this is an acceptable documented follow-up and the phase passes if the
deterministic heuristic + wiring is correct and exhaustively tested — which it is. This is
NOT counted as a gap and does NOT require human verification before proceeding to Phase 4.

### Gaps Summary

No gaps. The deterministic heuristic is fully implemented, correctly wired, and exhaustively
tested. The architectural contract (LLM owns only free-text judgment; Python owns all numeric
scores, recommendation, and the hard deal-breaker filter) is enforced at the schema level and
verified by independent spot-checks. Weighted sum is exact, ranking decay is graduated with a
non-zero floor, location rules are correct across all branches, seniority lowers without
auto-rejecting, and the deal-breaker override runs last so the honest score is preserved.
Full suite is green (127 passed) with zero network dependency in scoring tests.

---

_Verified: 2026-05-22T05:00:00Z_
_Verifier: Claude (gsd-verifier)_
