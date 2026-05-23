# Phase 3: Heurística de Scoring (núcleo) - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, defaults auto-accepted — user hands-off)

> ⭐ Esta es la fase NÚCLEO del proyecto (CLAUDE.md: "la fase más importante, dale el cuidado
> que merece"). La heurística combina lógica determinista + juicio del LLM; NO se deja todo al LLM.

<domain>
## Phase Boundary

Para cada oferta única (`Job`), producir un `JobScore` (schema ya definido en
`app/models/schemas.py`) honesto y fiable, combinando lógica determinista (Python, testeable
sin LLM) y juicio del LLM (Instructor + Anthropic, mockeable). Incluye el cargador de
`UserProfile` desde `data/profile.yaml` (`app/config/`), necesario para ranking, preferencias,
deal-breakers y pesos. Entrega módulos bajo `app/scoring/` + `app/config/` + tests exhaustivos.

Fuera de boundary: endpoints HTTP (Fase 4), persistencia (Fase 4), orquestación CV+dedup+score
de punta a punta (Fase 4 /jobs/process), observabilidad Langfuse real (Fase 5 — pero estructurar
la llamada LLM para que sea fácil de envolver luego).
</domain>

<decisions>
## Implementation Decisions

### Reparto determinista vs LLM (CLAUDE.md regla: combinar, no dejar todo al LLM)

**Capa DETERMINISTA (Python puro, unit-testeable sin LLM):**
- `encaje_puesto` = función de DECAIMIENTO del `rango_puesto`: rango 1 → 100 (máximo), cada
  posición más abajo reduce de forma graduada (default lineal con `paso` configurable, p.ej. 100,
  85, 70, 55…), con un `suelo` para ofertas fuera de ranking (rango_puesto=None → encaje bajo,
  p.ej. 20, NO 0 — fuera de ranking no se descarta sola). Parámetros configurables (defaults en
  código; opcionalmente leíbles de profile.yaml). El LLM decide QUÉ rango encaja; el SCORE de
  encaje_puesto lo calcula Python desde el decay → "ranking como peso graduado" es determinista y testeable.
- `encaje_ubicacion` = reglas deterministas desde `Job.remote` + `Job.location` vs `UserProfile`:
  remote y modalidad_ideal lo permite → alto (~100); onsite/hybrid en ciudad de
  `ciudades_preferidas` o `acepta_onsite_solo_en` → alto; onsite/hybrid fuera de esas ciudades y
  `dispuesto_a_reubicarse=false` → muy bajo (~10) y marcar candidato a deal-breaker de ubicación;
  `unknown` → neutro (~50).
- `score_total` = suma PONDERADA de los 4 sub-encajes con pesos de `UserProfile.pesos`
  (puesto/skills/ubicacion/seniority, ya en schema; deben sumar 1.0 — validar al cargar). Fórmula
  determinista, redondeo a int 0-100.
- `recommendation` = bandas deterministas de `score_total` (defaults: ≥80 strong_fit, ≥60 good_fit,
  ≥40 maybe, <40 skip), configurables. PERO un deal-breaker fuerza skip (override duro).
- **Deal-breaker = filtro DURO**: si se dispara cualquier deal-breaker (detección determinista de
  los basados en ubicación, p.ej. "presencial fuera de Barcelona" desde location/remote, + los
  detectados por el LLM en el texto, p.ej. "exige 5+ años") → `deal_breaker_hit=true`,
  `deal_breaker_cual` explica cuál, y `recommendation=skip` (sin importar el resto).

**Capa LLM (Instructor + Anthropic, response_model = LLMJobAssessment):**
- `puesto_detectado` (str) + `rango_puesto` (int|null): el LLM empareja la oferta con la entrada
  del ranking usando los sinónimos; null si ninguna encaja.
- `encaje_skills` (0-100): requisitos de la oferta vs skills REALES del CVProfile.
- `encaje_seniority` (0-100): nivel/años pedidos vs experiencia real del CVProfile; pedir mucho
  más baja el encaje y aparece en `missing_requirements`, pero NO descarta solo.
- `matched_skills` [str], `missing_requirements` [str], `reasons_for` [str], `reasons_against` [str]
  (honesto, sin inflar).
- `deal_breaker_hit_texto` (bool) + `cual` (str|null): deal-breakers detectables en el texto.
- El LLM NO calcula `score_total`, `encaje_puesto` ni `encaje_ubicacion` (esos son deterministas).

### Estructura de módulos
- `app/config/loader.py`: `load_user_profile(path="data/profile.yaml") -> UserProfile`
  (yaml → Pydantic; validar que `pesos` suman 1.0; errores claros).
- `app/scoring/ranking.py`: `encaje_puesto_desde_rango(rango: int|None, ...) -> int` (decay).
- `app/scoring/location.py`: `evaluar_ubicacion(job, profile) -> (encaje:int, deal_breaker:str|None)`.
- `app/scoring/llm.py`: `build_instructor_client()` (factory, mock seam) + `assess_job(job, cv, profile, client) -> LLMJobAssessment` (prompt incluye CVProfile + ranking con sinónimos + preferencias ubicación/remoto + deal_breakers + la oferta).
- `app/scoring/scorer.py`: `score_job(job, cv_profile, user_profile, client=None, ...) -> JobScore`
  (orquesta: ubicación determinista → assess LLM → decay → combinar deal-breakers → score_total
  ponderado → recommendation; ensambla JobScore).
- Nuevo schema `LLMJobAssessment` en `app/models/schemas.py` (junto a JobScore).

### Modelo LLM
- Configurable vía env `ANTHROPIC_MODEL_SCORING`; default un Claude con buen juicio/coste para
  scoring por oferta (recomendado `claude-sonnet-4-6`; el scoring necesita más juicio que el
  parseo de CV). Claude's discretion sobre el nombre exacto. `max_retries` razonable.
- Clave desde `ANTHROPIC_API_KEY` (env); nunca hardcodeada. Estructurar la llamada en una sola
  función para que Fase 5 pueda envolverla con Langfuse fácilmente.

### Tests (QA-04 — exhaustivos, LLM mockeado)
- Decay del ranking: rango 1 → encaje_puesto máximo; rangos más bajos → menor (monótono);
  rango None (fuera de ranking) → encaje bajo pero > 0 (no se descarta solo).
- Deal-breaker fuerza skip: con deal_breaker_hit (ubicación O texto) → recommendation=skip aunque
  los sub-scores sean altos.
- Ubicación: remote permitido → alto; onsite en Barcelona → alto; onsite en Madrid + no
  reubicarse → muy bajo (y deal-breaker de ubicación).
- score_total: dados 4 sub-scores + pesos conocidos → total ponderado esperado (cálculo exacto).
- recommendation: bandas correctas según score_total.
- seniority: el LLM (mock) devuelve encaje_seniority bajo + missing_requirements → se reflejan en
  el JobScore sin forzar skip.
- El LLM SIEMPRE mockeado (devuelve un LLMJobAssessment controlado); cero red en tests.

### Claude's Discretion
- Nombre exacto del modelo default y de la decay (lineal vs por tramos) — lineal con paso/suelo configurable
- Si los parámetros de decay/bandas viven en profile.yaml o en código con defaults (mínimo: configurables)
- Estructura interna exacta y nombres de campos de `LLMJobAssessment`
- Cómo se redondean/clampan los scores
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models/schemas.py`: `JobScore`, `Desglose`, `Recommendation` enum, `UserProfile`,
  `PesosScoring`, `PuestoRanking`, `CVProfile`, `Job`, `ModalidadRemoto`, `RemoteJob`. Usar tal cual; añadir `LLMJobAssessment`.
- `data/profile.yaml`: perfil real de Jaime (ranking, preferencias, deal_breakers, pesos, dedup_umbral).
- `app/cv/llm_client.py`: patrón EXACTO de cliente Instructor + factory inyectable + mock en tests
  (`build_instructor_client`, response_model). Replicar para `app/scoring/llm.py`.
- `app/cv/parser.py` produce el `CVProfile` real que consumirá el scoring.
- `tests/conftest.py`: patrón de mock del cliente LLM (mock_llm_client) — replicar para scoring.

### Established Patterns
- Pydantic v2, type hints, Spanish naming. Instructor `client.messages.create(response_model=...)`.
- Lazy/injectable LLM client + mock en tests (Fases 1-2). pyyaml ya es dependencia (profile loader).
- `uv add` para deps. Esta fase probablemente NO necesita deps nuevas (instructor/anthropic/pyyaml ya están).

### Integration Points
- `score_job` lo consumirá `/jobs/process` y `/jobs/score` (Fase 4). Entrada: Job (deduplicado,
  Fase 2) + CVProfile (Fase 1) + UserProfile (loader de esta fase).
- La llamada LLM se envolverá con Langfuse en Fase 5 (OBS-02) — mantenerla en una función única.
</code_context>

<specifics>
## Specific Ideas

- Pesos por defecto (profile.yaml): puesto 35% / skills 30% / ubicacion 20% / seniority 15%.
- Ranking real de Jaime: 1) AI Engineer 2) ML Engineer 3) Data Engineer 4) MLOps, con sinónimos.
- Deal-breakers reales: "exige 5+ años de experiencia", "presencial fuera de Barcelona".
- HONESTIDAD es el valor central: reasons_against y missing_requirements sin inflar — el valor es filtrar bien.
</specifics>

<deferred>
## Deferred Ideas

- Observabilidad Langfuse real alrededor de la llamada de scoring (Fase 5, OBS-02)
- Endpoints /jobs/score y /jobs/process (Fase 4)
- Persistencia de los scores (Fase 4)
- Calibración fina de los pesos/decay contra resultados reales (post-uso real)
</deferred>
