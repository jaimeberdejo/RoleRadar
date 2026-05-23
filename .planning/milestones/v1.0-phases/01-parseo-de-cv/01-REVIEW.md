---
phase: 01-parseo-de-cv
reviewed: 2026-05-22T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - app/cv/__init__.py
  - app/cv/cache.py
  - app/cv/extractor.py
  - app/cv/llm_client.py
  - app/cv/parser.py
  - tests/conftest.py
  - tests/cv/test_cache.py
  - tests/cv/test_extractor.py
  - tests/cv/test_llm_client.py
  - tests/cv/test_parser.py
findings:
  critical: 1
  warning: 4
  info: 3
  total: 8
status: issues_found
---

# Phase 01: Code Review Report — CV PDF Parsing

**Reviewed:** 2026-05-22
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

The CV parsing module is well-structured and follows the single-responsibility principle cleanly across `extractor.py`, `cache.py`, `llm_client.py`, and `parser.py`. The cache-first flow (CV-03), injection seam for the LLM client, and test isolation via `monkeypatch.setenv` are all sound. Tests pass and the happy path is correctly covered.

However, there is one critical bug: `extract_text_from_pdf` does not catch `pymupdf.FileDataError` or `pymupdf.EmptyFileError`, so passing corrupted or empty bytes produces a raw pymupdf exception instead of the documented `ValueError` — this breaks the documented contract and will propagate as an opaque 500 in the FastAPI endpoint. Four warnings follow: missing `encoding=` on file I/O (portability risk for Spanish CV content), no path validation in cache key helpers (path-traversal possible if called with untrusted input), a stale module-level `CACHE_DIR` that will mislead readers, and missing error handling for a corrupted cache file. Three info-level observations are also documented.

---

## Critical Issues

### CR-01: `extract_text_from_pdf` Leaks pymupdf-Specific Exceptions for Invalid Input

**File:** `app/cv/extractor.py:25-33`

**Issue:** The docstring declares `Raises: ValueError` as the only exception, but `pymupdf.open(stream=..., filetype="pdf")` raises `pymupdf.FileDataError` for non-PDF bytes and `pymupdf.EmptyFileError` for empty input. Neither is caught or wrapped. Any caller that does `except ValueError` (including the documented public interface of `parse_cv`) will silently propagate a `pymupdf.FileDataError`, which becomes an unhandled 500 at the FastAPI layer. Verified with `uv run python`:

```
# b"not a pdf"  → pymupdf.FileDataError: Failed to open stream
# b""           → pymupdf.EmptyFileError: Cannot open empty stream.
```

**Fix:**
```python
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            pages_text = [page.get_text() for page in doc]
    except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
        raise ValueError(
            f"No se pudo abrir el PDF: {exc}. "
            "Comprueba que el fichero es un PDF válido y no está vacío."
        ) from exc
    text = "\n\n".join(pages_text).strip()
    if not text:
        raise ValueError(
            "El PDF no contiene capa de texto extraíble. "
            "PDFs escaneados (solo imagen) no están soportados en v1."
        )
    return text
```

---

## Warnings

### WR-01: `cache.py` File I/O Has No Explicit Encoding — Breaks on Non-UTF-8 Locales

**File:** `app/cv/cache.py:52` and `app/cv/cache.py:69`

**Issue:** `cache_file.read_text()` and `cache_file.write_text(...)` both use the platform default encoding. `model_dump_json()` (Pydantic v2, backed by Rust `serde_json`) emits literal UTF-8 characters for non-ASCII content — Spanish names, roles like "Ingeniero de IA", accented skills, etc. On a Windows or Latin-1 locale host this will either `UnicodeEncodeError` on write or silently corrupt multi-byte characters on read, poisoning the cache. The project's own `Experiencia` schema stores `empresa` and `rol` as plain `str`, so real-world CV data will hit this.

**Fix:** Always pass `encoding="utf-8"` explicitly:
```python
# line 52
return CVProfile.model_validate_json(cache_file.read_text(encoding="utf-8"))

# line 69
cache_file.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
```

---

### WR-02: `load_cached_profile` / `save_cached_profile` Accept Arbitrary `content_hash` — Path Traversal Risk

**File:** `app/cv/cache.py:41-69`

**Issue:** Both public functions accept `content_hash: str` without validation. If called with a value like `"../../../etc/cron.d/evil"` the resulting path is `_cache_dir() / "../../../etc/cron.d/evil.json"`, which resolves outside the cache directory. Verified:

```
Path('/tmp/test_cache') / '../etc/passwd.json'
→ resolved: /private/tmp/etc/passwd.json
```

In the current codebase `parse_cv` always calls `pdf_hash()` first, which produces a safe hex digest. But the public signature of `load_cached_profile` / `save_cached_profile` places no restriction on the input — a future caller or the `/cv/parse` FastAPI endpoint receiving a user-supplied hash parameter could exploit this for read/write outside the cache directory.

