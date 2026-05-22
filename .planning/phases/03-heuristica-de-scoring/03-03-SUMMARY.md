---
phase: 03-heuristica-de-scoring
plan: "03"
subsystem: scoring
tags: [python, pydantic, scoring, location, deterministic, nfd, unicode]

# Dependency graph
requires:
  - phase: 03-heuristica-de-scoring
    provides: "app/models/schemas.py: Job, RemoteJob, ModalidadRemoto, UserProfile, PreferenciasUbicacion, PreferenciaRemoto"
  - phase: 03-heuristica-de-scoring
    provides: "03-02 conftest fixtures: sample_user_profile, sample_job_onsite_barcelona, sample_job_onsite_madrid, sample_job_remote"
provides:
  - "app/scoring/location.py: evaluar_ubicacion(job, profile) -> tuple[int, str|None] determinista para SCORE-03"
  - "tests/scoring/test_location.py: 13 tests cubriendo las 8 ramas del mapa de decisión + Pitfall 6 + T-03-06"
affects:
  - scoring/scorer.py (Plan 04 — consume evaluar_ubicacion como primer paso del scorer)
  - tests/scoring/test_scorer.py (Plan 04 — tests de integración usan los mismos scores de ubicación)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NFD city normalization replicada localmente en scoring/ para evitar import de app.dedup (Pitfall 7 isolation)"
    - "Substring city match: any(norm(c) in norm(loc)) para manejar 'Barcelona, España' vs 'Barcelona'"
    - "TDD: test → implementation en dos commits atómicos separados (test RED → feat GREEN)"

key-files:
  created:
    - app/scoring/location.py
    - tests/scoring/test_location.py
  modified: []

key-decisions:
  - "NFD replicado localmente en scoring/location.py (no importar app.dedup) — aísla los tests de scoring de torch/BGE-M3 (Pitfall 7)"
  - "Substring match (city in location) en lugar de igualdad exacta — maneja sufijos de país como 'Barcelona, España' (Pitfall 6)"
  - "unicodedata.category(c) != 'Mn' — convención del proyecto (idéntica a normalize_field en app/dedup/normalize.py)"

patterns-established:
  - "location.py isolation pattern: nunca importar app.dedup desde app.scoring para mantener los tests de scoring torch-free"
  - "TDD Red-Green commit pairing: test commit (failing) → feat commit (passing) para cada módulo determinista"

requirements-completed: [SCORE-03]

# Metrics
duration: 12min
completed: 2026-05-22
---

# Phase 3 Plan 03: Heurística de Scoring — Location Evaluator Summary

**Evaluador determinista de ubicación/remoto: `evaluar_ubicacion(job, profile)` con NFD substring city matching, 8 ramas booleanas puras, y deal-breaker de ubicación para presencial/híbrido fuera de ciudades aceptadas**

## Performance

- **Duration:** 12 min
- **Started:** 2026-05-22T~04:10:00Z
- **Completed:** 2026-05-22T~04:22:00Z
- **Tasks:** 1 (TDD: RED + GREEN commits)
- **Files created:** 2

## Accomplishments

- `evaluar_ubicacion(job, profile)` implementa las 8 ramas del mapa de decisión (RESEARCH Pattern 4) con lógica booleana pura, cero LLM
- NFD substring city matching: "Barcelona, España" matchea "Barcelona" porque `_ciudad_aceptada` usa `any(norm(c) in norm(loc))` (Pitfall 6)
- `location=None` manejado de forma segura — `_ciudad_aceptada` retorna `False` sin crash (T-03-06)
- 13 tests verdes cubriendo todas las ramas + robustez; suite completa 115 passed, 0 failures

## Task Commits

1. **Task 1 RED — failing tests:** `8177c4b` (test)
2. **Task 1 GREEN — implementation:** `b0af933` (feat)

**Plan metadata:** (docs commit a continuación)

_Nota: TDD — dos commits por tarea (test RED → feat GREEN)_

## Files Created/Modified

- `app/scoring/location.py` — `evaluar_ubicacion(job, profile) -> tuple[int, str|None]` + helpers `_normalize_city` y `_ciudad_aceptada` (NFD, stdlib only)
- `tests/scoring/test_location.py` — 13 tests: una función por rama + Pitfall 6 + T-03-06

## Decisions Made

1. **NFD replicado localmente:** El algoritmo de normalización de ciudad se replica en `scoring/location.py` (no se importa `app.dedup.normalize`). Motivo: evitar que los tests de scoring arrastren la inicialización de `BgeM3Embedder` (torch / sentence-transformers), lo que haría los tests lentos e inestables si el modelo no está descargado (Pitfall 7 de RESEARCH.md). El algoritmo es trivial (3 líneas de stdlib) y la convención NFD es idéntica.

2. **Substring match sobre igualdad exacta:** `_ciudad_aceptada` usa `any(norm(c) in norm(loc) for c in ciudades)`. Las APIs de empleo devuelven la ubicación con país o región ("Barcelona, España", "Madrid, Spain"); igualdad exacta contra "Barcelona" fallaría silenciosamente (Pitfall 6).

3. **Convención `category(c) != "Mn"`:** Idéntica a `app/dedup/normalize.py` — coherencia del proyecto (no `not unicodedata.combining(c)` que es equivalente pero menos explícito).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `evaluar_ubicacion` lista para ser consumida por `scoring/scorer.py` (Plan 04, paso 1 del orquestador de 6 pasos)
- La tupla `(encaje_ubicacion, deal_breaker_loc)` encaja directamente en el override de deal-breaker del scorer (RESEARCH Pattern 6)
- `tests/scoring/test_location.py` usa los mismos fixtures de conftest que usará `test_scorer.py` — no hay conflictos

## Self-Check: PASSED

- FOUND: app/scoring/location.py
- FOUND: tests/scoring/test_location.py
- FOUND: 03-03-SUMMARY.md
- Commits verified: 8177c4b (test RED), b0af933 (feat GREEN)
- 13 tests passed; full suite 115 passed, 0 failures, 0 regressions

---
*Phase: 03-heuristica-de-scoring*
*Completed: 2026-05-22*
