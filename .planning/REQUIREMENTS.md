# Requirements: BuscadorDeEmpleo

**Defined:** 2026-05-22
**Core Value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias), con el ranking como peso graduado y los deal-breakers como filtro duro.

> Nota: es un **servicio headless** consumido por n8n. Los requisitos se expresan como
> capacidades del servicio (no "User can X" de UI). FASE 1 (schemas + profile.yaml +
> estructura) ya está validada y no se re-lista aquí.

## v1 Requirements

Requisitos del milestone (FASES 2-5). Cada uno mapea a una fase del roadmap.

### CV — Parseo de CV (FASE 2)

- [ ] **CV-01**: El servicio acepta un CV en PDF y extrae un `CVProfile` estructurado vía Pydantic + Instructor (LLM)
- [ ] **CV-02**: El `CVProfile` incluye experiencia, skills técnicas, formación, años de experiencia total (estimado) y dominios
- [ ] **CV-03**: El `CVProfile` se cachea y solo se re-parsea si el CV cambia (no re-parsear en cada run)

### NORM — Normalización de ofertas (FASE 3)

- [ ] **NORM-01**: El servicio acepta una lista de ofertas crudas heterogéneas + un identificador de fuente y devuelve `Job`s normalizados
- [ ] **NORM-02**: Cada `Job` recibe un `id` estable (hash de empresa + título normalizado + ubicación)
- [ ] **NORM-03**: El parseo por fuente está aislado en funciones de mapeo claramente marcadas y ajustables (sin asumir formatos de API de memoria)
- [ ] **NORM-04**: Una oferta mal formada no tumba el batch — se procesa lo que se puede y se reporta lo que falló

### DEDUP — Deduplicación semántica (FASE 3)

- [ ] **DEDUP-01**: Deduplicación por hash exacto (empresa + título normalizado)
- [ ] **DEDUP-02**: Deduplicación semántica con embeddings BGE-M3 locales sobre (título + empresa + primeras N palabras de descripción), agrupando por similitud coseno con umbral configurable
- [ ] **DEDUP-03**: Al deduplicar se conserva la oferta con descripción más completa y se guardan las URLs alternativas

### SCORE — Heurística de scoring (FASE 4) ← núcleo

- [ ] **SCORE-01**: Para cada oferta única, el servicio devuelve un `JobScore` con `score_total`, `recommendation` y desglose (encaje_puesto / skills / ubicación / seniority)
- [ ] **SCORE-02**: El ranking de puestos actúa como PESO graduado (función de decaimiento configurable), no como filtro binario; una oferta fuera de ranking no se descarta sola
- [ ] **SCORE-03**: Ubicación y remoto se evalúan según preferencias (remote permitido → alto; onsite/hybrid alto solo en ciudades aceptadas; presencial fuera sin reubicación → muy bajo)
- [ ] **SCORE-04**: Seniority se compara contra la experiencia real del `CVProfile`; pedir mucho más baja el encaje y aparece en `missing_requirements`, pero no descarta solo
- [ ] **SCORE-05**: Si se dispara un deal-breaker → `recommendation = skip`, `deal_breaker_hit = true` y se explica cuál (filtro duro)
- [ ] **SCORE-06**: `score_total` es combinación ponderada de los cuatro sub-encajes con pesos configurables desde `profile.yaml` (defaults: puesto 35% / skills 30% / ubicación 20% / seniority 15%)
- [ ] **SCORE-07**: El score es honesto: `reasons_for`, `reasons_against`, `matched_skills` (skills reales que pide la oferta) y `missing_requirements` sin inflar
- [ ] **SCORE-08**: El prompt al LLM incluye CVProfile real, ranking de puestos con sinónimos, preferencias de ubicación/remoto, deal-breakers y la oferta

### API — Endpoints FastAPI (FASE 5)