**Fix:** Validate `content_hash` to be a safe hex string before constructing the path, or resolve the resulting path and assert it stays under `_cache_dir()`:
```python
import re
_HEX_RE = re.compile(r'^[0-9a-f]{64}$')

def _validate_hash(content_hash: str) -> None:
    if not _HEX_RE.match(content_hash):
        raise ValueError(f"Invalid cache key: {content_hash!r}")

def load_cached_profile(content_hash: str) -> CVProfile | None:
    _validate_hash(content_hash)
    cache_file = _cache_dir() / f"{content_hash}.json"
    ...

def save_cached_profile(content_hash: str, profile: CVProfile) -> None:
    _validate_hash(content_hash)
    ...
```

---

### WR-03: Corrupted Cache File Raises Unhandled `ValidationError` in `load_cached_profile`

**File:** `app/cv/cache.py:52`

**Issue:** If the JSON file in the cache directory is truncated or corrupted (disk full, interrupted write, manual edit), `CVProfile.model_validate_json(cache_file.read_text())` raises a Pydantic `ValidationError`. This exception is not caught anywhere in the call chain (`load_cached_profile` → `parse_cv`), so it propagates as a 500 without any user-actionable message. Verified:

```
CVProfile.model_validate_json('{invalid json')
→ pydantic_core.ValidationError: 1 validation error for CVProfile
```

The correct recovery is to log a warning, delete (or rename) the corrupt file, and fall through to re-parse from the PDF.

**Fix:**
```python
import logging
logger = logging.getLogger(__name__)

def load_cached_profile(content_hash: str) -> CVProfile | None:
    cache_file = _cache_dir() / f"{content_hash}.json"
    if not cache_file.exists():
        return None
    try:
        return CVProfile.model_validate_json(cache_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cache corrupta para hash %s, se ignorará: %s", content_hash, exc)
        try:
            cache_file.unlink(missing_ok=True)
        except OSError:
            pass
        return None
```

---

### WR-04: Stale Module-Level `CACHE_DIR` Constant Will Mislead Runtime Readers

**File:** `app/cv/cache.py:21`

**Issue:** `CACHE_DIR: Path = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))` is evaluated **once at import time**. Any change to `CV_CACHE_DIR` after import (e.g., via `monkeypatch.setenv` in tests, or a runtime config reload) is not reflected in `CACHE_DIR`. The internal code correctly uses `_cache_dir()` for all operations, but the exported `CACHE_DIR` symbol is part of the module's public namespace. Any external code that imports and reads `CACHE_DIR` directly will get a stale value and likely cache to the wrong directory without any error. The inline comment acknowledges this but a silent staleness is a footgun — especially since `_cache_dir()` already exists.

**Fix:** Remove the module-level `CACHE_DIR` constant entirely, or demote it to a private `_CACHE_DIR_DEFAULT` string constant to make clear it is not live:
```python
# Instead of exporting a live-looking Path constant, expose only the function
# _CACHE_DIR_DEFAULT = "data/.cache"  # private reference, not exported
```
If it must remain public, annotate it explicitly:
```python
# WARNING: evaluated at import time; use _cache_dir() for the current value.
CACHE_DIR: Path = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
```

---

## Info

### IN-01: `sample_pdf_bytes` Fixture and Test Helper in `test_extractor.py` Leave pymupdf Documents Open

**File:** `tests/conftest.py:50-60` and `tests/cv/test_extractor.py:31-36`

**Issue:** Both fixtures create a `pymupdf.Document` via `pymupdf.open()`, call `.tobytes()`, and return the bytes — but never call `doc.close()`. Each open document holds a native MuPDF context. In the session-scoped fixture this is a single leak, but the pattern sets a bad precedent. The `with` context manager (as used in `extractor.py`) is the correct approach.

**Fix:**
```python
# conftest.py
doc = pymupdf.open()
try:
    page = doc.new_page()
    page.insert_text((72, 72), "...", fontsize=12)
    return doc.tobytes()
finally:
    doc.close()

# test_extractor.py — test_extract_text_raises_on_empty_pdf
with pymupdf.open() as doc:
    doc.new_page()
    empty_pdf = doc.tobytes()
```

---

### IN-02: `test_llm_client.py` Duplicates `EXPECTED_PROFILE` Instead of Reusing `conftest.EXPECTED_PROFILE`

**File:** `tests/cv/test_llm_client.py:20-31`

**Issue:** `_MOCK_PROFILE` is a local copy of `EXPECTED_PROFILE` from `conftest.py` — same fields, same values. If the `CVProfile` fixture data changes, both copies need updating. The duplication is low-risk (test-only) but the `conftest.EXPECTED_PROFILE` constant exists precisely to avoid this.

**Fix:** Import and reuse:
```python
from tests.conftest import EXPECTED_PROFILE as _MOCK_PROFILE
```

---

### IN-03: No Test Covers the `ValueError` Path for a Corrupted/Non-PDF Input to `parse_cv`

**File:** `tests/cv/test_parser.py`

**Issue:** `test_parse_cv_returns_cv_profile` and `test_cache_avoids_second_llm_call` cover the happy path and the cache short-circuit. There is no test that passes non-PDF bytes to `parse_cv` and asserts a clean `ValueError`. Once CR-01 is fixed, this path will be testable and should be covered, since it is explicitly documented in the `parse_cv` docstring.

**Fix:** Add a test:
```python
def test_parse_cv_raises_for_invalid_pdf(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))
    with pytest.raises(ValueError):
        parse_cv(b"not a pdf")
```

---

_Reviewed: 2026-05-22_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
