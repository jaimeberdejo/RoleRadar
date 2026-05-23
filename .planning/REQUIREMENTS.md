# Requirements: BuscadorDeEmpleo

**Defined:** 2026-05-22
**Core Value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias), con el ranking como peso graduado y los deal-breakers como filtro duro.

> Nota: es un **servicio headless** consumido por n8n. Los requisitos se expresan como
> capacidades del servicio (no "User can X" de UI). FASE 1 (schemas + profile.yaml +
> estructura) ya está validada y no se re-lista aquí.

## v1 Requirements

Requisitos del milestone (FASES 2-5). Cada uno mapea a una fase del roadmap.

### CV — Parseo de CV (FASE 2)

- [x] **CV-01**: El servicio acepta un CV en PDF y extrae un `CVProfile` estructurado vía Pydantic + Instructor (LLM)
- [x] **CV-02**: El `CVProfile` incluye experiencia, skills técnicas, formación, años de experiencia total (estimado) y dominios
- [x] **CV-03**: El `CVProfile` se cachea y solo se re-parsea si el CV cambia (no re-parsear en cada run)

### NORM — Normalización de ofertas (FASE 3)

- [x] **NORM-01**: El servicio acepta una lista de ofertas crudas heterogéneas + un identificador de fuente y devuelve `Job`s normalizados
- [x] **NORM-02**: Cada `Job` recibe un `id` estable (hash de empresa + título normalizado + ubicación)
- [x] **NORM-03**: El parseo por fuente está aislado en funciones de mapeo claramente marcadas y ajustables (sin asumir formatos de API de memoria)
- [x] **NORM-04**: Una oferta mal formada no tumba el batch — se procesa lo que se puede y se reporta lo que falló

### DEDUP — Deduplicación semántica (FASE 3)

- [x] **DEDUP-01**: Deduplicación por hash exacto (empresa + título normalizado)
- [x] **DEDUP-02**: Deduplicación semántica con embeddings BGE-M3 locales sobre (título + empresa + primeras N palabras de descripción), agrupando por similitud coseno con umbral configurable
- [x] **DEDUP-03**: Al deduplicar se conserva la oferta con descripción más completa y se guardan las URLs alternativas

### SCORE — Heurística de scoring (FASE 4) ← núcleo

- [x] **SCORE-01**: Para cada oferta única, el servicio devuelve un `JobScore` con `score_total`, `recommendation` y desglose (encaje_puesto / skills / ubicación / seniority)
- [x] **SCORE-02**: El ranking de puestos actúa como PESO graduado (función de decaimiento configurable), no como filtro binario; una oferta fuera de ranking no se descarta sola
- [x] **SCORE-03**: Ubicación y remoto se evalúan según preferencias (remote permitido → alto; onsite/hybrid alto solo en ciudades aceptadas; presencial fuera sin reubicación → muy bajo)
- [x] **SCORE-04**: Seniority se compara contra la experiencia real del `CVProfile`; pedir mucho más baja el encaje y aparece en `missing_requirements`, pero no descarta solo
- [x] **SCORE-05**: Si se dispara un deal-breaker → `recommendation = skip`, `deal_breaker_hit = true` y se explica cuál (filtro duro)
- [x] **SCORE-06**: `score_total` es combinación ponderada de los cuatro sub-encajes con pesos configurables desde `profile.yaml` (defaults: puesto 35% / skills 30% / ubicación 20% / seniority 15%)
- [x] **SCORE-07**: El score es honesto: `reasons_for`, `reasons_against`, `matched_skills` (skills reales que pide la oferta) y `missing_requirements` sin inflar
- [x] **SCORE-08**: El prompt al LLM incluye CVProfile real, ranking de puestos con sinónimos, preferencias de ubicación/remoto, deal-breakers y la oferta

### API — Endpoints FastAPI (FASE 5)

- [x] **API-01**: `POST /cv/parse` — sube CV (PDF), devuelve y cachea el `CVProfile`
- [x] **API-02**: `GET /profile` — devuelve el `UserProfile` cargado
- [x] **API-03**: `POST /jobs/normalize` — recibe ofertas crudas + source, devuelve `Job`s
- [x] **API-04**: `POST /jobs/process` — recibe ofertas crudas de varias fuentes, hace normalización + dedup + scoring y devuelve ofertas únicas puntuadas y ordenadas por `score_total`, marcando las ya-vistas
- [x] **API-05**: `POST /jobs/score` — (granular) puntúa una lista de `Job`s ya normalizados
- [x] **API-06**: `GET /jobs/history` — ofertas guardadas con su score y fecha
- [x] **API-07**: Contrato pensado para n8n — JSON limpio de entrada/salida y errores con códigos HTTP claros

### STORE — Persistencia (FASE 5)

- [x] **STORE-01**: Persistencia SQLite local (stdlib sqlite3), ruta configurable vía `SQLITE_DB_PATH` (default `data/jobs.db`). 100% local, sin dependencias de red. _(Decisión 2026-05-23: Supabase eliminado del alcance — ver PROJECT.md.)_
- [x] **STORE-02**: Se guardan las ofertas con fecha (histórico para ver evolución)
- [x] **STORE-03**: Control de "ya-vistas/ya-notificadas" entre runs para que n8n no repita ofertas entre días

### OBS — Observabilidad y robustez (FASE 5 / transversal)

