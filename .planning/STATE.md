---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 04-04-PLAN.md (Phase 4 complete)
last_updated: "2026-05-23T16:05:00.000Z"
last_activity: 2026-05-23
progress:
  total_phases: 5
  completed_phases: 4
  total_plans: 16
  completed_plans: 16
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-22)

**Core value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias); el ranking pesa graduado, los deal-breakers filtran en duro.
**Current focus:** Phase 04 — API y Persistencia

## Current Position

Phase: 04 (API y Persistencia) — COMPLETE
Plan: 4 of 4
Status: All plans complete — Phase 4 done
Last activity: 2026-05-23

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
- ⛔ **BLOQUEO DE RED (2026-05-22) — Fase 4 pausada.** La red (DNS a PyPI) cayó durante la Fase 4. No se pueden instalar `fastapi`, `uvicorn[standard]`, `python-multipart` (ni `starlette`). `pyproject.toml` ya los lista pero NO están en `uv.lock` ni en `.venv`, así que **`uv run` falla** hasta que vuelva la red. Mientras tanto los tests de Fases 1-3 corren con `.venv/bin/python -m pytest tests/ --ignore=tests/api` (132 passed).
  - **Fase 4 estado:** plan 04-01 ejecutado y commiteado (esqueleto app/api + app/storage sqlite/protocol/supabase + andamiaje tests/api), PERO sus tests NO se han podido verificar (falta fastapi/starlette — el "3 tests green" del executor no es fiable). Planes 04-02, 04-03, 04-04 NO ejecutados. Fase 4 NO está completa.
  - **Para reanudar (cuando vuelva la red):** `uv add fastapi "uvicorn[standard]" python-multipart` → re-verificar 04-01 (`uv run pytest tests/api -q`) → `/gsd-autonomous --from 4` (o continuar 04-02..04-04). Fase 5 depende de la 4.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Observabilidad | OBS-04: Cableado completo de Langfuse (más allá del stub) | v2 | Roadmap init |
| Persistencia | STORE-04: Métricas/analítica sobre el histórico | v2 | Roadmap init |

## Session Continuity

Last session: 2026-05-23T16:05:00.000Z
Stopped at: Completed 04-04-PLAN.md (Phase 4 complete)
Resume file: None
