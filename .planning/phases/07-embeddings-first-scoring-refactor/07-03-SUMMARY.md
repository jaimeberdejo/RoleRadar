---
phase: "07-embeddings-first-scoring-refactor"
plan: "03"
subsystem: "scoring"
tags: ["seniority", "deterministic", "regex", "rule-engine", "tdd"]
dependency_graph:
  requires: ["07-01"]
  provides: ["app/scoring/seniority.py — evaluar_seniority, SeniorityResult"]
  affects: ["app/scoring/scorer.py (phase 07-05 will inject this)"]
tech_stack:
  added: []
  patterns: ["dataclass result type", "module-level compiled regex", "ratio-to-score mapping table"]
key_files:
  created:
    - app/scoring/seniority.py
    - tests/scoring/test_seniority.py
  modified: []
decisions:
  - "None anios_candidato returns neutral 50 (not 0) — STATE blocker prevents unfair penalisation when CV was parsed without year extraction"
  - "Ratio-to-score table with 6 bands (1.5→100, 1.0→85, 0.7→65, 0.5→45, 0.3→25, <0.3→10) — never 0 (CLAUDE.md rule 3: requisitos inflados)"
  - "Regex captures lower bound of hyphen ranges ('5-7 years' → 5.0) — auto-fixed in GREEN phase"
  - "Level keywords map to approximate years (junior→1, senior→5, lead→7, etc.) as fallback when no numeric signal present"
  - "No app.dedup imports — stdlib only (re, dataclasses, logging) to prevent torch loading in scorer tests"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-25"
  tasks_completed: 1
  files_created: 2
---

# Phase 07 Plan 03: Deterministic Seniority Rule Engine Summary

Implemented `app/scoring/seniority.py` — a stdlib-only deterministic seniority evaluator that parses required years/level from job description text and compares against `CVProfile.anios_experiencia_total` using a documented ratio-to-score mapping.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED | Add failing tests | 94419e3 | tests/scoring/test_seniority.py |
| GREEN | Implement seniority rule engine | 8f06f35 | app/scoring/seniority.py |

## What Was Built

`evaluar_seniority(job_description: str, anios_candidato: float | None) -> SeniorityResult`

- `SeniorityResult` dataclass: `encaje_seniority: int` (0-100), `seniority_nota: str` (never empty), `anos_requeridos: float | None`
- Regex parses: "N+ years", "N años", "N-M years" (lower bound), "at least N years", "minimum N years"
- Level keyword fallback: junior/mid-level/senior/lead/staff/principal/director → approximate years
- `anios_candidato=None` → score=50, nota contains "desconocida" (STATE blocker)
- No requirement found → score=75 (generous assumption)
- Ratio mapping with 6 bands — minimum return is 10, never 0
- 26 tests, all passing; 189 total tests green, no regressions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed hyphen-range regex lower-bound capture**
- **Found during:** GREEN phase, test `test_years_parsed_range_takes_lower_bound`
- **Issue:** Original regex `(\d+)\s*\+?\s*(?:to\s*\d+\s*)?...` only handled "to" ranges, not hyphen ranges. For "5-7 years" it matched the second `\d+` ("7") before the word "years" instead of the intended lower bound "5".
- **Fix:** Rewrote the optional range suffix as `(?:[+]|\s*[-]\s*\d+|\s*to\s*\d+)?` so hyphen ranges are consumed as part of the match and the first captured group remains the lower bound.
- **Files modified:** app/scoring/seniority.py (_RE_ANOS pattern)
- **Commit:** 8f06f35

## Known Stubs

None. The module is fully implemented with no placeholder logic.

## Threat Flags

None beyond what was already documented in the plan's threat model (T-07-06, T-07-07). The regex fix for hyphen ranges did not introduce new ReDoS risk — the hyphen range alternative uses literal `-` and a bounded `\d+` group.

## Self-Check: PASSED

- app/scoring/seniority.py exists and exports evaluar_seniority, SeniorityResult
- tests/scoring/test_seniority.py exists with 26 tests
- Commits 94419e3 (RED) and 8f06f35 (GREEN) present in git log
- 189 tests pass, 0 failures, 0 regressions
