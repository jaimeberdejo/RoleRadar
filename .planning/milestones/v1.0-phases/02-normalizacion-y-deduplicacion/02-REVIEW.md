---
phase: 02-normalizacion-y-deduplicacion
reviewed: 2026-05-22T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - app/dedup/__init__.py
  - app/dedup/normalize.py
  - app/dedup/mappers.py
  - app/dedup/embedder.py
  - app/dedup/exact.py
  - app/dedup/semantic.py
  - app/dedup/merger.py
  - tests/dedup/test_normalize.py
  - tests/dedup/test_dedup_units.py
  - tests/dedup/test_dedup.py
findings:
  critical: 1
  warning: 7
  info: 2
  total: 10
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-05-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 02 covers raw-offer normalization (two source mappers + generic fallback), two-level
deduplication (exact hash + greedy cosine clustering), and merge. The overall architecture is
sound: deferred imports avoid the torch drag, the greedy clustering is correctly implemented,
and the test fixtures are correctly keyed to `build_embed_text` output.

One **blocker** was found: `merge_group` silently drops the `urls_alternativas` already
accumulated on non-canonical jobs during the semantic-level pass. This means every exact-level
URL accumulation is lost whenever the canonical changes at the semantic level.

Seven warnings cover: a `None`-description crash in `arbeitnow_mapper`, a separator-injection
hash collision in `stable_job_id`, an integer `posted_at` crash in `generic_mapper`, missing
L2-normalization in two `FakeEmbedder` paths, a wrong empty-list return shape in
`FakeEmbedder`, and two contradicting doc/comment claims about output ordering that describe
behavior that was never implemented.

---

## Critical Issues

### CR-01: `merge_group` drops `urls_alternativas` from non-canonical group members

**File:** `app/dedup/merger.py:63-70`

**Issue:** `merge_group` builds the new `urls_alternativas` list as:

```python
urls_alternativas_nuevas = [j.url for j in group if j is not canonical and j.url is not None]
todas_las_alternativas = list(canonical.urls_alternativas) + urls_alternativas_nuevas
```

This collects only `.url` (the primary URL) from each discarded job, ignoring `.urls_alternativas`
on those discarded jobs. In the two-level dedup pipeline this is a data-loss defect:

1. **Exact-level merge** (level 1): `job_A` and `job_B` share the same `company+title`. `job_A`
   is canonical (longer desc), `job_B.url` is appended → `job_A.urls_alternativas = ['url_B']`.
2. **Semantic-level merge** (level 2): `job_A` (representative) and `job_C` (different title,
   same semantic cluster) are merged. `job_C` has a longer description, becomes the new
   canonical. `merge_group` sets:
   ```
   todas = list(job_C.urls_alternativas)   # []
          + [job_A.url]                     # only the primary URL of the discarded job
   # 'url_B' — previously accumulated in job_A.urls_alternativas — is silently lost
   ```

Any URL tracked during exact deduplication can disappear from the final canonical whenever the
canonical changes at the semantic level.

**Fix:** Collect `urls_alternativas` from every group member, not just the canonical, and union
them all (excluding the final canonical URL to avoid self-reference):

```python
# Collect ALL alternative URLs from every member of the group
all_urls: list[str] = []
for j in group:
    if j.url is not None:
        all_urls.append(j.url)
    all_urls.extend(j.urls_alternativas)

# The canonical's primary URL is not an "alternative"
canonical_url = canonical.url
todas_las_alternativas = [u for u in all_urls if u != canonical_url]
# Optionally deduplicate while preserving order:
seen: set[str] = set()
todas_las_alternativas = [u for u in todas_las_alternativas if not (u in seen or seen.add(u))]
```

---

## Warnings

### WR-01: `arbeitnow_mapper` crashes with `TypeError` when `description` key is present but has `None` value

**File:** `app/dedup/mappers.py:67-68`

**Issue:**
```python
raw_desc = raw.get("description", "")   # returns None if key exists with value None
clean_desc = re.sub(r"<[^>]+>", " ", raw_desc).strip()  # TypeError: expected str, got NoneType
```

`dict.get(key, default)` only returns the default when the key is **absent**. If the API sends
`"description": null`, `raw.get("description", "")` returns `None`, and `re.sub` raises
`TypeError`. Because `normalize_jobs` catches all exceptions, the offer goes to `errors` instead
of crashing the batch, but the mapping contract claims to handle untrusted external payloads.

**Fix:**
```python
raw_desc = raw.get("description") or ""
```
This treats both absent keys and explicit `None`/falsy values as empty string before passing to `re.sub`.

