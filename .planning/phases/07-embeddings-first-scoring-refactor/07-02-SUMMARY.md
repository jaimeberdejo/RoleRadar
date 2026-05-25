---
phase: "07-embeddings-first-scoring-refactor"
plan: "02"
subsystem: "scoring"
tags: ["embeddings", "cosine-similarity", "bge-m3", "puesto-match", "skills-match", "tdd"]
dependency_graph:
  requires:
    - "07-01: scorer v2 guard tests (RED) — established FakeEmbedder and test infrastructure"
    - "app/dedup/embedder.py: Embedder Protocol + FakeEmbedder (TYPE_CHECKING duck-typed)"
    - "app/scoring/ranking.py: encaje_puesto_desde_rango (feeds from rango_puesto returned here)"
    - "app/models/schemas.py: PuestoRanking schema"
  provides:
    - "app/scoring/puesto_match.py: match_puesto_por_coseno + UMBRAL_PUESTO_DEFAULT"
    - "app/scoring/skills_match.py: encaje_skills_por_coseno + CV_SKILLS_TEXT_MAX_TOKENS"
  affects:
    - "app/scoring/scorer.py: will call both helpers in Wave 2 (07-03)"
tech_stack:
  added: []
  patterns:
    - "TYPE_CHECKING guard: prevents torch/sentence-transformers import at module level (Pitfall 7)"
    - "Batch embedding: single embedder.embed([query] + corpus) call for efficiency"
    - "dot-product-as-cosine: L2-normalized vectors, dot == cosine (BGE-M3 invariant)"
    - "TDD RED-GREEN cycle: failing tests committed before implementation"
key_files:
  created:
    - "app/scoring/puesto_match.py"
    - "app/scoring/skills_match.py"
    - "tests/scoring/test_puesto_match.py"
    - "tests/scoring/test_skills_match.py"
  modified: []
decisions:
  - "TYPE_CHECKING guard for Embedder import: prevents torch loading in scorer tests (Pitfall 7 from CONTEXT.md)"
  - "Single embed() call per function: [query] + corpus in one batch — avoids N+1 embed calls"
  - "UMBRAL_PUESTO_DEFAULT=0.55: real BGE-M3 matches cluster >=0.70, noise <=0.40; 0.55 gives comfortable margin"
  - "CV_SKILLS_TEXT_MAX_TOKENS=500 chars: protects against pathological inputs; typical CV text <200 tokens"
  - "empty job_description returns 0 (not error): neutral score when description unavailable"
  - "empty cv_text raises ValueError (not silent 0): per plan requirement — never silent failure"
metrics:
  duration: "~12 minutes"
  completed: "2026-05-25"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 0
---

# Phase 07 Plan 02: BGE-M3 Cosine Helpers (puesto_match + skills_match) Summary

BGE-M3 cosine matching helpers with TYPE_CHECKING guard and TDD: `match_puesto_por_coseno` resolves job title→ranking entry (threshold 0.55), `encaje_skills_por_coseno` maps CV↔description cosine to 0-100 score.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 RED | puesto_match RED tests | 6460d34 | tests/scoring/test_puesto_match.py |
| 1 GREEN | puesto_match implementation | 4ed4414 | app/scoring/puesto_match.py, tests/scoring/test_puesto_match.py |
| 2 RED | skills_match RED tests | 544a43e | tests/scoring/test_skills_match.py |
| 2 GREEN | skills_match implementation | 228af60 | app/scoring/skills_match.py, tests/scoring/test_skills_match.py |

## Implementation Details

### app/scoring/puesto_match.py

Resolves which ranking entry a job title matches via cosine similarity.

Key design points:
- Builds corpus texts as `f"{entry.titulo} {' '.join(entry.sinonimos)}"` per entry — richer match surface
- Single `embedder.embed([title] + corpus_texts)` call (batch efficiency)
- `cosines = corpus_vecs @ title_vec` — dot product == cosine for L2-normalized vectors
- `UMBRAL_PUESTO_DEFAULT = 0.55`: documented threshold (real matches ~0.75+, noise <0.40)
- Returns `("fuera de ranking", None)` for empty ranking or below-threshold result
- 157 lines, 9 tests passing

### app/scoring/skills_match.py

Maps CV text ↔ job description cosine similarity to a 0-100 score.

Key design points:
- Takes plain strings (scorer.py builds cv_text from CVProfile before calling)
- Truncates cv_text at `CV_SKILLS_TEXT_MAX_TOKENS = 500` chars before embedding
- `score = int(round(max(0.0, min(1.0, cosine)) * 100))` — linear map with clamp
- empty cv_text → ValueError (clear error as required)
- empty job_description → 0 neutral (WARNING logged, not error)
- 159 lines, 13 tests passing

## Test Results

- 185 tests passing (full suite minus 07-01 guard tests, which are correctly failing RED)
- 0 regressions on existing 45 scoring tests
- 22 new tests added (9 for puesto_match, 13 for skills_match)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed below-threshold test vectors in test_puesto_match.py**
- **Found during:** Task 1 GREEN run
- **Issue:** The original test used `FakeEmbedder(default_vector=[0,1,0,0])` for the below-threshold test. Since FakeEmbedder uses `default_vector` for ALL unknown texts (including the query), both query and corpus got the same default vector → cosine=1.0 → test incorrectly expected below-threshold behavior.
- **Fix:** Added explicit per-text vector mappings in the test: query `[1,0,0,0]`, corpus entries `[0,1,0,0]` and `[0,0,1,0]` (orthogonal → cosine=0 < 0.55 threshold).
- **Files modified:** tests/scoring/test_puesto_match.py
- **Commit:** 4ed4414

## Known Stubs

None — both functions are fully implemented and tested.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.
Both functions accept plain strings and a duck-typed embedder; no external I/O.
Threat model T-07-03, T-07-04, T-07-05 (from plan) — all accepted or mitigated per spec:
- cv_text truncated at 500 chars (T-07-05 mitigated)
- Job description passed as data, not executed (T-07-03 accepted)

## Self-Check: PASSED

- app/scoring/puesto_match.py: FOUND
- app/scoring/skills_match.py: FOUND
- Commit 6460d34 (RED test puesto_match): FOUND
- Commit 4ed4414 (GREEN puesto_match): FOUND
- Commit 544a43e (RED test skills_match): FOUND
- Commit 228af60 (GREEN skills_match): FOUND
- 185 tests passing, 0 regressions