- [x] **OBS-01**: Logging estructurado (ofertas que entran, duplicados detectados, ofertas puntuadas, coste / nº de llamadas LLM)
- [x] **OBS-02**: Interfaz de observabilidad Langfuse preparada (stub) para trazar las llamadas de scoring
- [x] **OBS-03**: Manejo de errores por capa

### DOC — Documentación y DX (FASE 5)

- [ ] **DOC-01**: README con instalación, `.env`, cómo editar `profile.yaml`, cómo subir el CV y cómo arrancar el servicio
- [ ] **DOC-02**: Sección dedicada "Integración con n8n" (qué nodos llaman a qué endpoints, flujo, formato exacto del JSON de `/jobs/process`, cómo exponer el servicio)
- [ ] **DOC-03**: `profile.yaml` de ejemplo + un par de ofertas de ejemplo (JSON) para probar `/jobs/process` sin n8n

### QA — Tests (mapeados a su fase)

- [x] **QA-01**: Test de parseo de CV con fixture PDF de ejemplo (LLM mockeado)
- [x] **QA-02**: Tests de normalización por fuente
- [x] **QA-03**: Tests de dedup (detecta duplicados obvios y casos semánticos; embeddings mockeados)
- [x] **QA-04**: Tests exhaustivos de la heurística de scoring (el ranking pesa bien, un deal-breaker fuerza skip, la ubicación se evalúa correcto; LLM mockeado)

## v2 Requirements

Reconocidos pero diferidos; no en el roadmap actual.

### Observabilidad

- **OBS-04**: Cableado completo de Langfuse (más allá del stub) con trazas reales de coste/latencia por llamada

### Persistencia

- **STORE-04**: Métricas/analítica sobre el histórico (evolución de matches en el tiempo)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Frontend / dashboard web propio | n8n se encarga de la entrega; el foco es el servicio inteligente headless |
| Orquestación n8n (Schedule, llamadas a APIs de empleo, Merge, entrega email/telegram) | Fuera de este código; se diseña pensando en ello pero se construye en n8n |
| Embeddings vía API (OpenAI u otros) | Decisión: BGE-M3 local (gratis, privado, coincide con el spec) |
| Scraping / llamadas salientes a APIs de empleo | Las hace n8n y nos manda las ofertas crudas |
| Autenticación / multi-usuario | Herramienta personal de un solo usuario (Jaime) |

## Traceability

> Nota: las etiquetas (FASE 2-5) del spec CLAUDE.md mapean a las fases del roadmap así:
> FASE 2 → Phase 1 (CV), FASE 3 → Phase 2 (Norm+Dedup), FASE 4 → Phase 3 (Scoring),
> FASE 5 → Phase 4 (API+Persistencia) + Phase 5 (Observabilidad+Docs).

| Requirement | Phase | Status |
|-------------|-------|--------|
| CV-01 | Phase 1 | Complete |
| CV-02 | Phase 1 | Complete |
| CV-03 | Phase 1 | Complete |
| QA-01 | Phase 1 | Complete |
| NORM-01 | Phase 2 | Complete |
| NORM-02 | Phase 2 | Complete |
| NORM-03 | Phase 2 | Complete |
| NORM-04 | Phase 2 | Complete |
| DEDUP-01 | Phase 2 | Complete |
| DEDUP-02 | Phase 2 | Complete |
| DEDUP-03 | Phase 2 | Complete |
| QA-02 | Phase 2 | Complete |
| QA-03 | Phase 2 | Complete |
| SCORE-01 | Phase 3 | Complete |
| SCORE-02 | Phase 3 | Complete |
| SCORE-03 | Phase 3 | Complete |
| SCORE-04 | Phase 3 | Complete |
| SCORE-05 | Phase 3 | Complete |
| SCORE-06 | Phase 3 | Complete |
| SCORE-07 | Phase 3 | Complete |
| SCORE-08 | Phase 3 | Complete |
| QA-04 | Phase 3 | Complete |
| API-01 | Phase 4 | Complete |
| API-02 | Phase 4 | Complete |
| API-03 | Phase 4 | Complete |
| API-04 | Phase 4 | Complete |
| API-05 | Phase 4 | Complete |
| API-06 | Phase 4 | Complete |
| API-07 | Phase 4 | Complete |
| STORE-01 | Phase 4 | Complete |
| STORE-02 | Phase 4 | Complete |
| STORE-03 | Phase 4 | Complete |
| OBS-01 | Phase 5 | Complete |
| OBS-02 | Phase 5 | Complete |
| OBS-03 | Phase 5 | Complete |
| DOC-01 | Phase 5 | Pending |
| DOC-02 | Phase 5 | Pending |
| DOC-03 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 38 total (el doc inicial decía "37"; el conteo real de IDs únicos es 38)
- Mapped to phases: 38 ✓
- Unmapped: 0 ✓

**Por fase:**
- Phase 1 (Parseo de CV): 4 — CV-01, CV-02, CV-03, QA-01
- Phase 2 (Normalización y Deduplicación): 9 — NORM-01..04, DEDUP-01..03, QA-02, QA-03
- Phase 3 (Heurística de Scoring): 9 — SCORE-01..08, QA-04
- Phase 4 (API y Persistencia): 10 — API-01..07, STORE-01..03
- Phase 5 (Observabilidad, Robustez y Docs): 6 — OBS-01..03, DOC-01..03

---
*Requirements defined: 2026-05-22*
*Last updated: 2026-05-22 after roadmap creation (traceability mapped)*