---

### WR-02: `stable_job_id` is vulnerable to separator-injection hash collisions

**File:** `app/dedup/normalize.py:79-85`

**Issue:** The hash key is built by concatenating normalized fields with `|` as separator:
```python
key = normalize_field(company) + "|" + normalize_field(title) + "|" + normalize_field(location)
```
`normalize_field` preserves the `|` character (it only strips diacritics and casefolds). If a
company or title contains a literal `|`, distinct `(company, title, location)` triples can
produce identical keys:

```python
stable_job_id("Corp", "A|Dev", "")   # key: "corp|a|dev|"
stable_job_id("Corp|A", "Dev", "")   # key: "corp|a|dev|"   ← same hash
```

Two genuinely different job offers would be assigned the same `id`, causing silent deduplication
of unrelated offers.

**Fix:** Use a separator that cannot appear in normalized output, such as the null byte `\x00`,
or use length-prefixed encoding:
```python
key = "\x00".join([normalize_field(company), normalize_field(title), normalize_field(location)])
```

---

### WR-03: `generic_mapper` passes raw `posted_at` / `created_at` integer directly to `Job`, causing Pydantic `ValidationError`

**File:** `app/dedup/mappers.py:193`

**Issue:**
```python
posted_at=raw.get("posted_at") or raw.get("created_at"),
```
`Job.posted_at` is typed `Optional[str]`. Pydantic v2 in strict mode rejects non-string values.
If `created_at` is a Unix timestamp integer (as returned by Arbeitnow-style APIs routed through
the generic mapper), the `Job` constructor raises a `ValidationError`, sending the offer to
`errors`. The `arbeitnow_mapper` correctly converts the integer to ISO 8601; `generic_mapper`
does not.

**Fix:** Mirror the timestamp conversion from `arbeitnow_mapper`:
```python
_ts_raw = raw.get("posted_at") or raw.get("created_at")
posted_at: str | None = None
if isinstance(_ts_raw, str):
    posted_at = _ts_raw
elif isinstance(_ts_raw, (int, float)):
    try:
        posted_at = datetime.fromtimestamp(int(_ts_raw), tz=timezone.utc).isoformat()
    except (ValueError, OSError, OverflowError):
        pass
```

---

### WR-04: `FakeEmbedder` does not L2-normalize pre-specified vectors (priority-1 and priority-2 paths)

**File:** `app/dedup/embedder.py:150-155`

**Issue:** The `Embedder` Protocol contract states:
> "Los vectores son L2-normalizados: dot(v, v) == 1.0"

`FakeEmbedder.embed()` has three resolution paths. Only the hash-fallback path (priority 3)
normalizes. The priority-1 (dict lookup) and priority-2 (default_vector) paths do not:

```python
if texto in self._vectors:
    v = np.array(self._vectors[texto], dtype=np.float32)   # no normalization
elif self._default_vector is not None:
    v = np.array(self._default_vector, dtype=np.float32)   # no normalization
```

If a caller passes a non-unit vector (e.g., `[3.0, 4.0, 0.0, 0.0]`), `FakeEmbedder` returns it
unnormalized. `semantic_cluster` then computes `E @ E.T` and treats it as cosine similarity, but
for non-unit vectors this is the dot product, not cosine similarity. Tests happen to pass only
because the test fixtures already supply unit vectors (`[1,0,0,0]` etc.).

**Fix:** Apply L2 normalization on all three paths, or document that callers of `FakeEmbedder`
must supply pre-normalized vectors and enforce it with an assertion:

```python
v = np.array(self._vectors[texto], dtype=np.float32)
norm = np.linalg.norm(v)
v = v / (norm + 1e-9)
```

---

### WR-05: `FakeEmbedder.embed([])` returns shape `(0,)` instead of `(0, dim)`, violating the Protocol contract

**File:** `app/dedup/embedder.py:145-146`

**Issue:**
```python
if not texts:
    return np.array([], dtype=np.float32)  # shape (0,) — wrong
```
The Protocol contract specifies `shape (len(texts), dim)`. For an empty list this should be
`shape (0, dim)` (a 2-D array with zero rows). Returning a 1-D `(0,)` array would cause a shape
error if any caller performs matrix operations on the result. `semantic_cluster` guards against
this with an early `if not jobs` return, so no crash happens today, but the contract is broken.
The test for this case (`test_embed_lista_vacia_devuelve_array_vacio`) only checks `len == 0`
and does not catch the wrong number of dimensions.

