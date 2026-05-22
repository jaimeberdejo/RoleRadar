# Roadmap: BuscadorDeEmpleo

## Overview

Construimos el cerebro de un agregador inteligente de empleo: un servicio FastAPI headless
que entiende el CV real de Jaime, normaliza y deduplica ofertas crudas, y las puntúa con
honestidad contra su perfil. El viaje sigue el orden natural del spec (CLAUDE.md): primero
enseñamos al servicio a leer el CV (FASE 2), luego a limpiar el ruido de ofertas duplicadas
(FASE 3), después le damos su juicio — la heurística de scoring que es el núcleo del
proyecto (FASE 4), lo exponemos vía HTTP con persistencia para que n8n lo consuma a diario
(FASE 5), y finalmente lo endurecemos con observabilidad, robustez de batch y la
documentación de integración que cierra el círculo. Cada fase deja una pieza inteligente
verificable de forma aislada antes de cablearla al conjunto.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Parseo de CV** - PDF → `CVProfile` estructurado y cacheado vía Pydantic + Instructor (completed 2026-05-22)
- [x] **Phase 2: Normalización y Deduplicación** - Ofertas crudas heterogéneas → `Job`s únicos, sin duplicados exactos ni semánticos (completed 2026-05-22)
- [ ] **Phase 3: Heurística de Scoring (núcleo)** - Cada oferta única recibe un `JobScore` honesto: ranking como peso, ubicación, seniority, deal-breakers
- [ ] **Phase 4: API y Persistencia** - Endpoints FastAPI que orquestan todo + almacenamiento SQLite-first con control de ya-vistas
- [ ] **Phase 5: Observabilidad, Robustez y Docs n8n** - Logging estructurado, stub Langfuse, batch resiliente y README con integración n8n

## Phase Details

### Phase 1: Parseo de CV
**Goal**: El servicio convierte el CV en PDF de Jaime en un `CVProfile` estructurado y fiable que el resto del sistema usará como verdad sobre su experiencia, sin re-parsear en cada run.
**Depends on**: Nothing (first phase) — FASE 1 (schemas, profile.yaml, estructura) ya está validada
**Requirements**: CV-01, CV-02, CV-03, QA-01
**Success Criteria** (what must be TRUE):
  1. Dado el CV en PDF de Jaime, el servicio devuelve un `CVProfile` con experiencia, skills técnicas, formación, años de experiencia total (estimado) y dominios poblados desde el contenido real
  2. Volver a pedir el parseo del mismo CV usa la versión cacheada y NO vuelve a llamar al LLM; solo se re-parsea si el PDF cambia
  3. El parseo usa Pydantic + Instructor y produce una salida estructurada válida (no texto libre) que valida contra el schema `CVProfile`
  4. Existe un test que parsea un PDF de ejemplo (fixture) con el LLM mockeado y verifica los campos clave del `CVProfile`
**Plans**: 4 plans
Plans:
- [x] 01-01-PLAN.md — Wave 0 setup: deps via uv, pytest config, tests/ tree + conftest fixtures (PDF builder, mocked instructor client)
- [x] 01-02-PLAN.md — extractor.py (pymupdf bytes→text) + cache.py (sha256 JSON CVProfile cache, CV-03) + tests
- [x] 01-03-PLAN.md — llm_client.py (instructor.from_anthropic, response_model=CVProfile, CV-01/CV-02) + mocked test
- [x] 01-04-PLAN.md — parser.py orchestrator + app.cv export + QA-01 end-to-end test (mocked LLM, cache short-circuit)

