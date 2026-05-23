---
phase: 04-api-y-persistencia
plan: "04"
subsystem: api
tags: [fastapi, orchestration, ya_visto, history, tdd]
dependency_graph:
  requires: ["04-02", "04-03"]
  provides: ["POST /jobs/process", "GET /jobs/history", "ScoredJobConVisto", "ProcessResponse"]
  affects: ["app/api/routes/jobs.py", "tests/api/test_process.py"]
tech_stack:
  added: []
  patterns: ["TDD RED/GREEN", "batch-resilient orchestration", "was_seen before upsert", "FakeStorage functional in-memory"]
key_files:
  created:
    - tests/api/test_process.py
  modified:
    - app/api/routes/jobs.py
    - .planning/phases/04-api-y-persistencia/04-VALIDATION.md
decisions:
  - "ya_visto computed via storage.was_seen(job.id) BEFORE upsert — if after, every offer in own run would return ya_visto=True"
  - "ScoredJobConVisto wraps ScoredJob+ya_visto without mutating core ScoredJob schema"
  - "limit clamped to [1,200] silently (no 400) to avoid breaking n8n on out-of-range params"
  - "FakeStorage is functional (populates _seen+_jobs) so ya_visto and history tests work with in-memory storage"
metrics:
  duration_seconds: 439
  completed_date: "2026-05-23"
  tasks_completed: 4
  files_changed: 3
---

# Phase 04 Plan 04: POST /jobs/process + GET /jobs/history + ya_visto Summary

**One-liner:** Full n8n orchestration endpoint — normalize+dedup+score+persist with ya_visto flag computed before upsert, ordered by score_total DESC, plus paginable history endpoint; all e2e tested via FakeStorage with zero network.

## What Was Built

### POST /jobs/process (API-04, API-07, STORE-03)
The main endpoint n8n calls daily. Accepts `{sources: [{source, offers}]}`, orchestrates:
1. **normalize_jobs** per source (batch-resilient, errors collected)
2. **deduplicate** with injected embedder + `user_profile.dedup_umbral`
3. **score_job** per unique job (batch-resilient, scoring errors go to `errors`)
4. **was_seen** called BEFORE upsert (critical: if after, every offer in its own run would be `ya_visto=True`)
5. **upsert_scored_jobs** to persist
6. Sort by `score_total DESC`

Returns `ProcessResponse{results: [ScoredJobConVisto], errors: [dict]}`.

`ScoredJobConVisto` wraps `job: Job + score: JobScore + ya_visto: bool` — does NOT mutate the core `ScoredJob` schema.

### GET /jobs/history (API-06)
Delegates to `storage.get_history(limit, offset)`. Limit clamped silently to `[1, 200]`, offset to `>= 0` — no 400 to avoid breaking n8n clients.

### New models in jobs.py
- `SourceBlock(source, offers)` — one source + its raw offers
- `ProcessRequest(sources: list[SourceBlock])` — request body
- `ScoredJobConVisto(job, score, ya_visto)` — response item with ya_visto
- `ProcessResponse(results, errors)` — full response

## Tests (tests/api/test_process.py)

7 e2e tests, all green, zero network, zero torch:

| Test | Requirement | Result |
|------|-------------|--------|
| `test_process_ordena_por_score_total` | API-04 | PASS |
| `test_process_ya_visto_primer_run_false` | STORE-03 | PASS |
| `test_process_ya_visto_segundo_run` | STORE-03 (core) | PASS |
| `test_process_persiste_en_history` | API-06 persistence | PASS |
| `test_process_oferta_malformada_va_a_errors` | API-07/NORM-04 | PASS |
| `test_process_sin_cv_profile_404` | API-04 prereq | PASS |
| `test_history_paginacion` | API-06 paging | PASS |

FakeStorage (conftest.py) is functional: `upsert_scored_jobs` populates `_seen` + `_jobs`; `was_seen` reads `_seen`; `get_history` returns `_jobs[offset:offset+limit]`. This enables `ya_visto` second-run and history tests with zero disk I/O.

## Full Suite

```
uv run pytest -q
161 passed, 5 warnings in 0.72s
```

154 tests pre-existing + 7 new. All green.

## Deviations from Plan

None — plan executed exactly as written.

The `FakeStorage` was already functional as described in `04-PLAN-CHECK-RESOLUTIONS.md` (B1+B3). No SQLiteStorage override was needed for the ya_visto tests; FakeStorage's in-memory `_seen` set was sufficient.

## Decisions Made

1. **was_seen before upsert (order critical):** `storage.was_seen(job.id)` is called before `storage.upsert_scored_jobs`. If reversed, every offer in its own run would return `ya_visto=True`, breaking STORE-03 semantics.

2. **ScoredJobConVisto vs mutating ScoredJob:** Added a new response wrapper model rather than adding `ya_visto` to the core `ScoredJob` schema. Keeps domain schemas stable and ya_visto as a purely HTTP-layer concern.

3. **limit clamp, not 400:** `GET /jobs/history` clamps `limit` to `[1, 200]` and `offset` to `>=0` silently. This avoids HTTP 400 errors breaking n8n automation flows on out-of-range parameters.

4. **TDD pattern:** Tests written first (RED commit `779da88`), then implementation (GREEN commits `195d34e`, `df42505`). 7/7 tests green.

## Threat Mitigations Applied

| Threat | Mitigation |
|--------|-----------|
| T-04-11 (DoS via malformed offers) | `normalize_jobs` batch-resilient + `try/except` per job in scoring loop → errors list, never 500 |
| T-04-13 (SQL injection via offer data) | `upsert_scored_jobs` uses parametrized placeholders (Plan 02) — `/jobs/process` never constructs SQL |

## Known Stubs

None — all data flows are wired end-to-end.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes beyond what is in the plan's threat model.

## Self-Check

- [x] `app/api/routes/jobs.py` — modified (exists)
- [x] `tests/api/test_process.py` — created (exists)
- [x] `04-VALIDATION.md` — modified (nyquist_compliant: true)
- [x] Commits 779da88, 195d34e, df42505, d0aa58b exist
- [x] `uv run pytest` → 161 passed

## Self-Check: PASSED
