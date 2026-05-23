---
phase: 01-parseo-de-cv
plan: 02
subsystem: cv-parsing
tags: [pymupdf, cache, sha256, pydantic-v2, tdd]
dependency_graph:
  requires:
    - "plan 01: pytest infra, sample_pdf_bytes fixture, app namespace"
  provides:
    - "app/cv/extractor.py: extract_text_from_pdf(pdf_bytes) -> str"
    - "app/cv/cache.py: pdf_hash, load_cached_profile, save_cached_profile, CACHE_DIR"
    - "5 unit tests green (3 extractor + 2 cache)"
  affects:
    - "plan 03 (llm_client.py): extractor is the first stage the parser feeds text to"
    - "plan 04 (parser.py): imports both modules by name — signatures are now fixed"
tech_stack:
  added: []
  patterns:
    - "pymupdf.open(stream=pdf_bytes, filetype='pdf') — in-memory PDF parsing"
    - "Lazy _cache_dir() reads CV_CACHE_DIR env var per call for test isolation"
    - "Pydantic v2 model_dump_json / model_validate_json for cache serialization"
    - "TDD: RED commit (failing test) before GREEN commit (implementation)"
key_files:
  created:
    - app/cv/extractor.py
    - app/cv/cache.py
    - tests/cv/test_extractor.py
    - tests/cv/test_cache.py
  modified: []
decisions:
  - "Lazy _cache_dir() over module-level constant: CACHE_DIR constant at import time would not see monkeypatch.setenv changes during tests; reading os.getenv inside each function guarantees isolation without re-importing the module"
  - "No try/except around pymupdf.open in extractor: let the caller decide — parser.py will handle pymupdf errors at the orchestration layer"
  - "import pymupdf (not import fitz): fitz is the legacy alias; pymupdf is the correct name since v1.24+"
metrics:
  duration_minutes: 2
  completed_date: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 0
---

# Phase 01 Plan 02: extractor.py + cache.py Summary

**One-liner:** PDF bytes-to-text extraction with pymupdf and sha256-keyed CVProfile JSON cache — both LLM-free leaf modules implemented with TDD (5 tests green).

## What Was Built

Two deterministic I/O modules that form the foundation of the CV parsing pipeline:

### Task 1: app/cv/extractor.py + tests (TDD)

Implemented `extract_text_from_pdf(pdf_bytes: bytes) -> str` using `pymupdf.open(stream=pdf_bytes, filetype="pdf")`. Iterates all pages and concatenates text in reading order. Raises a clear Spanish `ValueError` ("El PDF no contiene capa de texto extraíble") on text-less PDFs (scanned image PDFs), with no OCR fallback. No `import fitz` — uses `import pymupdf` throughout.

Three tests cover:
1. Returns non-empty string for valid PDF (using `sample_pdf_bytes` fixture)
2. Extracted text contains known fixture content ("AI Engineer")
3. Raises `ValueError` matching "capa de texto" for blank-page PDF built inline

### Task 2: app/cv/cache.py + tests (TDD — CV-03)

Implemented three functions:
- `pdf_hash(pdf_bytes)`: sha256 hex digest of PDF bytes
- `load_cached_profile(content_hash)`: reads `{hash}.json` from cache dir; returns `None` on miss
- `save_cached_profile(content_hash, profile)`: writes `profile.model_dump_json(indent=2)` to `{hash}.json`

Cache dir is configurable via `CV_CACHE_DIR` env var (default `data/.cache`). Chose a lazy `_cache_dir()` helper that re-reads `os.getenv` on each call so `monkeypatch.setenv` works in tests without re-importing the module. Uses `model_dump_json` / `model_validate_json` exclusively (no `.dict()` / `json.dumps`).

Two tests cover:
1. Roundtrip save→load equals (verifies `skills_tecnicas` and `anios_experiencia_total`)
2. Miss on nonexistent hash returns `None`

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — both modules are complete and deterministic. No LLM dependency, no placeholder data.

## Threat Flags

T-01-05 (Information Disclosure — cached CVProfile PII on disk): Confirmed mitigated — `data/.cache/` gitignored (verified via `git check-ignore`). Cache files are never logged.

T-01-03 (DoS — malformed/huge PDF): Mitigated by not adding try/except around pymupdf; text-less PDFs raise ValueError immediately, no OCR loop risk.

## Self-Check: PASSED

Files verified to exist:
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/app/cv/extractor.py: FOUND
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/app/cv/cache.py: FOUND
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/tests/cv/test_extractor.py: FOUND
- /Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/tests/cv/test_cache.py: FOUND

Commits verified:
- c6d135a: test(01-02): add failing tests for PDF text extractor (RED)
- da22753: feat(01-02): implement extract_text_from_pdf using pymupdf (GREEN)
- 3acd630: test(01-02): add failing tests for CV cache (CV-03) (RED)
- 91692b8: feat(01-02): implement CV profile cache keyed by sha256 (CV-03) (GREEN)

All 5 tests pass: `uv run pytest tests/cv/test_extractor.py tests/cv/test_cache.py -q`

## TDD Gate Compliance

Both tasks followed RED/GREEN cycle:
1. `test(01-02)` commit (RED) — failing import errors confirmed before implementation
2. `feat(01-02)` commit (GREEN) — all tests pass after implementation
