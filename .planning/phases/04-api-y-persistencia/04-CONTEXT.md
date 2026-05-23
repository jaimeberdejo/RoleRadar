# Phase 4: API y Persistencia - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning
**Mode:** Smart discuss (autonomous, defaults auto-accepted — user hands-off)

<domain>
## Phase Boundary

Exponer el servicio como una API HTTP/JSON (FastAPI) consumible por n8n que orquesta
parseo de CV + normalización + dedup + scoring de punta a punta, persiste el histórico con
fecha (SQLite-first) y recuerda qué ofertas ya se vieron entre runs. Entrega `app/api/`
(endpoints) + `app/storage/` (persistencia) + tests con TestClient (LLM y embedder mockeados).

Fuera de boundary: observabilidad Langfuse real (Fase 5), README/docs n8n (Fase 5),
orquestación n8n en sí (la hace n8n por fuera), llamadas a APIs de empleo (n8n).
</domain>

<decisions>
## Implementation Decisions

### App FastAPI (app/api/)
- Deps nuevas: `fastapi`, `uvicorn[standard]`, `python-multipart` (para subir el PDF en /cv/parse). `uv add`.
- Estructura: `app/api/main.py` crea la instancia `FastAPI()` e incluye routers; routers por concern en `app/api/routes/`: `cv.py`, `profile.py`, `jobs.py`. (Claude's discretion sobre el split exacto.)
- Arrancable con `uvicorn app.api.main:app`. Documentar el comando (README es Fase 5).

### Endpoints (contrato para n8n — JSON limpio, códigos HTTP claros)
- **POST /cv/parse**: recibe el CV en PDF (multipart UploadFile) → `parse_cv` (Fase 1) → `CVProfile` (cacheado). Devuelve el CVProfile. (API-01)
- **GET /profile**: `load_user_profile` (Fase 3) → `UserProfile`. (API-02)
- **POST /jobs/normalize**: body `{source: str, offers: [dict]}` → `normalize_jobs` (Fase 2) → `{jobs: [Job], errors: [dict]}`. (API-03)
- **POST /jobs/score**: body `{jobs: [Job]}` (ya normalizados) → puntúa cada uno con `score_job` (Fase 3) usando el CVProfile cacheado + UserProfile → `[ScoredJob]`. (API-05)
- **POST /jobs/process**: body `{sources: [{source, offers}]}` (o `{source, offers}` simple) → normaliza todas + dedup (Fase 2) + score (Fase 3) → `[ScoredJob]` ORDENADAS por `score_total` desc, marcando `ya_visto` (vistas en runs anteriores), y persiste. ESTE es el endpoint principal de n8n. (API-04)
- **GET /jobs/history**: ofertas guardadas con su score y fecha (paginable simple). (API-06)
- Contrato n8n (API-07): modelos Pydantic de request/response; errores con códigos HTTP claros (400 input inválido, 422 validación Pydantic automática, 404 si falta CVProfile cacheado en /jobs/score|process con guía "llama a /cv/parse primero", 500 con mensaje claro). Una oferta mal formada NO tumba el batch (reusar la resiliencia de Fase 2; reportar `errors` en la respuesta).

### Dependencia del CVProfile para scoring
- /jobs/score y /jobs/process necesitan un `CVProfile`. Usar el CVProfile CACHEADO por /cv/parse
  (Fase 1 cache). Si no hay ninguno cacheado → responder 4xx claro pidiendo llamar a /cv/parse
  primero (o aceptar el CV en el body como alternativa — Claude's discretion; mínimo: usar caché).

### Persistencia (app/storage/) — SQLite-first
- **Abstracción `Storage` (Protocol/ABC)** con métodos tipo: `upsert_scored_jobs(scored: list[ScoredJob]) -> None`, `was_seen(job_id) -> bool` / `mark_seen(...)`, `get_history(...) -> list[...]`.
- **`SQLiteStorage`** implementación completa con **stdlib `sqlite3`** (NO SQLAlchemy — evitar dep pesada). Tablas: `jobs` (id PK, title, company, location, remote, url, source, score_total, recommendation, score_json, first_seen, last_seen, notified/seen flag). Histórico con fecha (STORE-02).
- **Control de ya-vistas (STORE-03)**: persistir los `Job.id` vistos; en /jobs/process marcar cada resultado con `ya_visto` = existía en runs anteriores; insertar/actualizar los nuevos. Así n8n no repite ofertas entre días.
- **Storage local (STORE-01)** — _ACTUALIZADO 2026-05-23: Supabase ELIMINADO del alcance._ Solo `SQLiteStorage` (stdlib sqlite3), ruta configurable vía `SQLITE_DB_PATH` (default `data/jobs.db`). 100% local, sin nube, sin selección por env de Supabase. El `Protocol` (`app/storage/protocol.py`) permite añadir otro backend en el futuro si hiciera falta DB en red.

### Inyección de dependencias (testabilidad)
- El cliente LLM (scoring + cv parse) y el `Embedder` (dedup) se inyectan vía FastAPI `Depends`,
  de modo que los tests usen `TestClient` con `app.dependency_overrides` para mockear LLM/embedder
  → CERO red en tests. El `Storage` también inyectable (tests usan SQLite temporal / tmp_path).

### Tests
- `tests/api/` con FastAPI `TestClient`. Cada endpoint: happy path + error (input inválido, falta CVProfile). /jobs/process end-to-end con LLM+embedder mockeados y SQLite temporal: verifica orden por score_total, marca ya_visto en segundo run, persistencia e historial. Una oferta mal formada → va a errors, no rompe.
- `tests/storage/` para SQLiteStorage (upsert, was_seen, history) con DB temporal.

### Claude's Discretion
- Split exacto de routers y nombres de los modelos request/response
- Esquema exacto de tablas SQLite y formato de score_json
- Grado de implementación del SupabaseStorage skeleton (mínimo: Protocol + selección + NotImplemented/parcial)
- Si /jobs/score|process aceptan CV en body además de usar caché
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Fase 1: `app.cv.parse_cv(pdf_bytes) -> CVProfile` (cacheado). 
- Fase 2: `app.dedup.normalize_jobs(raw, source) -> (jobs, errors)` y `app.dedup.deduplicate(jobs, embedder=None) -> [Job]`.
- Fase 3: `app.scoring.score_job(job, cv_profile, user_profile, client=None) -> JobScore`; `app.config.load_user_profile() -> UserProfile`.
- Schemas: `Job`, `ScoredJob`, `JobScore`, `CVProfile`, `UserProfile` en `app/models/schemas.py`.
- Patrón de cliente LLM inyectable + mock en tests (Fases 1-3) → reutilizar para los Depends.

### Established Patterns
- Pydantic v2, type hints, Spanish naming. `uv add` para deps. Lazy import para deps pesadas.
- Mock del LLM y del embedder en tests (nunca red, nunca descargar BGE-M3).
- `app.dedup` y `app.scoring` son torch-free al importar; mantener la app importable sin cargar torch hasta que se use el embedder real.

### Integration Points
- /jobs/process es el endpoint que n8n llama a diario. Su contrato JSON se documentará en el README (Fase 5).
- La llamada de scoring se envolverá con Langfuse en Fase 5; mantener el punto de inyección limpio.
</code_context>

<specifics>
## Specific Ideas

- n8n manda ofertas crudas de varias fuentes (Arbeitnow, JSearch, FlyByAPIs) → /jobs/process.
- El valor: devolver ofertas únicas, puntuadas, ordenadas, y marcadas ya_visto para no repetir.
- Salud: incluir un GET /health simple para que n8n/monitorización compruebe que el servicio está vivo (barato, útil).
</specifics>

<deferred>
## Deferred Ideas

- Implementación real completa de Supabase + pgvector (skeleton ahora; real cuando se conecte)
- Observabilidad Langfuse alrededor del scoring (Fase 5)
- README + sección integración n8n (Fase 5)
- Autenticación de la API (fuera de scope v1 — herramienta personal; n8n la alcanza en localhost/red privada)
</deferred>
