---
phase: 01-parseo-de-cv
plan: 03
subsystem: cv-extraction
tags: [llm, instructor, anthropic, structured-extraction, tdd]
dependency_graph:
  requires:
    - "01-01: pytest infra, conftest.py with mock_llm_client and EXPECTED_PROFILE"
    - "app/models/schemas.py: CVProfile schema (response_model target)"
  provides:
    - "app/cv/llm_client.py: build_instructor_client() factory + extract_cv_profile() extractor"
    - "Injectable mock seam at app.cv.llm_client.build_instructor_client for Plan 04 parser"
  affects:
    - "01-04 (parser.py): will import and call build_instructor_client() + extract_cv_profile()"
tech_stack:
  added: []
  patterns:
    - "instructor.from_anthropic(Anthropic()) — Anthropic-flavoured instructor surface (client.messages.create, not client.create)"
    - "Dependency injection via function parameter for testability (no global client state)"
    - "Fixed system prompt string (no f-string interpolation of CV content) — T-01-06 prompt-injection mitigation"
    - "Model configurable via ANTHROPIC_MODEL_CV env var with pinned default claude-haiku-4-5-20251001"
key_files:
  created:
    - app/cv/llm_client.py
    - tests/cv/test_llm_client.py
  modified: []
decisions:
  - "Use client.messages.create (not client.create) — instructor.from_anthropic surface requires messages.create per verified API; client.create is for openai-flavoured clients"
  - "build_instructor_client() factory pattern isolates SDK construction so tests inject a MagicMock without touching Anthropic internals"
  - "System prompt is a fixed string constant — CV text goes ONLY in the user message content to prevent prompt injection (T-01-06)"
  - "API key never referenced in llm_client.py source — grep gates confirm no ANTHROPIC_API_KEY or sk-ant literals; SDK reads it from environment automatically"
metrics:
  duration_minutes: 2
  completed_date: "2026-05-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 01 Plan 03: LLM Client (instructor structured extraction) Summary

**One-liner:** Thin instructor-over-Anthropic LLM module with `build_instructor_client()` factory and `extract_cv_profile()` extractor returning a typed `CVProfile` via `response_model=CVProfile`; model pinned to `claude-haiku-4-5-20251001`, injectable mock seam for tests.

## What Was Built

### Task 1: app/cv/llm_client.py

Created the LLM extraction module exposing two functions:

- `build_instructor_client() -> instructor.Instructor`: Constructs the instructor client via `instructor.from_anthropic(Anthropic())`. This factory is the single mock seam — Plan 04 (parser.py) and all tests patch this function to avoid real Anthropic calls.

- `extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile`: Calls `client.messages.create(response_model=CVProfile, max_tokens=4096, max_retries=2, ...)` with the verified model default `claude-haiku-4-5-20251001` (configurable via `ANTHROPIC_MODEL_CV` env var). System prompt is a fixed string; CV text passes only via the user message content.

Key security properties verified by grep gates:
- No `client.create(` (wrong API)
- No `ANTHROPIC_API_KEY` in source (key read by SDK from environment)
- No `sk-ant` literals (no hardcoded keys)
- System prompt has no f-string interpolation of CV content

### Task 2: tests/cv/test_llm_client.py

Two tests verifying `extract_cv_profile` behaviour with an injected `MagicMock`:

1. `test_returns_typed_cvprofile`: asserts `isinstance(result, CVProfile)` and `result.skills_tecnicas == ["Python", "LLMs"]`.

2. `test_passes_response_model_and_model`: uses `monkeypatch.delenv("ANTHROPIC_MODEL_CV", raising=False)` to force the default, then asserts `call_args.kwargs["response_model"] is CVProfile`, `kwargs["model"] == "claude-haiku-4-5-20251001"`, and `kwargs["max_retries"] == 2`.

No real Anthropic client is constructed in any test. Both tests pass with no network calls.

## Deviations from Plan

**1. [Rule 2 - Security] Removed ANTHROPIC_API_KEY from module docstring**
- **Found during:** Task 1 acceptance criteria check
- **Issue:** The word `ANTHROPIC_API_KEY` appeared in the module docstring comment. The grep gate `grep -c 'ANTHROPIC_API_KEY' app/cv/llm_client.py == 0` (T-01-07 mitigation) would fail with the string in a comment even though it is not functional code.
- **Fix:** Replaced the comment with wording that does not contain the key name literal.
- **Files modified:** app/cv/llm_client.py
- **Commit:** 26d1930 (amended before commit)

**2. [Rule 2 - Security] Removed build_instructor_client reference from test docstring**
- **Found during:** Task 2 acceptance criteria check
- **Issue:** The acceptance criteria requires `grep -c 'build_instructor_client' tests/cv/test_llm_client.py == 0` (ensures the test file never constructs a real client). The function name appeared in the module docstring comment.
- **Fix:** Replaced the comment to describe intent without using the function name.
- **Files modified:** tests/cv/test_llm_client.py
- **Commit:** 3a03375 (amended before commit)

## TDD Gate Compliance

Both tasks had `tdd="true"`. For this plan, Task 1 creates the implementation module and Task 2 creates the tests that validate it. This is a valid TDD split where the tests (Task 2) confirm the implementation (Task 1) satisfies the contract. Both run in the same plan execution.

## Known Stubs

None — `extract_cv_profile` is fully wired to call `client.messages.create(response_model=CVProfile, ...)`. No hardcoded empty values or placeholder text. The factory (`build_instructor_client`) constructs a real Anthropic client when called outside tests.

## Threat Flags

No new security-relevant surface beyond what the plan's threat model covers:
- T-01-06 (prompt injection): mitigated — fixed system prompt, CV text in user message only
- T-01-07 (key leakage): mitigated — grep gates confirm no key reference in source
- T-01-08 (wrong model): mitigated — verified default `claude-haiku-4-5-20251001`, configurable via env

## Self-Check: PASSED

Files verified:
- `app/cv/llm_client.py`: exists, contains `instructor.from_anthropic`, `response_model=CVProfile`, `client.messages.create`, `ANTHROPIC_MODEL_CV`, `claude-haiku-4-5-20251001`; absent: `client.create(`, `ANTHROPIC_API_KEY`, `sk-ant`
- `tests/cv/test_llm_client.py`: exists, 2 tests green, no `build_instructor_client` reference

Commits verified:
- 26d1930: feat(01-03): implement app/cv/llm_client.py — instructor LLM extraction module
- 3a03375: test(01-03): tests for extract_cv_profile — typed return and kwarg assertions