### Phase 2: Normalización y Deduplicación
**Goal**: El servicio convierte listas de ofertas crudas heterogéneas (de cualquier fuente) en `Job`s normalizados con id estable, y elimina duplicados tanto exactos como semánticos sin perder información, dejando un conjunto limpio de ofertas únicas.
**Depends on**: Phase 1
**Requirements**: NORM-01, NORM-02, NORM-03, NORM-04, DEDUP-01, DEDUP-02, DEDUP-03, QA-02, QA-03
**Success Criteria** (what must be TRUE):
  1. Dada una lista de ofertas crudas + un identificador de fuente, el servicio devuelve `Job`s normalizados, cada uno con un id estable (hash de empresa + título normalizado + ubicación) que es idéntico para la misma oferta entre runs
  2. Una oferta mal formada dentro del batch no tumba el resto: se procesa lo que se puede y se reporta lo que falló
  3. El servicio detecta y colapsa duplicados exactos (mismo hash) y duplicados semánticos (embeddings BGE-M3 locales sobre título + empresa + primeras N palabras, similitud coseno sobre umbral configurable)
  4. Al deduplicar conserva la oferta con la descripción más completa y guarda las URLs alternativas de las descartadas
  5. Existen tests de normalización por fuente y de dedup (duplicados obvios y casos semánticos) con embeddings mockeados
**Plans**: 4 plans
Plans:
- [x] 02-01-PLAN.md — Wave 0 setup: uv add sentence-transformers + tests/dedup/ + fixtures dedup en conftest (FakeEmbedder, payloads)
- [x] 02-02-PLAN.md — Normalización: normalize.py (NFD id sha256) + mappers.py (registry arbeitnow/generic AJUSTABLE) + normalize_jobs facade batch-resiliente + tests (NORM-01..04, QA-02)
- [x] 02-03-PLAN.md — Dedup helpers: embedder.py (Embedder Protocol + BgeM3Embedder lazy + FakeEmbedder) + exact.py + semantic.py (greedy coseno numpy) + merger.py + tests unitarios (DEDUP-01..03)
- [x] 02-04-PLAN.md — Integración: deduplicate() facade ensamblado + test end-to-end con FakeEmbedder (QA-03)

### Phase 3: Heurística de Scoring (núcleo)
**Goal**: El servicio puntúa cada oferta única contra el perfil REAL de Jaime con honestidad, combinando lógica determinista y juicio del LLM, de modo que el ranking de puestos pese de forma graduada, los deal-breakers filtren en duro y el resultado sea fiable y explicable.
**Depends on**: Phase 1, Phase 2
**Requirements**: SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, SCORE-06, SCORE-07, SCORE-08, QA-04
**Success Criteria** (what must be TRUE):
  1. Para cada oferta única el servicio devuelve un `JobScore` con `score_total` (0-100), `recommendation` y el desglose (encaje_puesto / skills / ubicación / seniority); `score_total` es la combinación ponderada de los cuatro sub-encajes con pesos configurables desde profile.yaml (defaults 35/30/20/15)
  2. El ranking de puestos actúa como peso graduado (función de decaimiento configurable): una oferta que casa con el puesto nº1 recibe encaje_puesto máximo, posiciones más bajas decaen, y una oferta fuera de ranking no se descarta sola sino que recibe encaje_puesto bajo
  3. La ubicación/remoto se evalúa correctamente: remote permitido → alto; onsite/hybrid alto solo en ciudades aceptadas; presencial fuera de Barcelona sin reubicación → muy bajo; y la seniority pedida se compara contra la experiencia real del `CVProfile`, bajando el encaje y apareciendo en `missing_requirements` sin descartar sola
  4. Si se dispara un deal-breaker, `recommendation = skip` y `deal_breaker_hit = true` explicando cuál (único filtro duro); el score es honesto en `reasons_for`, `reasons_against`, `matched_skills` y `missing_requirements`, y el prompt al LLM incluye CVProfile real + ranking con sinónimos + preferencias + deal-breakers + la oferta
  5. Tests exhaustivos de la heurística (LLM mockeado) verifican que el ranking pesa bien, que un deal-breaker fuerza skip, y que la ubicación se evalúa correcto
