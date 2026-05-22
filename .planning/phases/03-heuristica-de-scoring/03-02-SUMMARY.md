---
phase: 03-heuristica-de-scoring
plan: 02
subsystem: scoring
tags: [pyyaml, pydantic, scoring, ranking, config, loader, decay]

requires:
  - phase: 03-heuristica-de-scoring/01
    provides: "LLMJobAssessment schema, UserProfile + PesosScoring schemas with check_sum"

provides:
  - "app/config/loader.py: load_user_profile(path) -> UserProfile via yaml.safe_load + model_validate"
  - "app/config/__init__.py: facade publico del modulo de config"
  - "app/scoring/ranking.py: encaje_puesto_desde_rango(rango, *, paso, suelo, maximo) -> int"
  - "tests/scoring/test_ranking.py: 11 tests del decay (valores exactos, monotonia, suelo, parametros)"
  - "tests/scoring/test_loader.py: 4 tests del loader (perfil real, ruta invalida, pesos invalidos, minimo)"

affects:
  - 03-heuristica-de-scoring/03
  - 03-heuristica-de-scoring/04
  - 03-heuristica-de-scoring/05

tech-stack:
  added: []
  patterns:
    - "Decay lineal: max(suelo, maximo - (rango-1)*paso) con defaults paso=15, suelo=20, maximo=100"
    - "Config loader: yaml.safe_load (nunca yaml.load) + UserProfile.model_validate con re-raise claro"
    - "Facade __init__.py de modulo de config (analogo a app/cv/__init__.py)"

key-files:
  created:
    - app/config/loader.py
    - app/config/__init__.py
    - app/scoring/ranking.py
    - tests/scoring/test_ranking.py
    - tests/scoring/test_loader.py
  modified: []

key-decisions:
  - "Parametros de decay (paso, suelo, maximo) como defaults en codigo con override por keyword — no en profile.yaml (decisión RESOLVED del RESEARCH: simplifica schema de UserProfile; ajuste diferido a v2)"
  - "yaml.safe_load exclusivamente (nunca yaml.load) para mitigar T-03-04 (ejecucion de codigo arbitrario via YAML)"
  - "FileNotFoundError y ValidationError envueltos con mensajes claros que incluyen ruta/campo (mitigacion T-03-05)"
  - "Validacion de pesos suma=1.0 delegada a PesosScoring.check_sum — no duplicada en loader"

patterns-established:
  - "Funciones puras de scoring (ranking.py): stdlib only, docstring en espanol, from __future__ import annotations, logger modulo"
  - "Loader de configuracion: try/except selectivo (FileNotFoundError, ValidationError) — no except Exception generico"

requirements-completed: [SCORE-02, SCORE-06]

duration: 15min
completed: 2026-05-22
---

# Phase 03 Plan 02: Config Loader + Ranking Decay Summary

**decay lineal encaje_puesto_desde_rango (100/85/70/55/suelo=20) y loader YAML -> UserProfile con errores claros**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-05-22T01:46:00Z
- **Completed:** 2026-05-22T02:01:15Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Funcion de decaimiento lineal pura (`encaje_puesto_desde_rango`) que convierte rango LLM → score determinista; rango=None → suelo=20 (fuera de ranking no descarta sola, SCORE-02)
- Loader de configuracion (`load_user_profile`) que usa yaml.safe_load + model_validate con errores claros para ruta inexistente y schema invalido incluidos pesos que no suman 1.0 (SCORE-06)
- 15 tests en verde: 11 para decay (valores exactos, monotonia, suelo, parametros), 4 para loader (perfil real, ruta invalida, pesos invalidos, minimo)
- Suite completa 102 tests verde (87 previos + 15 nuevos, cero regresiones)

## Task Commits

Cada tarea fue committeada atomicamente:

1. **Task 1 RED: test_ranking.py** - `4afa25e` (test)
2. **Task 1 GREEN: app/scoring/ranking.py** - `bc4c999` (feat)
3. **Task 2: app/config/loader.py + __init__.py + test_loader.py** - `4d3c5e7` (feat)

**Plan metadata:** pendiente (docs: complete plan)

## Files Created/Modified

- `app/scoring/ranking.py` - Funcion encaje_puesto_desde_rango: decay lineal max(suelo, maximo-(rango-1)*paso)
- `app/config/loader.py` - load_user_profile: yaml.safe_load + model_validate con manejo de errores claro
- `app/config/__init__.py` - Facade publico del modulo de config (re-exporta load_user_profile)
- `tests/scoring/test_ranking.py` - 11 tests: valores exactos 1/2/3/4/None, monotonia, suelo respetado, params configurables
- `tests/scoring/test_loader.py` - 4 tests: perfil real, ruta inexistente, pesos invalidos, minimo valido

## Decisions Made

- Parametros de decay en codigo con defaults (no en profile.yaml): simplifica UserProfile schema; ajuste diferido a v2 segun RESEARCH
- yaml.safe_load exclusivamente para mitigar ejecucion de codigo arbitrario (T-03-04)
- Re-raise con mensajes claros (ruta en FileNotFoundError, detalle Pydantic en ValueError) para que el arranque del servicio sea diagnosticable (T-03-05)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `encaje_puesto_desde_rango` lista para ser consumida por `app/scoring/scorer.py` (Plan 04/05)
- `load_user_profile` lista para ser consumida por el endpoint GET /profile (Fase 5) y por scorer
- Tests de ranking y loader en verde como base para tests de scorer (Plan 04/05)

## Self-Check: PASSED

- app/scoring/ranking.py: FOUND
- app/config/loader.py: FOUND
- app/config/__init__.py: FOUND
- tests/scoring/test_ranking.py: FOUND
- tests/scoring/test_loader.py: FOUND
- 03-02-SUMMARY.md: FOUND
- Commit 4afa25e (test RED ranking): FOUND
- Commit bc4c999 (feat GREEN ranking): FOUND
- Commit 4d3c5e7 (feat loader+tests): FOUND
- 102 tests pass, 0 regressions

---
*Phase: 03-heuristica-de-scoring*
*Completed: 2026-05-22*
