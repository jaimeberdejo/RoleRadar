---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Deployment & n8n Integration
status: completed
stopped_at: v1.1 shipped (tag v1.1) — incremento post-MVP vía quick tasks (Docker + auth + integración n8n end-to-end + gpt-4o-mini). Sin roadmap/fases; detalle en Quick Tasks Completed.
last_updated: "2026-05-25T00:00:00.000Z"
last_activity: 2026-05-25
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 19
  completed_plans: 19
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-22)

**Core value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias); el ranking pesa graduado, los deal-breakers filtran en duro.
**Current focus:** v1.1 shipped (deploy + integración n8n funcionando). Próximo: v2 (Langfuse real, analítica histórico, pre-filtrado server-side) o más tuning.

## Current Position

Phase: 05 (Observabilidad, Robustez y Docs n8n) — COMPLETE
Plan: 3 of 3
Status: Complete
Last activity: 2026-05-24 - Completed quick task 260524-tgs: backfill automático 2 meses en la guía n8n

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: — min
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 2 | 3 tasks | 10 files |
| Phase 01-parseo-de-cv P02 | 2 | 2 tasks | 4 files |
| Phase 01-parseo-de-cv P03 | 2 | 2 tasks | 2 files |
| Phase 01-parseo-de-cv P04 | 1 | 2 tasks | 3 files |
| Phase 02-normalizacion-y-deduplicacion P03 | 262 | 2 tasks | 5 files |
| Phase 02-normalizacion-y-deduplicacion P04 | 3 | 2 tasks | 2 files |
| Phase 03-heuristica-de-scoring P02 | 15 | 2 tasks | 5 files |
| Phase 03-heuristica-de-scoring P03 | 12 | 1 task | 2 files |
| Phase 03-heuristica-de-scoring P04 | 253 | 2 tasks | 5 files |
| Phase 04-api-y-persistencia P03 | 4min | 3 tasks | 5 files |
| Phase 04-api-y-persistencia P04 | 7min | 4 tasks | 3 files |
| Phase 05-observabilidad-robustez-docs P01 | 318 | 3 tasks | 6 files |
| Phase 05-observabilidad-robustez-docs P02 | 25 | - tasks | - files |
| Phase 05-observabilidad-robustez-docs P03 | 15min | 2 tasks | 6 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Setup]: Servicio headless, sin frontend propio — n8n entrega; foco en la inteligencia
- [Setup]: Embeddings BGE-M3 LOCAL (no API) — gratis, privado, coincide con el spec
- [Setup]: SQLite primero, Supabase como upgrade — arrancar local sin deps externas
- [Setup]: Construir FASES 2-5 en este milestone — sistema completo usable de verdad
- [Roadmap]: Scoring (FASE 4) tiene su propia fase dedicada (Phase 3) por ser el núcleo
- [Phase ?]: Use pymupdf for in-memory PDF fixture generation instead of reportlab — pymupdf already a core dep
- [Phase ?]: Cache-first ordering: hash+cache check before any extraction or LLM call — repeated malformed PDFs are cheap
- [Phase ?]: Mock at import site: patch app.cv.parser.build_instructor_client (not definition site) so patched name is intercepted in parser namespace
- [Phase ?]: NFD not NFC for accent normalization
- [Phase ?]: NFD decomposes precomposed chars; NFC keeps them intact
- [Phase ?]: stable_job_id returns full 64-char sha256 hex — matches Phase 1 _HEX_RE pattern from cv/cache.py
- [Phase ?]: arbeitnow remote=False maps to RemoteJob.unknown — not onsite; RemoteJob.remote only when remote=True
- [Phase ?]: Parametros de decay (paso, suelo, maximo) como defaults en codigo — no en profile.yaml. Simplifica schema de UserProfile; ajuste diferido a v2.
- [Phase ?]: yaml.safe_load exclusivamente en loader para mitigar ejecucion de codigo arbitrario (T-03-04).
- [Phase ?]: NFD replicado localmente en scoring/location.py — no importar app.dedup para mantener tests de scoring torch-free (Pitfall 7).
- [Phase ?]: Substring city match en evaluar_ubicacion: any(norm(c) in norm(loc)) para que 'Barcelona, España' matchee 'Barcelona'.
- [Phase ?]: deal-breaker override last: score_total stays honest, only recommendation→skip
- [Phase ?]: fixed system prompt (anti prompt-injection): offer in XML <oferta> section, system is string literal
- [Phase ?]: scoring module never imports app.dedup: scorer receives deduplicated Jobs (keeps tests fast <1s)
- [Phase ?]: Separación de responsabilidades
- [Phase 4 P04]: was_seen computed BEFORE upsert — if after, every offer in own run would be ya_visto=True
- [Phase 4 P04]: ScoredJobConVisto wraps ScoredJob+ya_visto without mutating core ScoredJob schema
- [Phase 4 P04]: limit clamped silently in GET /jobs/history to avoid breaking n8n on out-of-range params

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- REQUIREMENTS.md decía "37 total" pero el conteo real de IDs únicos es 38 (CV 3 + NORM 4 + DEDUP 3 + SCORE 8 + API 7 + STORE 3 + OBS 3 + DOC 3 + QA 4). Coverage corregido a 38/38.
- ✅ **RESUELTO (2026-05-23) — bloqueo de red de la Fase 4.** La red volvió; se instalaron `fastapi`/`uvicorn[standard]`/`python-multipart` y se reconcilió `uv.lock`. Fase 4 completada y verificada (162→ahora 179 tests). Supabase eliminado del alcance por decisión del usuario (solo SQLite local). `uv run` funciona con normalidad.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260523-u5d | Dockerfile + docker-compose + nota de despliegue Docker (con aviso de que la key de JSearch/RapidAPI va en n8n, no aquí) | 2026-05-24 | aa08eb1 | [260523-u5d-crear-dockerfile-docker-compose-nota-de-](./quick/260523-u5d-crear-dockerfile-docker-compose-nota-de-/) |
| 260524-sg6 | Autenticación opcional X-API-Key via Starlette middleware; /health pública; /docs protegida; secrets.compare_digest; 185→195 tests | 2026-05-24 | 9753539 | [260524-sg6-anadir-autenticacion-por-api-key-cabecer](./quick/260524-sg6-anadir-autenticacion-por-api-key-cabecer/) |
| 260524-sv8 | Guía paso a paso docs/N8N-WORKFLOW.md (montar el workflow en n8n nodo a nodo: Schedule→HTTP→Code→/jobs/process→Filter→Telegram), enlazada desde el README | 2026-05-24 | b17770c | [260524-sv8-crear-docs-n8n-workflow-md-guia-paso-a-p](./quick/260524-sv8-crear-docs-n8n-workflow-md-guia-paso-a-p/) |
| fast | docs/N8N-WORKFLOW.md: patrón multi-query JSearch (lista de queries + `={{ $json.query }}`) y Code node con `.all()`/flatMap en vez de `.first()` | 2026-05-24 | 2f99fd5 | — (gsd-fast, follow-up de 260524-sv8) |
| 260524-tgs | docs/N8N-WORKFLOW.md: backfill automático de 2 meses en el primer run (Nodo 1.5 HTTP /jobs/history + Code "Modo de búsqueda"; JSearch con date_posted/num_pages por expresión; filtro 60 días en Code ProcessRequest) | 2026-05-24 | ef4a9b5 | [260524-tgs-ampliar-docs-n8n-workflow-md-con-backfil](./quick/260524-tgs-ampliar-docs-n8n-workflow-md-con-backfil/) |
| fast | n8n/workflow.json importable (11 nodos, flujo completo, keys por $env sin hardcodear) + sección "Importar el workflow" en la guía | 2026-05-24 | 323dafd | — (gsd-fast) |
| fast | servicio n8n añadido al docker-compose.yml (puerto 5678, volumen n8n_data, $env, keys interpoladas desde .env) + URLs del workflow.json a buscadordeempleo:8000 | 2026-05-24 | fc2877e | — (gsd-fast) |
| fast | sub-flujo "Subir CV (una vez)" en workflow.json (Form Trigger → POST /cv/parse multipart) + sección en la guía | 2026-05-24 | d34fae9 | — (gsd-fast) |
| fast | fix .dockerignore: excluir data/jobs.db y data/.cache/ (los patrones raíz *.db/.cache no matchean rutas anidadas → la BD de test se horneaba en la imagen y sembraba el volumen, rompiendo el primer-run del backfill) | 2026-05-24 | 7a04c37 | — (gsd-fast) |
| fast | backfill por defecto a 1 mes + num_pages 1 (antes 2 meses/10 páginas) en workflow.json y guía; documentado cómo subir a ~2 meses | 2026-05-24 | ed8a41b | — (gsd-fast) |
| fast | bajar umbral del Filter de score 70→50 en workflow.json y guía | 2026-05-24 | 4f2150e | — (gsd-fast) |

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Observabilidad | OBS-04: Cableado completo de Langfuse (más allá del stub) | v2 | Roadmap init |
| Persistencia | STORE-04: Métricas/analítica sobre el histórico | v2 | Roadmap init |
| verification_gap | Phase 01 (parseo CV): verificación manual del CVProfile contra el CV real + ANTHROPIC_API_KEY (los tests mockean el LLM por diseño) | human_needed | v1.0 close (2026-05-23) |
| manual_check | Calidad real del dedup BGE-M3 (modelo ~2.3GB) y del juicio LLM de scoring con ofertas reales | human_needed | v1.0 close (2026-05-23) |

## Session Continuity

Last session: 2026-05-23
Stopped at: Completed 05-03-PLAN.md — Phase 5 complete; all 5 phases done; milestone v1.0 complete
Resume file: None
