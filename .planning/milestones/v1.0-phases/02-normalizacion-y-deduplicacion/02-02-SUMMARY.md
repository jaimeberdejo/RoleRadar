---
phase: 02-normalizacion-y-deduplicacion
plan: 02
subsystem: dedup-normalize
tags: [normalization, mappers, NFD, sha256, stable-id, batch-resilient, arbeitnow, registry]
dependency_graph:
  requires: [02-01]
  provides: [app/dedup/normalize.py, app/dedup/mappers.py, app/dedup/__init__.py, tests/dedup/test_normalize.py]
  affects: [02-03, 02-04]
tech_stack:
  added: []
  patterns:
    - NFD-accent-strip-casefold (normalize_field via unicodedata.normalize("NFD") + Mn filter)
    - sha256-stable-id (stable_job_id returns full 64-hex, same as cv/cache.py pattern)
    - source-mapper-registry (MAPPER_REGISTRY dict + AJUSTABLE comments per NORM-03)
    - batch-resilient-facade (per-item try/except in normalize_jobs, structured logging)
    - HTML-strip-in-mapper (re.sub tag strip in arbeitnow_mapper before Job.description)
key_files:
  created:
    - app/dedup/normalize.py
    - app/dedup/mappers.py
    - app/dedup/__init__.py
    - tests/dedup/test_normalize.py
  modified: []
decisions:
  - "Used NFD not NFC for accent normalization — NFC recomposes precomposed chars (é, ñ) and does NOT strip them; NFD decomposes to base+Mn so filter works (Pitfall 2)"
  - "stable_job_id returns full 64-char sha256 hex (no truncation) — consistent with Phase 1 _HEX_RE = r'^[0-9a-f]{64}$' pattern from cv/cache.py"
  - "arbeitnow remote=False maps to RemoteJob.unknown, not onsite — no evidence it is onsite (could be hybrid); RemoteJob.remote only when remote=True"
  - "mappers.py created together with normalize.py in Task 1 commit — test file imports all three modules at collection time; split across commits would break collection"
  - "All AJUSTABLE banners in mappers.py follow plan spec: comments on each mapper + stubs for jsearch/flybyapis"
metrics:
  duration_minutes: 3
  completed_date: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 4
---

# Phase 02 Plan 02: Normalization — normalize.py + mappers.py + batch facade + tests Summary

NFD-based accent strip + stable sha256 id (normalize.py), source-mapper registry with arbeitnow and generic mappers marked AJUSTABLE (mappers.py), and batch-resilient normalize_jobs facade in __init__.py. 34 tests pass covering NORM-01..04 and QA-02.

## What Was Built

### Task 1: normalize.py — normalize_field + stable_job_id (commit: 3e6fddd)

- `app/dedup/normalize.py` (stdlib only — no external deps):
  - `normalize_field(s: str) -> str`: NFD decomposition + Mn category filter + casefold + collapse spaces. Uses `unicodedata.normalize("NFD", s)` then `"".join(c for c in s if unicodedata.category(c) != "Mn")`. Handles all European/Spanish accented chars correctly.
  - `stable_job_id(company, title, location) -> str`: SHA-256 hex (64 chars) of `normalize(company)|normalize(title)|normalize(location)` key. Deterministic across runs. Matches Phase 1 `_HEX_RE` convention.
  - Module-level `logger = logging.getLogger(__name__)`.

- `app/dedup/__init__.py`: Package init with `normalize_jobs` facade; also committed here since test file imports all three modules at collection time.
- `app/dedup/mappers.py`: Registry + mappers (see Task 2 notes below).
- `tests/dedup/test_normalize.py`: Full test suite (34 tests) covering all NORM requirements and QA-02.

### Task 2: mappers.py + normalize_jobs facade — full suite green (included in 3e6fddd)

- `app/dedup/mappers.py`:
  - `MapperFn = Callable[[dict, str], Job]` type alias.
  - `arbeitnow_mapper`: uses confirmed Arbeitnow API fields (company_name, title, description/HTML→strip, remote bool, url, location, created_at→ISO 8601). `salary=None` (free tier). Banner + per-mapper comments marked `AJUSTABLE`.
  - `generic_mapper`: best-effort field matching (company_name/company/employer, title/job_title/position, location/city/place, description/body/summary, url/apply_url/link, remote/is_remote/work_type). Handles bool and str remote inference.
  - `MAPPER_REGISTRY = {"arbeitnow": arbeitnow_mapper, "generic": generic_mapper}` with commented stubs for jsearch/flybyapis.

