# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-22)

**Core value:** Puntuar y filtrar ofertas con honestidad contra el perfil REAL de Jaime (CV verdadero + ranking de puestos + preferencias); el ranking pesa graduado, los deal-breakers filtran en duro.
**Current focus:** Phase 1 — Parseo de CV

## Current Position

Phase: 1 of 5 (Parseo de CV)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-05-22 — Roadmap created, 38 v1 requirements mapped across 5 phases

Progress: [░░░░░░░░░░] 0%

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

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Setup]: Servicio headless, sin frontend propio — n8n entrega; foco en la inteligencia
- [Setup]: Embeddings BGE-M3 LOCAL (no API) — gratis, privado, coincide con el spec
- [Setup]: SQLite primero, Supabase como upgrade — arrancar local sin deps externas
- [Setup]: Construir FASES 2-5 en este milestone — sistema completo usable de verdad
- [Roadmap]: Scoring (FASE 4) tiene su propia fase dedicada (Phase 3) por ser el núcleo

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

Last session: 2026-05-22
Stopped at: ROADMAP.md and STATE.md created; REQUIREMENTS.md traceability updated
Resume file: None
