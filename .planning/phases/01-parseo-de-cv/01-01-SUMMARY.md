---
phase: 01-parseo-de-cv
plan: 01
subsystem: test-infra
tags: [scaffolding, deps, pytest, fixtures, pymupdf]
dependency_graph:
  requires: []
  provides:
    - "pytest runnable via `uv run pytest` from project root"
    - "tests/conftest.py: sample_pdf_bytes, EXPECTED_PROFILE, mock_llm_client fixtures"
    - "app/ namespace packages importable under pytest (pythonpath=[\".\"])"
    - "Core deps installed: pymupdf, instructor, anthropic, python-dotenv"
  affects:
    - "All subsequent plans (01-02 to 01-04) depend on this test infra"
tech_stack:
  added:
    - pymupdf>=1.27.2.3
    - instructor>=1.15.1
    - anthropic>=0.104.0
    - python-dotenv>=1.2.2
    - pytest>=9.0.3 (dev)
  patterns:
    - "pytest config via [tool.pytest.ini_options] in pyproject.toml"
    - "In-memory PDF fixture generation with pymupdf (no reportlab needed)"
    - "MagicMock for instructor.from_anthropic() client surface"
key_files:
  created:
    - pyproject.toml (updated: deps + [tool.pytest.ini_options])
    - uv.lock
    - app/__init__.py
    - app/models/__init__.py
    - app/cv/__init__.py
    - tests/__init__.py
    - tests/cv/__init__.py
    - tests/fixtures/__init__.py
    - tests/conftest.py
  modified:
    - .gitignore (added to git tracking; content already correct)
decisions:
  - "Use pymupdf for in-memory PDF fixture generation instead of reportlab (pymupdf already a core dep; avoids test-only extra dependency)"
  - "Exit code 5 from pytest --collect-only is acceptable: means no tests collected (not a collection error) — correct for Wave 0 before any test functions exist"
metrics:
  duration_minutes: 2
  completed_date: "2026-05-22"
  tasks_completed: 3
  tasks_total: 3
  files_created: 9
  files_modified: 1
---

# Phase 01 Plan 01: Test Infrastructure Scaffolding (Wave 0) Summary

**One-liner:** Wave 0 test scaffolding — pymupdf/instructor/anthropic deps installed via uv, pytest config added to pyproject.toml with pythonpath=["."], and tests/conftest.py with in-memory PDF fixture and mocked instructor client ready for plans 02-04.

## What Was Built

Established the complete test and dependency scaffolding for Phase 1. Every subsequent plan (01-02 through 01-04) can now run `uv run pytest tests/cv -q` from the project root with zero additional setup.

### Task 1: Install deps and add pytest config
Installed the four phase dependencies (`pymupdf`, `instructor`, `anthropic`, `python-dotenv`) and the dev dependency (`pytest`) via `uv add`, updating `uv.lock`. Added `[tool.pytest.ini_options]` to `pyproject.toml` with:
- `testpaths = ["tests"]`
- `pythonpath = ["."]` — required so `from app.cv.parser import parse_cv` resolves under pytest
- `addopts = "-q"`

### Task 2: Create package tree and conftest with shared fixtures
Created all six `__init__.py` package markers (`app/`, `app/models/`, `app/cv/`, `tests/`, `tests/cv/`, `tests/fixtures/`), making the `app` namespace importable under pytest. Created `tests/conftest.py` exposing:
- `sample_pdf_bytes` (session scope): minimal PDF generated in-memory with pymupdf containing known text ("AI Engineer", "Acme Corp", "Python", "LLMs") for extractor and parser tests
- `EXPECTED_PROFILE`: module-level `CVProfile` constant used by mocks
- `mock_llm_client` (function scope): `MagicMock` mirroring the `instructor.from_anthropic()` surface — `.messages.create.return_value = EXPECTED_PROFILE`

### Task 3: Confirm cache dir is gitignored
Verified `.gitignore` already contains `.cache/` pattern covering `data/.cache/` at any depth. Confirmed via `git check-ignore data/.cache/test.json`. No duplicate rule added. Added `.gitignore` to git tracking.

## Deviations from Plan

None — plan executed exactly as written.

Note: `uv run pytest --collect-only` exits with code 5 ("no tests collected"), not 0, because no test functions exist yet in Wave 0. This is the correct pytest behavior and not a collection error. The plan's intent ("collection succeeds even with no test functions yet") is met — no ImportError, no SyntaxError.

## Known Stubs

None — this plan only establishes infrastructure (deps, config, fixtures). No application logic or data stubs.

## Threat Flags

No new security-relevant surface introduced. T-01-01 (data/.cache/ PII protection) confirmed mitigated by .gitignore verification in Task 3.

## Self-Check: PASSED

Files verified:
- pyproject.toml: contains pymupdf, instructor, anthropic, python-dotenv, tool.pytest.ini_options, pythonpath
- tests/conftest.py: contains sample_pdf_bytes, EXPECTED_PROFILE, mock_llm_client, pymupdf, messages.create
- All 7 package files exist
- data/.cache/ gitignored confirmed

Commits verified:
- ebe2351: chore(01-01): install phase deps and add pytest config
- 0d7d365: feat(01-01): create package tree and shared test fixtures
- 93cb13c: chore(01-01): confirm data/.cache/ is gitignored