- [ ] **API-01**: `POST /cv/parse` — sube CV (PDF), devuelve y cachea el `CVProfile`
- [ ] **API-02**: `GET /profile` — devuelve el `UserProfile` cargado
- [ ] **API-03**: `POST /jobs/normalize` — recibe ofertas crudas + source, devuelve `Job`s
- [ ] **API-04**: `POST /jobs/process` — recibe ofertas crudas de varias fuentes, hace normalización + dedup + scoring y devuelve ofertas únicas puntuadas y ordenadas por `score_total`, marcando las ya-vistas
- [ ] **API-05**: `POST /jobs/score` — (granular) puntúa una lista de `Job`s ya normalizados
- [ ] **API-06**: `GET /jobs/history` — ofertas guardadas con su score y fecha
- [ ] **API-07**: Contrato pensado para n8n — JSON limpio de entrada/salida y errores con códigos HTTP claros

### STORE — Persistencia (FASE 5)

- [ ] **STORE-01**: Persistencia SQLite-first, con upgrade a Supabase (Postgres + pgvector) y credenciales desde entorno
- [ ] **STORE-02**: Se guardan las ofertas con fecha (histórico para ver evolución)
- [ ] **STORE-03**: Control de "ya-vistas/ya-notificadas" entre runs para que n8n no repita ofertas entre días

### OBS — Observabilidad y robustez (FASE 5 / transversal)

- [ ] **OBS-01**: Logging estructurado (ofertas que entran, duplicados detectados, ofertas puntuadas, coste / nº de llamadas LLM)
- [ ] **OBS-02**: Interfaz de observabilidad Langfuse preparada (stub) para trazar las llamadas de scoring
- [ ] **OBS-03**: Manejo de errores por capa

### DOC — Documentación y DX (FASE 5)

- [ ] **DOC-01**: README con instalación, `.env`, cómo editar `profile.yaml`, cómo subir el CV y cómo arrancar el servicio
- [ ] **DOC-02**: Sección dedicada "Integración con n8n" (qué nodos llaman a qué endpoints, flujo, formato exacto del JSON de `/jobs/process`, cómo exponer el servicio)
- [ ] **DOC-03**: `profile.yaml` de ejemplo + un par de ofertas de ejemplo (JSON) para probar `/jobs/process` sin n8n

### QA — Tests (mapeados a su fase)

- [ ] **QA-01**: Test de parseo de CV con fixture PDF de ejemplo (LLM mockeado)
- [ ] **QA-02**: Tests de normalización por fuente
- [ ] **QA-03**: Tests de dedup (detecta duplicados obvios y casos semánticos; embeddings mockeados)
- [ ] **QA-04**: Tests exhaustivos de la heurística de scoring (el ranking pesa bien, un deal-breaker fuerza skip, la ubicación se evalúa correcto; LLM mockeado)

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

Se rellena durante la creación del roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CV-01 | TBD | Pending |
| CV-02 | TBD | Pending |
| CV-03 | TBD | Pending |
| NORM-01 | TBD | Pending |
| NORM-02 | TBD | Pending |
| NORM-03 | TBD | Pending |
| NORM-04 | TBD | Pending |
| DEDUP-01 | TBD | Pending |
| DEDUP-02 | TBD | Pending |
| DEDUP-03 | TBD | Pending |
| SCORE-01 | TBD | Pending |
| SCORE-02 | TBD | Pending |
| SCORE-03 | TBD | Pending |
| SCORE-04 | TBD | Pending |
| SCORE-05 | TBD | Pending |
| SCORE-06 | TBD | Pending |
| SCORE-07 | TBD | Pending |
| SCORE-08 | TBD | Pending |
| API-01 | TBD | Pending |
| API-02 | TBD | Pending |
| API-03 | TBD | Pending |
| API-04 | TBD | Pending |
| API-05 | TBD | Pending |
| API-06 | TBD | Pending |
| API-07 | TBD | Pending |
| STORE-01 | TBD | Pending |
| STORE-02 | TBD | Pending |
| STORE-03 | TBD | Pending |
| OBS-01 | TBD | Pending |
| OBS-02 | TBD | Pending |
| OBS-03 | TBD | Pending |
| DOC-01 | TBD | Pending |
| DOC-02 | TBD | Pending |
| DOC-03 | TBD | Pending |
| QA-01 | TBD | Pending |
| QA-02 | TBD | Pending |
| QA-03 | TBD | Pending |
| QA-04 | TBD | Pending |

**Coverage:**
- v1 requirements: 37 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 37 ⚠️

---
*Requirements defined: 2026-05-22*
*Last updated: 2026-05-22 after initial definition*
