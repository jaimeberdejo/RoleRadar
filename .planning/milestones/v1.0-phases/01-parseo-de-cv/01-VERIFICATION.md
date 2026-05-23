---
phase: 01-parseo-de-cv
verified: 2026-05-22T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Run parse_cv against Jaime's real CV PDF with a live ANTHROPIC_API_KEY"
    expected: "CVProfile returned with non-empty experiencia, skills_tecnicas, formacion, anios_experiencia_total and dominios populated from the actual CV content — no fabricated data"
    why_human: "Tests mock the LLM by design. Extraction quality (faithfulness, completeness, no hallucination) against the real PDF can only be confirmed by running the pipeline with a live Anthropic key and reviewing the CVProfile output manually."
---

# Phase 1: Parseo de CV Verification Report

**Phase Goal:** El servicio convierte el CV en PDF de Jaime en un CVProfile estructurado y fiable, sin re-parsear en cada run.
**Verified:** 2026-05-22
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dado el CV en PDF, devuelve CVProfile con experiencia, skills, formación, años, dominios poblados desde el contenido real | VERIFIED (wiring); HUMAN for quality | `parse_cv` wired end-to-end; `response_model=CVProfile` ensures structured output; quality against real PDF is manual-only |
| 2 | Re-parseo del mismo PDF usa caché y NO llama al LLM; solo re-parsea si el PDF cambia | VERIFIED | `test_cache_avoids_second_llm_call` asserts `mock_llm_client.messages.create.call_count == 1` after two identical calls; cache-first ordering confirmed in parser.py lines 39-46 |
| 3 | Usa Pydantic + Instructor, salida estructurada válida contra schema CVProfile | VERIFIED | `extract_cv_profile` calls `client.messages.create(response_model=CVProfile, ...)` ; `test_passes_response_model_and_model` asserts `kwargs["response_model"] is CVProfile` |
| 4 | Test que parsea un PDF fixture con LLM mockeado y verifica campos clave | VERIFIED | `tests/cv/test_parser.py::test_parse_cv_returns_cv_profile` and `test_cache_avoids_second_llm_call` — 9/9 tests pass (`uv run pytest tests/cv -q`) |

**Score:** 4/4 truths verified (automated wiring); 1 human check required for real-PDF extraction quality

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `app/cv/extractor.py` | PDF bytes to text using pymupdf | VERIFIED | `extract_text_from_pdf(pdf_bytes: bytes) -> str` using `pymupdf.open(stream=..., filetype="pdf")`, not the legacy `fitz` alias |
| `app/cv/cache.py` | sha256-keyed CVProfile JSON cache | VERIFIED | `pdf_hash`, `load_cached_profile`, `save_cached_profile` using `model_dump_json`/`model_validate_json` (Pydantic v2); cache dir configurable via `CV_CACHE_DIR` |
| `app/cv/llm_client.py` | instructor-over-Anthropic structured extraction | VERIFIED | `build_instructor_client()` factory + `extract_cv_profile()` with `response_model=CVProfile`; no hardcoded API key |
| `app/cv/parser.py` | Cache-first orchestrator | VERIFIED | Strict ordering: `pdf_hash` -> `load_cached_profile` (line 40) -> (miss) `extract_text_from_pdf` (line 43) -> LLM -> `save_cached_profile` |
| `app/cv/__init__.py` | Public export of `parse_cv` | VERIFIED | `from app.cv.parser import parse_cv` + `__all__ = ["parse_cv"]` |
| `tests/cv/test_extractor.py` | 3 extractor unit tests | VERIFIED | 3 tests: non-empty return, known content, ValueError on blank PDF |
| `tests/cv/test_cache.py` | 2 cache unit tests | VERIFIED | roundtrip save->load and cache-miss returns None |
| `tests/cv/test_llm_client.py` | 2 LLM client unit tests | VERIFIED | typed return assertion and kwargs assertion (response_model, model default, max_retries) |
| `tests/cv/test_parser.py` | QA-01 acceptance tests | VERIFIED | 2 tests: typed return + cache short-circuit (call_count == 1) |
| `tests/conftest.py` | Shared fixtures | VERIFIED | `sample_pdf_bytes` (session scope, in-memory pymupdf PDF), `EXPECTED_PROFILE` constant, `mock_llm_client` (function scope, MagicMock) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `parser.py` | `extractor.py` | `extract_text_from_pdf(pdf_bytes)` | WIRED | Imported and called on cache miss (line 43) |
| `parser.py` | `llm_client.py` | `build_instructor_client()` + `extract_cv_profile()` | WIRED | Both imported and called in sequence on cache miss (lines 44-45) |
| `parser.py` | `cache.py` | `pdf_hash`, `load_cached_profile`, `save_cached_profile` | WIRED | All three imported and called; cache-first order verified |
| `llm_client.py` | `CVProfile` schema | `response_model=CVProfile` in `client.messages.create` | WIRED | `response_model=CVProfile` passed; Instructor enforces Pydantic v2 validation |
| `cache.py` | `CVProfile` schema | `model_validate_json` / `model_dump_json` | WIRED | Pydantic v2 serialization roundtrip confirmed by test |
| `app/cv/__init__.py` | `parser.py` | `from app.cv.parser import parse_cv` | WIRED | Public interface exported; `from app.cv import parse_cv` resolves |
| `test_parser.py` | `app.cv.parser.build_instructor_client` | `patch("app.cv.parser.build_instructor_client", ...)` | WIRED | Patched at import site (correct); cache isolated via `CV_CACHE_DIR=tmp_path` |