**Fix:**
```python
if not texts:
    return np.empty((0, self._dim), dtype=np.float32)
```

---

### WR-06: `deduplicate()` docstring claims output is ordered, but no sort is applied

**File:** `app/dedup/__init__.py:99`

**Issue:** The docstring return description reads:
> "Lista de Jobs únicos, fusionados y **ordenados**."

The implementation has no sort step:
```python
result = [merge_group([representatives[i] for i in cluster]) for cluster in clusters]
return result
```
Output order is determined by the order `exact_group` (which uses a `defaultdict` and is
insertion-ordered in Python 3.7+) and by greedy cluster seed selection. Neither is a meaningful
"ordered" output for the caller.

**Fix:** Either remove "y ordenados" from the docstring, or add an explicit sort (e.g., by
`description` length descending, matching the merge strategy) and document the sort key.

---

### WR-07: `semantic.py` documents that `deduplicate()` sorts before calling `semantic_cluster`, but this is not implemented

**File:** `app/dedup/semantic.py:68-69`

**Issue:** The docstring for `semantic_cluster` states:
> "Para mayor determinismo en producción, ordenar los jobs por longitud de descripción
>  descendente antes de llamar (Pitfall 5 de RESEARCH.md). **El facade deduplicate() aplica ese
>  orden.**"

`deduplicate()` in `app/dedup/__init__.py` does not sort `representatives` before passing them to
`semantic_cluster`. The greedy algorithm is order-dependent: with an unsorted input, which job
becomes the cluster seed is non-deterministic across batches with different insertion orders,
leading to different canonical selections and different `urls_alternativas` accumulation.

**Fix:** Either add the sort in `deduplicate()` before the `semantic_cluster` call:
```python
representatives.sort(key=lambda j: len(j.description), reverse=True)
```
Or remove the false claim from the `semantic_cluster` docstring if the sort is intentionally
left to the caller.

---

## Info

### IN-01: `conftest.py` malformed-payload comment incorrectly says the error is a `ValidationError`

**File:** `tests/conftest.py:189-191`

**Issue:** The comment states:
> "Los valores de tipo incorrecto (company_name=entero, title=None) hacen que la validación de
>  Job falle con **ValidationError**."

The actual failure in `arbeitnow_mapper` is a `TypeError` raised by
`unicodedata.normalize('NFD', 12345)` inside `normalize_field()`, which is called from
`stable_job_id()` before Pydantic ever runs. The functional behavior (offer goes to `errors`,
batch continues) is correct, but the comment misleads anyone debugging the error path.

**Fix:** Update the comment:
```python
# Por qué es inválido:
# - "company_name": 12345  → tipo int; normalize_field(int) lanza TypeError en stable_job_id
# - "title": None          → normalize_field(None) también lanza TypeError
```

---

### IN-02: No test exercises the two-level URL accumulation chain (exact merge then semantic merge)

**File:** `tests/dedup/test_dedup.py` (missing test)

**Issue:** All `urls_alternativas` tests (both unit and end-to-end) check either the exact-level
merge OR the semantic-level merge in isolation. No test verifies that a URL accumulated during
the exact-level pass survives through the semantic-level pass when the canonical changes. This
gap allowed the bug described in CR-01 to go undetected.

**Fix:** Add an end-to-end test in `test_dedup.py`:

```python
def test_deduplicate_exact_urls_survive_semantic_merge(embedder_identico):
    """URLs accumulated during exact-level merge must survive semantic-level merge."""
    # j_a and j_b are exact duplicates → merge into canonical_ab (longer desc = j_b)
    # canonical_ab.urls_alternativas = ['https://example.com/a']
    # j_c has different title (semantic dup of canonical_ab via embedder_identico,
    # longer desc than canonical_ab) → becomes new canonical
    # canonical_c.urls_alternativas must contain BOTH 'url_b_primary' AND 'url_a_from_exact'
    j_a = make_job("id-a", "AI Eng", "Corp", "Short.", "https://example.com/a")
    j_b = make_job("id-b", "AI Eng", "Corp", "Medium description here.", "https://example.com/b")
    j_c = make_job("id-c", "LLM Eng", "Corp2",
                   "Very long description that beats everything else.", "https://example.com/c")

    result = deduplicate([j_a, j_b, j_c], embedder=embedder_identico)

    assert len(result) == 1
    alt_urls = result[0].urls_alternativas
    assert "https://example.com/a" in alt_urls, "URL from exact-level merge must survive"
    assert "https://example.com/b" in alt_urls
```

---

_Reviewed: 2026-05-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
