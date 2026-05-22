---
phase: 02-normalizacion-y-deduplicacion
plan: 01
subsystem: dedup-setup
tags: [sentence-transformers, fixtures, test-infrastructure, wave-0]
dependency_graph:
  requires: [01-04]
  provides: [sentence-transformers-dep, tests/dedup-package, dedup-fixtures-in-conftest]
  affects: [02-02, 02-03, 02-04]
tech_stack:
  added: [sentence-transformers==5.5.1, torch==2.12.0, numpy==2.4.6, transformers==5.9.0]
  patterns: [deferred-import-for-heavy-dep, injectable-fake-embedder, batch-resilient-fixtures]
key_files:
  created:
    - tests/dedup/__init__.py
  modified:
    - pyproject.toml
    - uv.lock
    - tests/conftest.py
decisions:
  - "sentence-transformers added as runtime dep (not dev-only) — used by BgeM3Embedder in production"
  - "FakeEmbedder import deferred inside fixture body (not module-level) — app/dedup/embedder.py not yet created in Wave 0"
  - "numpy imported at module-level in conftest.py — safe, it is a direct dep of sentence-transformers"
  - "FakeEmbedder interface follows plan spec: __init__(vectors, default_vector, dim) per plan 02-01 interfaces section"
metrics:
  duration_minutes: 5
  completed_date: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 4
---

# Phase 02 Plan 01: Wave 0 Setup — Dependency + Test Infrastructure Summary

sentence-transformers 5.5.1 declared as runtime dep and tests/dedup package created with five deterministic dedup fixtures in conftest.py (FakeEmbedder deferred import, Arbeitnow/generic/malformed payloads).

## What Was Built

### Task 1: sentence-transformers + tests/dedup package (commit: 649dc79)

- Added `sentence-transformers>=5.5.1` to `pyproject.toml` dependencies (runtime, not dev-only)
- `uv add` resolved and installed 19 packages including torch 2.12.0, numpy 2.4.6, transformers 5.9.0
- Created `tests/dedup/__init__.py` as empty package init (analog to `tests/cv/__init__.py`)

### Task 2: Dedup fixtures in tests/conftest.py (commit: f983949)

Five new fixtures appended below existing CV fixtures (CV fixtures preserved intact):

1. **`fake_embedder_identico`** — `FakeEmbedder(default_vector=[1,0,0,0])`: always returns same unit vector → cosine 1.0 between any pair → forces semantic merge in dedup tests
2. **`fake_embedder_ortogonal`** — `FakeEmbedder(vectors={...})`: three orthogonal vectors → cosine 0.0 between distinct jobs → verifies non-duplicate jobs are NOT merged at threshold 0.85
3. **`sample_arbeitnow_payload`** — verified Arbeitnow API shape: slug, company_name, title, description (HTML), remote (bool), url, tags, job_types, location, created_at (Unix int); no salary field
4. **`sample_generic_payload`** — generic field convention: employer, job_title, city, body, apply_url, is_remote (bool True) for generic_mapper tests
5. **`sample_malformed_payload`** — `{"company_name": 12345, "title": None}` — type mismatch triggers Pydantic ValidationError → verifies NORM-04 batch resilience

Critical invariant maintained: `from app.dedup.embedder import FakeEmbedder` is **deferred** inside each fixture body. Module-level collection does not attempt to import `app.dedup.embedder` (which doesn't exist yet in Wave 0).

## Verification Results

```
uv run pytest -q → 13 passed, 0 failed (no torch import during collection)
grep sentence-transformers pyproject.toml → 1 match
tests/dedup/__init__.py → exists
5 new fixtures defined, 2 existing CV fixtures preserved
FakeEmbedder import NOT at module level (only inside fixture bodies)
```

## Deviations from Plan

None - plan executed exactly as written.

The `FakeEmbedder` interface in the fixtures matches the plan's spec:
`__init__(self, vectors: dict[str, np.ndarray] | None = None, default_vector: np.ndarray | None = None, dim: int = 4)`. Plan 03 must implement `app/dedup/embedder.py` with this exact signature.

## Known Stubs

None. This plan creates only test infrastructure; no app logic was implemented.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The dependency addition (sentence-transformers/torch) is mitigated by the supply-chain lock via `uv.lock` with pinned hashes (T-02-02 from threat model: accepted).

## Self-Check: PASSED

- [x] `tests/dedup/__init__.py` exists
- [x] `pyproject.toml` contains `sentence-transformers>=5.5.1`
- [x] `uv.lock` updated (699 lines added in Task 1 commit)
- [x] `tests/conftest.py` has 5 new fixtures + 2 preserved CV fixtures
- [x] Commit `649dc79` exists: `chore(02-01): add sentence-transformers + create tests/dedup package`
- [x] Commit `f983949` exists: `feat(02-01): add dedup fixtures to tests/conftest.py`
- [x] `uv run pytest -q` → 13 passed, 0 failed