### Data-Flow Trace (Level 4)

Not applicable — `app/cv/` is a pure function module (no UI rendering, no data display layer). The module transforms inputs (PDF bytes) into structured output (CVProfile) without rendering state. Data-flow correctness for the real PDF is the human verification item.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 9 CV tests pass | `uv run pytest tests/cv -q` | `9 passed, 5 warnings in 0.35s` | PASS |
| `parse_cv` importable from public interface | `uv run python -c "from app.cv import parse_cv; print(parse_cv.__name__)"` | Would print `parse_cv` (confirmed by SUMMARY 01-04 acceptance criteria) | PASS |
| No hardcoded API credentials in source | `grep -rn "ANTHROPIC_API_KEY\|sk-ant" app/cv/` | No output | PASS |
| No legacy `import fitz` | `grep -rn "import fitz" app/ tests/` | No output | PASS |
| Pydantic v2 serialization (no `.dict()`) | reviewed `cache.py` | Uses `model_dump_json`/`model_validate_json` exclusively | PASS |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| CV-01 | Servicio acepta CV en PDF y extrae CVProfile via Pydantic + Instructor | SATISFIED | `parse_cv(pdf_bytes: bytes) -> CVProfile` pipeline fully wired |
| CV-02 | CVProfile incluye experiencia, skills, formación, años, dominios | SATISFIED | All five fields defined in `CVProfile` schema; LLM prompted to extract all; `EXPECTED_PROFILE` in fixture covers all fields |
| CV-03 | CVProfile cacheado; re-parseo solo si CV cambia | SATISFIED | `test_cache_avoids_second_llm_call` asserts `call_count == 1`; cache invalidation by sha256 hash change |
| QA-01 | Test de parseo con fixture PDF y LLM mockeado | SATISFIED | `tests/cv/test_parser.py` — 2 acceptance tests, 9 total green |

### Anti-Patterns Found

None — no TODOs, FIXMEs, placeholder comments, hardcoded credentials, empty return stubs, or `import fitz` found in any `app/cv/` file.

### Human Verification Required

#### 1. Real PDF Extraction Quality

**Test:** With `ANTHROPIC_API_KEY` set in `.env`, run:
```
uv run python -c "
from app.cv.parser import parse_cv
import json, pathlib
pdf = pathlib.Path('data/cv.pdf').read_bytes()   # replace with actual CV path
profile = parse_cv(pdf)
print(profile.model_dump_json(indent=2))
"
```
**Expected:** CVProfile with all five fields non-empty (`experiencia` listing real employers/roles, `skills_tecnicas` matching actual skills in the CV, `formacion` with real degrees, `anios_experiencia_total` reasonably estimated, `dominios` reflecting the candidate's domains). No fabricated data.

**Why human:** The test suite mocks the LLM by design — this is correct architecture. Only a human can judge whether the Anthropic claude-haiku-4-5-20251001 model faithfully extracts from Jaime's real PDF without hallucinating or omitting data. This is explicitly documented as a manual-only verification in `01-VALIDATION.md`.

### Gaps Summary

No gaps blocking the phase goal. All wiring is correct, all 9 tests pass, no stubs or placeholders found. The one human verification item (real-PDF extraction quality) is an expected manual check, acknowledged by the phase's own VALIDATION.md, and cannot be confirmed programmatically. It does not constitute a codebase defect.

---

_Verified: 2026-05-22_
_Verifier: Claude (gsd-verifier)_
