# Phase 2: Normalización y Deduplicación - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, defaults auto-accepted — user hands-off)

<domain>
## Phase Boundary

Convertir listas de ofertas crudas heterogéneas (de cualquier fuente) en `Job`s
normalizados con id estable (schema `Job` ya definido en `app/models/schemas.py`), y
eliminar duplicados en dos niveles: hash exacto y semántico (embeddings BGE-M3 locales).
Entrega módulos reutilizables bajo `app/dedup/` (y normalización bajo `app/dedup/` o un
`app/normalize/` — Claude's discretion) + tests con embeddings mockeados.

Fuera de boundary: scoring (Fase 3), endpoints HTTP (Fase 4), persistencia en DB (Fase 4),
llamadas salientes a APIs de empleo (las hace n8n). Las fuentes se reciben ya como payloads.
</domain>

<decisions>
## Implementation Decisions

### Normalización de ofertas
- Entrada: lista de ofertas crudas (dicts heterogéneos) + un identificador de `source`. Salida: lista de `Job` normalizados.
- **Mapeo por fuente aislado en un registry**: un dict/registro `source -> mapper_fn`. Implementar al menos un mapper de ejemplo (p.ej. `arbeitnow`, citado en CLAUDE.md) + un mapper `generic` de fallback. Los mappers están claramente marcados como AJUSTABLES (no asumir formatos de API de memoria; el usuario los afinará contra respuestas reales). Cada mapper traduce el payload crudo → campos de `Job`.
- **id estable**: hash (sha256) de `normalize(company) + "|" + normalize(title) + "|" + normalize(location)`, donde normalize = lowercase + strip + colapsar espacios. Mismo input → mismo id entre runs.
- **Batch resiliente**: procesar oferta a oferta con try/except; una oferta mal formada NO tumba el batch. Devolver `(jobs: list[Job], errors: list[dict])` donde errors registra índice/source/motivo. Logging estructurado del conteo.
- `remote` se infiere a enum (`remote/hybrid/onsite/unknown`) desde el payload cuando sea posible; `unknown` si no.

### Deduplicación
- **Nivel 1 — hash exacto**: agrupar por (empresa normalizada + título normalizado). Colisión exacta → duplicado.
- **Nivel 2 — semántico**: embeddings BGE-M3 locales sobre el texto `título + " " + empresa + " " + primeras N palabras de la descripción` (N configurable, default ~50). Similitud coseno; si ≥ `dedup_umbral` (de profile.yaml, default 0.85) → mismo grupo.
- **Abstracción `Embedder` (protocol/ABC)**: el módulo de dedup NO debe requerir torch para importarse. La implementación real (`Bge M3Embedder`) hace **lazy import** de `sentence-transformers` dentro de `__init__`/primera llamada y carga `BAAI/bge-m3` perezosamente. Tests inyectan un `FakeEmbedder` determinista (sin red, sin torch). Esto hace dedup testeable y rápido en CI.
- Librería: **sentence-transformers** (`SentenceTransformer("BAAI/bge-m3")`) por API simple y buena documentación (vs FlagEmbedding). Justificar en RESEARCH.
- **Al fusionar duplicados**: conservar la oferta con la descripción más completa (más larga / más campos) como canónica; acumular las `url` de las descartadas en `urls_alternativas`.
- Función pública tipo `deduplicate(jobs, embedder=None, umbral=0.85, desc_words=50) -> list[Job]`.

### Tests (QA-02, QA-03)
- QA-02: normalización por fuente — dado un payload de ejemplo por source, el mapper produce el `Job` esperado; oferta mal formada → va a `errors`, no rompe el batch.
- QA-03: dedup — detecta duplicados obvios (hash exacto) y casos semánticos (con `FakeEmbedder` que devuelve vectores controlados para forzar alta/baja similitud); verifica que se conserva la descripción más completa y se acumulan urls_alternativas.
- Embeddings SIEMPRE mockeados en tests (no descargar BGE-M3 en CI).

### Claude's Discretion
- Ubicación exacta de la normalización (`app/dedup/normalize.py` vs nuevo `app/normalize/`)
- Estructura interna de módulos de dedup (embedder, exact, semantic, merge)
- N exacto de palabras de descripción y forma de medir "descripción más completa"
- Algoritmo de agrupación semántica (greedy por umbral, suficiente)
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `app/models/schemas.py`: `Job` (con `id`, `urls_alternativas`, `remote: RemoteJob`, `salary`, `raw`), `RemoteJob` enum, `Salary`. Usar tal cual.
- `app/cv/` (Fase 1) establece el patrón de módulos: extractor/cache/llm_client/parser con dependency injection y lazy import para deps pesadas + tests que mockean la dependencia externa. Replicar ese patrón para el embedder (igual que se mockeó el LLM client).
- `tests/conftest.py` ya existe; añadir fixtures de dedup (FakeEmbedder, payloads de ejemplo).

### Established Patterns
- Pydantic v2, type hints, Spanish naming. `uv add` para deps. Python >=3.13.
- Lazy import + injectable dependency for heavy/external deps (probado en Fase 1 con el LLM client) → aplicar al `Embedder`.
- Deps nuevas esta fase: `sentence-transformers` (trae torch — dep pesada aceptada conscientemente por decisión bloqueada).

### Integration Points
- Salida (`Job`s únicos) la consumirá el scoring (Fase 3) y el endpoint `/jobs/normalize` + `/jobs/process` (Fase 4).
- `dedup_umbral` se lee de `data/profile.yaml` (UserProfile.dedup_umbral) — el cargador de perfil puede no existir aún; de momento aceptar el umbral como parámetro con default 0.85 (el wiring al profile.yaml puede ser en Fase 4 cuando se cargue UserProfile, o un loader mínimo aquí — Claude's discretion).
</code_context>

<specifics>
## Specific Ideas

- CLAUDE.md menciona fuentes: Arbeitnow, JSearch, FlyByAPIs. Usar Arbeitnow como mapper de ejemplo (es de formato conocido/abierto), el resto como stubs ajustables.
- Conservar el payload original en `Job.raw` para depurar mapeos contra respuestas reales.
</specifics>

<deferred>
## Deferred Ideas

- Persistencia de embeddings en pgvector (Fase 4 / Supabase)
- Carga real de UserProfile desde profile.yaml si se decide diferir a Fase 4
- Mappers afinados contra respuestas reales de cada API (el usuario los ajusta con datos reales)
</deferred>