- `app/dedup/__init__.py`:
  - `normalize_jobs(raw_offers, source) -> tuple[list[Job], list[dict]]`
  - Looks up mapper via `MAPPER_REGISTRY.get(source) or MAPPER_REGISTRY["generic"]`
  - Per-item try/except with `# noqa: BLE001`; errors list gets `{"index": idx, "source": source, "error": str(exc)}`
  - Structured log: `logger.info("normalize_jobs: source=%s in=%d ok=%d errors=%d", ...)`
  - `__all__ = ["normalize_jobs"]`

## Verification Results

```
uv run pytest tests/dedup/test_normalize.py -q      → 34 passed
uv run pytest -q (full suite)                       → 47 passed, 0 failed
grep -c "def normalize_field\|def stable_job_id" app/dedup/normalize.py  → 2
grep -c "NFD" app/dedup/normalize.py                → 6
stable_job_id('a','b','c') length                   → 64
normalize_field('Ácmé') == normalize_field('Acme')  → True
grep -c "def arbeitnow_mapper\|def generic_mapper" app/dedup/mappers.py  → 2
grep -c "MAPPER_REGISTRY" app/dedup/mappers.py      → 2
grep -ic "AJUSTABLE" app/dedup/mappers.py           → 8
grep -c "def normalize_jobs" app/dedup/__init__.py  → 1
grep -c "noqa: BLE001\|except Exception" app/dedup/__init__.py  → 1
from app.dedup import normalize_jobs                → no error
```

## Deviations from Plan

### Auto-committed mappers.py in Task 1 (minor structural deviation)

- **Found during:** Task 1 GREEN phase
- **Issue:** The test file `tests/dedup/test_normalize.py` imports `from app.dedup.mappers import ...` and `from app.dedup import normalize_jobs` at module level. pytest collection fails if those modules don't exist — even when running only `-k "normalize or stable_id"`.
- **Fix:** Created `app/dedup/mappers.py` and the full `app/dedup/__init__.py` in the same Task 1 commit rather than deferring to Task 2.
- **Impact:** None — both tasks ended up committed together (single commit `3e6fddd`); all acceptance criteria satisfied; plan outcome unchanged.
- **Files modified:** app/dedup/mappers.py, app/dedup/__init__.py

## Known Stubs

None. All mappers produce real Job objects; `normalize_jobs` is fully functional. The commented stubs for `jsearch` and `flybyapis` in MAPPER_REGISTRY are intentional placeholders (NORM-03 requirement: mark clearly as AJUSTABLE) — they do not affect runtime behavior.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes.

Threat mitigations implemented as required by threat model:
- **T-02-03 (DoS):** per-item try/except in `normalize_jobs` — malformed offers go to `errors`, batch never crashes.
- **T-02-04 (Tampering/HTML injection):** `arbeitnow_mapper` strips HTML tags with `re.sub(r"<[^>]+>", " ", raw_desc)` before storing in `Job.description`; original HTML preserved in `Job.raw` only.

## Self-Check: PASSED

- [x] `app/dedup/normalize.py` exists and exports `normalize_field` + `stable_job_id`
- [x] `app/dedup/mappers.py` exists and exports `MAPPER_REGISTRY`, `arbeitnow_mapper`, `generic_mapper`
- [x] `app/dedup/__init__.py` exists and exports `normalize_jobs`
- [x] `tests/dedup/test_normalize.py` exists (34 tests)
- [x] Commit `3e6fddd` exists: `feat(02-02): normalize_field + stable_job_id (NFD accent strip, 64-hex sha256)`
- [x] `uv run pytest tests/dedup/test_normalize.py -q` → 34 passed
- [x] `uv run pytest -q` (full suite) → 47 passed
- [x] All 6 acceptance criteria for Task 1 pass
- [x] All 7 acceptance criteria for Task 2 pass
