---
phase: 02-normalizacion-y-deduplicacion
plan: "04"
subsystem: dedup-facade
tags: [deduplication, facade, integration, tdd, FakeEmbedder, anti-torch, QA-03]
dependency_graph:
  requires: [02-02, 02-03]
  provides: [deduplicate-facade, QA-03-e2e-test]
  affects: [03-scoring, 04-endpoints]
tech_stack:
  added: []
  patterns:
    - deferred-imports-anti-torch (imports inside function body to keep sys.modules clean)
    - embedder-injection (embedder= param seam, FakeEmbedder in tests, BgeM3Embedder lazy in prod)
    - two-level-dedup (exact_group → merge_group → semantic_cluster → merge_group)
key_files:
  created:
    - tests/dedup/test_dedup.py
  modified:
    - app/dedup/__init__.py
decisions:
  - "Deferred imports inside deduplicate() body — from app.dedup.exact/semantic/merger/embedder imported inside function, not at module top, preserving anti-torch invariant (T-02-11)"
  - "embedder=None lazily instantiates BgeM3Embedder only in production path; FakeEmbedder injected via parameter in all tests (T-02-10)"
  - "test_dedup.py uses local fixture FakeEmbedders (embedder_identico, embedder_ortogonal) rather than global conftest ones, for precise control over embed text keys"
  - "Zero mentions of BgeM3Embedder in test file (including comments/docstrings) to satisfy grep gate"
metrics:
  duration_minutes: 3
  completed_date: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 2
---

# Phase 02 Plan 04: deduplicate() Facade + QA-03 End-to-End Test Summary

**One-liner:** Public deduplicate() facade wiring exact_group → merge_group → semantic_cluster → merge_group with deferred imports for anti-torch invariant, plus 8 end-to-end tests covering exact dup, semantic dup, no-fusion, description-kept, urls_alternativas, and empty list — all with injected FakeEmbedder.

## What Was Built

### Task 1: deduplicate() facade in app/dedup/__init__.py (commit: 92cebb9)

`app/dedup/__init__.py` extended (normalize_jobs preserved) with:
- `deduplicate(jobs, embedder=None, umbral=0.85, desc_words=50) -> list[Job]`
- Deferred imports inside function body (anti-torch, T-02-11):
  - `from app.dedup.exact import exact_group`
  - `from app.dedup.semantic import semantic_cluster`
  - `from app.dedup.merger import merge_group`
  - `from app.dedup.embedder import BgeM3Embedder`
- Level 1: `exact_group(jobs)` → `[merge_group(g) for g in groups]`
- `if embedder is None: embedder = BgeM3Embedder()` — lazy, only in real use
- Level 2: `semantic_cluster(representatives, embedder, umbral, desc_words)` → `[merge_group([representatives[i] for i in cluster]) for cluster in clusters]`
- `__all__ = ["normalize_jobs", "deduplicate"]`
- Structured logging at both levels with job/group/cluster counts
- Anti-torch invariant verified: `import app.dedup` does not pull torch into `sys.modules`

### Task 2: tests/dedup/test_dedup.py — QA-03 end-to-end (commit: f6c8b77)

8 tests in `tests/dedup/test_dedup.py` (281 lines):
1. `test_deduplicate_empty_returns_empty` — empty list → empty list
2. `test_deduplicate_qa03_exact_dup_plus_unique` — **QA-03**: 3 jobs (2 exact dupes + 1 unique) → 2 output
3. `test_deduplicate_exact_keeps_longest_description` — level-1 merge keeps longest description
4. `test_deduplicate_exact_accumulates_urls_alternativas` — level-1 merge accumulates urls_alternativas (DEDUP-03 e2e)
5. `test_deduplicate_semantic_dup_collapses_with_identical_embedder` — embedder_identico forces semantic merge of hash-distinct jobs
6. `test_deduplicate_semantic_dup_accumulates_urls_alternativas` — semantic merge also accumulates urls_alternativas
7. `test_deduplicate_no_fusion_with_orthogonal_embedder` — orthogonal embedder keeps 3 jobs distinct (umbral=0.85)
8. `test_only_fake_embedder_in_tests` — documents T-02-10 invariant (FakeEmbedder always injected)

All tests use `embedder=` parameter injection directly — no `patch()`. Zero `BgeM3Embedder` mentions in test file (satisfies grep gate).

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| 92cebb9 | feat | deduplicate() facade with deferred imports + lazy BgeM3Embedder |
| f6c8b77 | feat | 8 end-to-end tests with FakeEmbedder injection (QA-03) |

## Verification Results

```
grep -c "def deduplicate" app/dedup/__init__.py      → 1 (PASS)
grep -c "def normalize_jobs" app/dedup/__init__.py    → 1 (PASS, preserved from Plan 02)
grep -c "from app.dedup.semantic...\|from app.dedup.exact...\|from app.dedup.merger..." app/dedup/__init__.py → 3 (PASS)
grep -c "if embedder is None" app/dedup/__init__.py   → 1 (PASS)
uv run python -c "from app.dedup import normalize_jobs, deduplicate"  → ok (PASS)
uv run python -c "import sys; import app.dedup; assert 'torch' not in sys.modules"  → PASS
grep -c "deduplicate(" tests/dedup/test_dedup.py      → 11 (≥3 PASS)
grep -c "embedder=" tests/dedup/test_dedup.py         → 11 (≥3 PASS)
grep -c "BgeM3Embedder" tests/dedup/test_dedup.py     → 0 (PASS)
grep -c "urls_alternativas" tests/dedup/test_dedup.py → 10 (≥1 PASS)
uv run pytest tests/dedup/test_dedup.py               → 8 passed
uv run pytest tests/dedup                             → 73 passed
uv run pytest                                         → 86 passed
```

## Deviations from Plan

None — plan executed exactly as written.

Minor note on TDD sequencing: Plan 04 has Task 1 (implement facade) before Task 2 (TDD tests). The `tdd="true"` on Task 2 means tests were written as the first action of Task 2, which immediately passed against Task 1's already-committed implementation. The RED phase of TDD was structural rather than temporal — the test file did not exist before Task 2's action.

## Known Stubs

None — deduplicate() is fully wired. No hardcoded empty values, no placeholder text.

## Threat Flags

None — no new network endpoints, auth paths, file access, or schema changes.

Threat mitigations from the plan's threat model implemented:

| Threat ID | Mitigation Applied |
|-----------|-------------------|
| T-02-10 | All tests inject FakeEmbedder via embedder= param; grep gate confirmed: 0 BgeM3Embedder mentions in test file |
| T-02-11 | Deferred imports (exact/semantic/merger/embedder) inside deduplicate() body; verified: import app.dedup does not pull torch into sys.modules |

## Self-Check: PASSED

- [x] `app/dedup/__init__.py` exports both `normalize_jobs` and `deduplicate`
- [x] `tests/dedup/test_dedup.py` exists (281 lines, 8 tests)
- [x] Commit `92cebb9` exists: `feat(02-04): add deduplicate() facade to app/dedup/__init__.py`
- [x] Commit `f6c8b77` exists: `feat(02-04): add end-to-end deduplicate() tests with FakeEmbedder (QA-03)`
- [x] `uv run pytest tests/dedup/test_dedup.py` → 8 passed
- [x] `uv run pytest tests/dedup` → 73 passed
- [x] `uv run pytest` (full suite) → 86 passed
- [x] Anti-torch invariant: `import app.dedup` does not introduce torch
- [x] Zero BgeM3Embedder mentions in test file
- [x] All 6 acceptance criteria for Task 1 pass
- [x] All 6 acceptance criteria for Task 2 pass
