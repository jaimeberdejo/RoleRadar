---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: "Completed 01-04-PLAN.md (Phase 1 complete: parse_cv orchestrator + QA-01 acceptance test)"
last_updated: "2026-05-22T01:09:03.986Z"
last_activity: 2026-05-22
progress:
  total_phases: 5
  completed_phases: 1
  total_plans: 8
  completed_plans: 7
  percent: 88
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-22)

**Core value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias); el ranking pesa graduado, los deal-breakers filtran en duro.
**Current focus:** Phase 02 — Normalización y Deduplicación

## Current Position

Phase: 02 (Normalización y Deduplicación) — EXECUTING
Plan: 4 of 4
Status: Ready to execute
Last activity: 2026-05-22

Progress: [█████████░] 88%

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

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

None yet.

### Blockers/Concerns

[Issues that affect future work]

- REQUIREMENTS.md decía "37 total" pero el conteo real de IDs únicos es 38 (CV 3 + NORM 4 + DEDUP 3 + SCORE 8 + API 7 + STORE 3 + OBS 3 + DOC 3 + QA 4). Coverage corregido a 38/38.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Observabilidad | OBS-04: Cableado completo de Langfuse (más allá del stub) | v2 | Roadmap init |
| Persistencia | STORE-04: Métricas/analítica sobre el histórico | v2 | Roadmap init |

## Session Continuity

Last session: 2026-05-22T01:09:03.982Z
Stopped at: Completed 01-04-PLAN.md (Phase 1 complete: parse_cv orchestrator + QA-01 acceptance test)
Resume file: None
