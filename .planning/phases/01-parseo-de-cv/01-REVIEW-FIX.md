---
phase: 01-parseo-de-cv
fixed_at: 2026-05-22T00:00:00Z
review_path: .planning/phases/01-parseo-de-cv/01-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-05-22
**Source review:** .planning/phases/01-parseo-de-cv/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (CR-01, WR-01, WR-02, WR-03, WR-04, IN-03)
- Fixed: 6
- Skipped: 0

## Fixed Issues

### CR-01: extract_text_from_pdf leaks pymupdf-specific exceptions

**Files modified:** `app/cv/extractor.py`
**Commit:** c942d7e
**Applied fix:** Wrapped `pymupdf.open(...)` in a `try/except (pymupdf.FileDataError, pymupdf.EmptyFileError)` block that re-raises as `ValueError` with a Spanish error message. The existing text-less-PDF `ValueError` is preserved unchanged. Docstring updated to document the expanded raises contract.

---

### WR-01 / WR-02 / WR-03 / WR-04: cache.py hardening

**Files modified:** `app/cv/cache.py`, `tests/cv/test_cache.py`
**Commit:** c22d0a1
**Applied fix:**

- WR-01: Added `encoding="utf-8"` to both `read_text()` and `write_text()` calls.
- WR-02: Added `_validate_hash()` helper using `re.compile(r"^[0-9a-f]{64}$")`. Both `load_cached_profile` and `save_cached_profile` call it as their first step, raising `ValueError` on any non-sha256 input (blocks path traversal).
- WR-03: Wrapped `CVProfile.model_validate_json(...)` in a broad `except Exception` block; on failure, logs a `logger.warning(...)`, calls `cache_file.unlink(missing_ok=True)`, and returns `None` so the caller falls through to re-parse.
- WR-04: Removed the stale module-level `CACHE_DIR: Path = ...` constant entirely. All internal code already used `_cache_dir()` exclusively; no external callers existed.

Test updates: replaced `h = "abc123"` with `_VALID_HASH = "a" * 64` and added three new tests: `test_cache_corrupt_file_returns_none`, `test_invalid_hash_raises_for_load`, `test_invalid_hash_raises_for_save`.

---

### IN-03: no test for parse_cv ValueError on invalid PDF

**Files modified:** `tests/cv/test_parser.py`
**Commit:** f85fe61
**Applied fix:** Added `test_parse_cv_raises_for_invalid_pdf` which calls `parse_cv(b"not a pdf")` and asserts `ValueError` is raised. No LLM mock needed — the error surfaces before the LLM is reached. Uses `monkeypatch` to redirect `CV_CACHE_DIR` to `tmp_path`.

---

## Skipped Issues

None — all in-scope findings were fixed.

---

_Fixed: 2026-05-22_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