**Plans**: 4 plans
Plans:
- [ ] 03-01-PLAN.md — Wave 0 setup: LLMJobAssessment + PesosScoring validator (suma=1.0) en schemas.py + tests/scoring/ tree + fixtures de scoring (mock LLM client, sample UserProfile/CVProfile/Jobs)
- [ ] 03-02-PLAN.md — Deterministas paralelos: config/loader.py (UserProfile desde profile.yaml, SCORE-06) + scoring/ranking.py (decay del ranking, SCORE-02) + tests
- [ ] 03-03-PLAN.md — Determinista: scoring/location.py (evaluar_ubicacion, reglas + NFD city match, SCORE-03) + tests de las 8 ramas
- [ ] 03-04-PLAN.md — NÚCLEO: scoring/llm.py (assess_job, SCORE-07/08) + scoring/scorer.py (orquestador 6 pasos, SCORE-01/04/05/06) + facade + QA-04 tests exhaustivos

### Phase 4: API y Persistencia
**Goal**: El servicio queda expuesto como una API HTTP/JSON consumible por n8n que orquesta parseo + normalización + dedup + scoring de punta a punta, persiste el histórico con fecha y recuerda qué ofertas ya se vieron entre runs.
**Depends on**: Phase 1, Phase 2, Phase 3
**Requirements**: API-01, API-02, API-03, API-04, API-05, API-06, API-07, STORE-01, STORE-02, STORE-03
**Success Criteria** (what must be TRUE):
  1. Los endpoints están operativos y devuelven JSON limpio: `POST /cv/parse`, `GET /profile`, `POST /jobs/normalize`, `POST /jobs/score`, `GET /jobs/history`, con códigos HTTP claros en error
  2. `POST /jobs/process` recibe ofertas crudas de varias fuentes, ejecuta normalización + dedup + scoring y devuelve las ofertas únicas puntuadas y ordenadas por `score_total`, marcando las ya-vistas en runs anteriores
  3. Las ofertas se persisten con fecha en SQLite (histórico de evolución), con la ruta de upgrade a Supabase (Postgres + pgvector) y credenciales desde entorno
  4. El control de ya-vistas/ya-notificadas funciona entre runs: una oferta procesada un día aparece marcada como vista al día siguiente, para que n8n no la repita
**Plans**: TBD

### Phase 5: Observabilidad, Robustez y Docs n8n
**Goal**: El servicio queda listo para portfolio y para uso real: visible (logging + stub Langfuse), resiliente por capas, y documentado de forma que cualquiera pueda instalarlo, configurarlo y conectarlo a n8n sin leer el código.
**Depends on**: Phase 4
**Requirements**: OBS-01, OBS-02, OBS-03, DOC-01, DOC-02, DOC-03
**Success Criteria** (what must be TRUE):
  1. El logging estructurado reporta el flujo de cada run: cuántas ofertas entran, cuántos duplicados se detectan, cuántas se puntúan y el coste / nº de llamadas LLM
  2. Existe una interfaz/stub de Langfuse preparada para trazar las llamadas de scoring, y el manejo de errores está aislado por capa (CV / normalización / dedup / scoring / storage)
  3. El README cubre instalación, `.env`, cómo editar `profile.yaml`, cómo subir el CV y cómo arrancar el servicio, con una sección dedicada a integración con n8n (qué nodos llaman a qué endpoints, flujo, formato exacto del JSON de `/jobs/process`, cómo exponer el servicio)
  4. Se incluye un `profile.yaml` de ejemplo y un par de ofertas de ejemplo (JSON) que permiten probar `/jobs/process` de inmediato sin n8n
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Parseo de CV | 4/4 | Complete   | 2026-05-22 |
| 2. Normalización y Deduplicación | 4/4 | Complete   | 2026-05-22 |
| 3. Heurística de Scoring (núcleo) | 0/TBD | Not started | - |
| 4. API y Persistencia | 0/TBD | Not started | - |
| 5. Observabilidad, Robustez y Docs n8n | 0/TBD | Not started | - |
