---
phase: 01-parseo-de-cv
plan: 04
subsystem: cv-parsing
tags: [orchestrator, cache-first, tdd, end-to-end, instructor, anthropic]
dependency_graph:
  requires:
    - "01-01: pytest infra, conftest fixtures (sample_pdf_bytes, EXPECTED_PROFILE, mock_llm_client)"
    - "01-02: extractor.py (extract_text_from_pdf) + cache.py (pdf_hash, load/save_cached_profile)"
    - "01-03: llm_client.py (build_instructor_client, extract_cv_profile)"
  provides:
    - "app/cv/parser.py: parse_cv(pdf_bytes: bytes) -> CVProfile cache-first orchestrator"
    - "app/cv/__init__.py: public export of parse_cv (the phase interface)"
    - "tests/cv/test_parser.py: QA-01 acceptance test — 2 tests green"
  affects:
    - "Phase 02+ (FastAPI endpoints): POST /cv/parse will call parse_cv directly"
    - "Any consumer in n8n flow that needs CV parsing: import from app.cv"
tech_stack:
  added: []
  patterns:
    - "Cache-first orchestration: hash → load_cached_profile → (miss) extract_text_from_pdf → build_instructor_client → extract_cv_profile → save_cached_profile"
    - "Mock seam at import site: patch('app.cv.parser.build_instructor_client') — NOT the definition in llm_client.py"
    - "CV_CACHE_DIR=tmp_path isolation in every test (T-01-11 mitigation)"
    - "TDD: parser test file validates orchestrator written in Task 1"
key_files:
  created:
    - app/cv/parser.py
    - tests/cv/test_parser.py
  modified:
    - app/cv/__init__.py
decisions:
  - "Cache check before any extraction: pdf_hash + load_cached_profile called BEFORE extract_text_from_pdf — malformed PDFs that are repeated are cheap (hash only, no text extraction, no LLM)"
  - "parse_cv propagates ValueError from extractor unchanged: calling code (FastAPI endpoint) decides HTTP status; parser is not an HTTP layer"
  - "Mock target is app.cv.parser.build_instructor_client (import site), not app.cv.llm_client.build_instructor_client — patching at the definition site would not intercept the already-imported name in parser.py"
metrics:
  duration_minutes: 1
  completed_date: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 1
---

# Phase 01 Plan 04: parser.py orchestrator + QA-01 acceptance test Summary

**One-liner:** Cache-first `parse_cv(pdf_bytes) -> CVProfile` orchestrator wiring extractor + LLM + cache in guaranteed order, exported from `app.cv`, with QA-01 acceptance test proving typed return and cache short-circuit (9 tests green across Phase 1).

## What Was Built

### Task 1: app/cv/parser.py + updated app/cv/__init__.py

Implemented the public `parse_cv(pdf_bytes: bytes) -> CVProfile` orchestrator with strict cache-first ordering:

1. `pdf_hash(pdf_bytes)` — compute sha256 of PDF content
2. `load_cached_profile(h)` — check cache BEFORE any extraction or LLM call (CV-03)
3. Cache hit: return immediately, no LLM call
4. Cache miss: `extract_text_from_pdf(pdf_bytes)` → `build_instructor_client()` → `extract_cv_profile(raw_text, client)` → `save_cached_profile(h, profile)` → return

The ordering gate was verified with `awk` confirming `load_cached_profile` appears on line 40 and `extract_text_from_pdf` appears on line 43.

Updated `app/cv/__init__.py` to export `parse_cv` and set `__all__ = ["parse_cv"]`, making `from app.cv import parse_cv` the canonical import path for all consumers.

Acceptance criteria verified:
- `grep -q 'def parse_cv' app/cv/parser.py` — passes
- `grep -q 'load_cached_profile' app/cv/parser.py` — passes
- `grep -q 'extract_cv_profile' app/cv/parser.py` — passes
- `grep -q 'build_instructor_client' app/cv/parser.py` — passes
- `awk` ordering gate — passes (cache before extraction)
- `grep -q 'from app.cv.parser import parse_cv' app/cv/__init__.py` — passes
- `uv run python -c "from app.cv import parse_cv; print(parse_cv.__name__)"` — exits 0

### Task 2: tests/cv/test_parser.py (QA-01 acceptance tests)

Two tests covering the two contract requirements:

1. `test_parse_cv_returns_cv_profile` (CV-01/CV-02): Calls `parse_cv(sample_pdf_bytes)` with the LLM mocked at `app.cv.parser.build_instructor_client`. Asserts `isinstance(result, CVProfile)` and `result.skills_tecnicas == ["Python", "LLMs"]`.

2. `test_cache_avoids_second_llm_call` (CV-03): Calls `parse_cv` twice with the same bytes inside one `patch` block. Asserts `mock_llm_client.messages.create.call_count == 1` — the LLM is invoked only on the first call; the second call returns from the file cache written to `tmp_path`.

Both tests isolate the cache with `monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))` and set `ANTHROPIC_API_KEY="test-key"` to prevent environment errors.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — `parse_cv` is fully wired with no hardcoded values or placeholder data. The full pipeline (hash → cache check → extract → LLM → cache write) is exercised in the acceptance test.

## Threat Flags

No new security-relevant surface beyond what the plan's threat model covers:

- T-01-09 (DoS — malformed PDF): Mitigated — extractor raises `ValueError` on text-less PDFs; cache check happens BEFORE extraction so repeated malformed input is cheap (hash only).
- T-01-10 (PII on disk): Mitigated — `CV_CACHE_DIR` defaults to `data/.cache` (gitignored); tests always redirect to `tmp_path`.
- T-01-11 (test cache contamination): Mitigated — every parser test sets `CV_CACHE_DIR=tmp_path/.cache`; no test writes to the real cache directory.

## Self-Check: PASSED

Files verified to exist:
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/app/cv/parser.py: FOUND
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/app/cv/__init__.py: FOUND (export present)
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/tests/cv/test_parser.py: FOUND

Commits verified:
- cab8bd3: feat(01-04): implement parse_cv cache-first orchestrator + public export
- f00e974: test(01-04): QA-01 end-to-end parser test — mocked LLM + tmp cache

Full phase suite: `uv run pytest tests/cv -q` — 9 passed

## TDD Gate Compliance

Task 2 is marked `tdd="true"`. In this plan, Task 1 builds the implementation (parser.py) and Task 2 builds the acceptance tests that validate it. The tests ran green immediately — consistent with Green phase TDD (implementation existed before test file). The mock_llm_client fixture and sample_pdf_bytes fixture were established in Plan 01 (Wave 0 RED gate for the phase). No TDD gate compliance issues.
