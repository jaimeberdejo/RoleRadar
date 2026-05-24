# Phase 7: Embeddings-First Scoring Refactor - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning
**Mode:** Streamlined (refactor; design pinned in CLAUDE.md heuristic + STATE v2.0 decisions — research/pattern-map/plan-check skipped, code-review + verification kept)

<domain>
## Phase Boundary

Refactor the scorer so **all four numeric sub-scores** (encaje_puesto, encaje_skills, encaje_ubicacion, encaje_seniority) and a complete `JobScore` are produced **deterministically, with NO OpenAI call**. OpenAI becomes **optional enrichment**: when `OPENAI_API_KEY` is present it adds honest prose (`reasons_for`, `reasons_against`) and itemized `matched_skills` / `missing_requirements`; when absent, rule-based fallback strings fill those fields. The numbers never depend on the LLM.

This is the project's core (CLAUDE.md: "si todo lo demás falla, la heurística de scoring debe funcionar y ser confiable"). Honesty in `reasons_against` / `missing_requirements` is the value.

</domain>

<decisions>
## Implementation Decisions (LOCKED — from CLAUDE.md heuristic + STATE v2.0)

### Entry point
- `score_job(job, user_profile, cv_profile, embedder, *, client=None)` — `embedder` is a REQUIRED injected dependency (the `Embedder` Protocol from app/dedup/embedder.py). `client` (instructor) stays optional/injectable for tests.
- **Numbers first, LLM deferred** (STATE decision): compute all 4 deterministic sub-scores + score_total + recommendation FIRST. Only then, in a branch `if os.getenv("OPENAI_API_KEY"):`, do a **deferred import** of the LLM enrichment and populate prose/lists. No OpenAI import at module top of the deterministic path.
- **Do NOT import app.dedup in scorer.py** (Pitfall 7 — drags BGE-M3/torch into scorer tests). Reference the `Embedder` Protocol via `TYPE_CHECKING` or a local Protocol; runtime is duck-typed on the injected embedder.

### The four numeric sub-scores (all deterministic)
1. **encaje_puesto** — keep `ranking.py` decay function. BUT `rango_puesto` + `puesto_detectado` are now resolved by **BGE-M3 cosine** between the job title and each ranking entry's `nombre` + `sinonimos` (SC3, SCORE-11). Pick the best-matching ranking entry above a configurable threshold (default ~0.55, justify); if none clears the threshold → `puesto_detectado="fuera de ranking"`, `rango_puesto=None`, low encaje_puesto. NOT an LLM call.
2. **encaje_skills** — **BGE-M3 cosine** between CV text (skills_tecnicas + experience technologies) and the job description (SC2, SCORE-10). Map cosine→0-100 with a documented linear mapping. If the embedder is missing/None → raise a CLEAR error, never a silent 0 (SC2).
3. **encaje_ubicacion** — keep existing deterministic `location.py` (`evaluar_ubicacion`). No change to its logic.
4. **encaje_seniority** — NEW deterministic rule (SCORE-12). Parse required years from the job description (regex for "N+ years", "N años", "senior/junior/lead" level words) and compare to `cv_profile.anios_experiencia_total`. **`anios_experiencia_total is None` → neutral 50** (STATE blocker: treat None as "unknown", not 0). Asking more than the candidate has lowers the score and adds to `missing_requirements`, but does NOT auto-skip (CLAUDE.md rule 3 — requisitos inflados).

### Deal-breakers (hard filter, deterministic)
- `deal_breaker_hit` detected by **deterministic keyword/substring matching** of `user_profile.deal_breakers` against the job text (title+description, accent/case-normalized) (SC4, SCORE-13). On hit: `deal_breaker_hit=True`, `deal_breaker_cual` set, and `recommendation=skip` regardless of numeric score (last-override, keep score_total honest — STATE decision "deal-breaker override last"). Works with OpenAI absent.

### score_total + recommendation
- `score_total` = weighted combination of the 4 sub-scores using `PesosScoring` weights (puesto/skills/ubicacion/seniority) from profile.yaml. Deterministic.
- recommendation via existing banding (`_banda`), then deal-breaker override → skip.

### OpenAI optional enrichment (SC5, SCORE-14, SCORE-15)
- When `OPENAI_API_KEY` present: deferred-import the enrichment path (refactor `llm.py` so it produces ONLY prose `reasons_for`/`reasons_against` and itemized `matched_skills`/`missing_requirements` — it must NOT be the source of the four numbers anymore). Keep the fixed system prompt / anti-injection `<oferta>` XML section (STATE decision).
- When absent: rule-based fallbacks — `matched_skills` = deterministic overlap of CV skills ∩ job text; `missing_requirements` = parsed job requirements not found in CV; `reasons_for`/`reasons_against` = templated strings derived from the numeric breakdown (e.g., "encaje_puesto alto: coincide con ranking #1"). Never empty/None.

</decisions>

<code_context>
## Existing Code Insights

- `app/scoring/scorer.py` (150 lines) — `score_job(job, user_profile, cv_profile, client=None)`; currently builds an instructor client and delegates skills/seniority/ranking-match/reasons/deal-breaker to the LLM. THIS is the file to refactor to numbers-first + embedder injection. `_banda(score)` → Recommendation stays.
- `app/scoring/llm.py` (205 lines) — `assess_job()` + `build_instructor_client()` + prompt builders. Refactor `assess_job` (or add an enrichment fn) to return ONLY prose + matched/missing lists, not the numeric scores. Keep `build_instructor_client` seam, `_escape_for_prompt`, `trace_llm`.
- `app/scoring/location.py` (179 lines) — deterministic `evaluar_ubicacion`. KEEP as-is (encaje_ubicacion).
- `app/scoring/ranking.py` (60 lines) — `encaje_puesto_desde_rango` decay. KEEP; now fed by embeddings-derived rango_puesto.
- `app/dedup/embedder.py` — `Embedder` Protocol (`embed(texts) -> np.ndarray`, L2-normalized so dot==cosine), `BgeM3Embedder`, and `FakeEmbedder` (test double — use to mock embeddings). A new deterministic title→ranking matcher likely lives in scoring (e.g., a new `ranking.py` helper or `puesto_match.py`) and takes the injected embedder.
- `app/models/schemas.py` — `JobScore` (numeric fields stay), `Desglose` (4 sub-scores), `LLMJobAssessment` (currently carries numbers + prose; the numbers become unused/removed from the enrichment path), `PuestoRanking` (nombre + sinonimos), `CVProfile.anios_experiencia_total: Optional[float]`, `PesosScoring` (weights, validated sum==1.0).
- Deferred from Phase 6: **WR-04** — when scoring reads weights from the settings table, validate them through `PesosScoring.check_sum`. Address here if a settings→PesosScoring path is introduced; otherwise note it forward.

</code_context>

<specifics>
## Specific Ideas

- Tests (QA-05, QA-07, SC6): mock both embedder (`FakeEmbedder`) and LLM. MUST include at least one end-to-end test of the complete "no OPENAI_API_KEY" path producing a full valid JobScore with all 4 numeric sub-scores. Cover: ranking match via embeddings, deal-breaker forces skip, seniority None→50, encaje_skills cosine mapping, OpenAI-present enrichment populated vs OpenAI-absent fallbacks present.
- Keep the scoring module's rule "never import app.dedup" intact (tests must not load torch via the scorer).

</specifics>

<deferred>
## Deferred Ideas

- SCORE-16 (salary extraction/filtering) — already deferred to v2.x in REQUIREMENTS.
- IN-02 from Phase 6 (score_json NOT NULL) — schema hardening, separate pass.

</deferred>
