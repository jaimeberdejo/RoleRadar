---
phase: 02-normalizacion-y-deduplicacion
fixed_at: 2026-05-22T00:00:00Z
review_path: .planning/phases/02-normalizacion-y-deduplicacion/02-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 10
skipped: 0
status: all_fixed
---

# Phase 02: Code Review Fix Report

**Fixed at:** 2026-05-22T00:00:00Z
**Source review:** `.planning/phases/02-normalizacion-y-deduplicacion/02-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 10 (CR: 1, WR: 7, IN: 2)
- Fixed: 10
- Skipped: 0

## Fixed Issues

### CR-01: `merge_group` drops `urls_alternativas` from non-canonical group members

**Files modified:** `app/dedup/merger.py`
**Commit:** `566be1f`
**Applied fix:** Replaced the narrow URL collection (only `.url` from non-canonical members) with a full pool of all URLs from all group members (both `.url` and `.urls_alternativas`). After pooling, the canonical's own URL is excluded, and the list is deduplicated in insertion order. This preserves URLs accumulated during exact-level merge when the canonical changes at semantic level.

---

### WR-01: `arbeitnow_mapper` crashes with `TypeError` when `description` is `None`

**Files modified:** `app/dedup/mappers.py`
**Commit:** `faeb8e0`
**Applied fix:** Changed `raw.get("description", "")` to `raw.get("description") or ""` so that both an absent key and an explicit `null`/`None` value are coerced to empty string before passing to `re.sub`.

---

### WR-02: `stable_job_id` vulnerable to separator-injection hash collisions

**Files modified:** `app/dedup/normalize.py`
**Commit:** `67b1b01`
**Applied fix:** Replaced the `|` field separator with `\x00` (NUL byte), which cannot appear in `normalize_field` output (which only produces Unicode text). Updated the docstring to explain the rationale. No tests asserted the old `|` format.

---

### WR-03: `generic_mapper` passes raw integer `created_at` to `Job.posted_at`

**Files modified:** `app/dedup/mappers.py`
**Commit:** `c55e2a6`
**Applied fix:** Added timestamp conversion in `generic_mapper` mirroring `arbeitnow_mapper`: string values pass through unchanged; `int`/`float` values are converted to ISO 8601 via `datetime.fromtimestamp(..., tz=timezone.utc).isoformat()`; invalid timestamps produce `None` with error recovery.

---

### WR-04: `FakeEmbedder` does not L2-normalize priority-1 and priority-2 paths

**Files modified:** `app/dedup/embedder.py`
**Commit:** `8464b8e`
**Applied fix:** Moved the L2 normalization (`norma = np.linalg.norm(v); v = v / (norma + 1e-9)`) outside the `if/elif/else` branches so it applies unconditionally to all three resolution paths (dict lookup, default_vector, hash-fallback). Zero-vector guard (`+ 1e-9`) is retained.

---

### WR-05: `FakeEmbedder.embed([])` returns wrong shape `(0,)` instead of `(0, dim)`

**Files modified:** `app/dedup/embedder.py`
**Commit:** `8464b8e`
**Applied fix:** Changed `return np.array([], dtype=np.float32)` to `return np.empty((0, self._dim), dtype=np.float32)`, matching the Protocol contract of shape `(len(texts), dim)`. The existing test only checked `len == 0` so it continued to pass with the correct 2-D shape.

---

### WR-06: `deduplicate()` docstring claims output is ordered but no sort was applied

**Files modified:** `app/dedup/__init__.py`
**Commit:** `90145e9`
**Applied fix:** Implemented the sort: `representatives.sort(key=lambda j: len(j.description), reverse=True)` before the `semantic_cluster` call. Updated the docstring to accurately describe the sort key and its purpose (deterministic canonical selection, not a general ordering guarantee).

---

### WR-07: `semantic_cluster` docstring falsely claims `deduplicate()` sorts before calling it

**Files modified:** `app/dedup/semantic.py`
**Commit:** `90145e9`
**Applied fix:** The sort is now actually implemented in `deduplicate()` (see WR-06). The `semantic_cluster` docstring was updated to reflect that the sort is now genuinely applied by the facade, making the claim truthful rather than aspirational.

---

### IN-01: `conftest.py` comment misidentifies the failure type as `ValidationError`

**Files modified:** `tests/conftest.py`
**Commit:** `04531af`
**Applied fix:** Corrected the comment to explain that the failure is a `TypeError` raised by `unicodedata.normalize()` inside `normalize_field()` (called from `stable_job_id()`) before Pydantic validation ever runs.

---

### IN-02: No test for two-level URL accumulation chain

**Files modified:** `tests/dedup/test_dedup.py`
**Commit:** `5075a20`
**Applied fix:** Added `test_deduplicate_exact_urls_survive_semantic_merge` — an end-to-end test with three jobs: j_a and j_b are exact duplicates (exact-level merge accumulates j_a.url into the canonical); j_c has a different title but identical embeddings (semantic-level merge picks j_c as canonical due to longest description). The test asserts both `https://example.com/a` (from exact-level merge) and `https://example.com/b` (primary URL of the exact-level canonical) are present in `urls_alternativas` of the final result.

---

## Skipped Issues

None — all findings were fixed.

---

_Fixed: 2026-05-22T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
