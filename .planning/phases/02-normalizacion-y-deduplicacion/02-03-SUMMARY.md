---
phase: 02-normalizacion-y-deduplicacion
plan: "03"
subsystem: dedup
tags: [embeddings, deduplication, semantic-clustering, lazy-import, numpy, pydantic-v2]
dependency_graph:
  requires: [02-01, 02-02]
  provides: [DEDUP-01, DEDUP-02, DEDUP-03]
  affects: [02-04]
tech_stack:
  added: [numpy]
  patterns: [lazy-import, protocol-injection, greedy-cosine-clustering, pydantic-model_copy]
key_files:
  created:
    - app/dedup/embedder.py
    - app/dedup/exact.py
    - app/dedup/semantic.py
    - app/dedup/merger.py
    - tests/dedup/test_dedup_units.py
  modified: []
decisions:
  - "FakeEmbedder vive en app/dedup/embedder.py (no en tests/) siguiendo el patrón de Phase 1: la seam de inyección vive junto a la implementación real"
  - "Fallback de FakeEmbedder usa hashlib.sha256 → np.random.default_rng para garantizar determinismo total por texto"
  - "np.clip(sim_matrix, -1.0, 1.0) obligatorio antes de comparar con umbral para mitigar precisión float32 (T-02-09)"
  - "merge_group usa model_copy(update=...) de Pydantic v2 para garantizar inmutabilidad del Job canónico original"
metrics:
  duration: "262 segundos (~4 min 22 seg)"
  completed_date: "2026-05-22"
  tasks_completed: 2
  files_count: 5
---

# Phase 02 Plan 03: Motor de Deduplicación (embedder + exact + semantic + merger) Summary

**One-liner:** Módulos hoja del motor de dedup: Embedder Protocol con BgeM3Embedder lazy-load (anti-torch), FakeEmbedder determinista, exact_group por hash NFD, semantic_cluster greedy coseno con numpy E@E.T + clip, y merge_group con model_copy Pydantic v2.

## What Was Built

Cuatro módulos independientes que implementan el motor de deduplicación de ofertas de empleo (DEDUP-01..03), más el suite de tests unitarios completo con invariante anti-torch.

### app/dedup/embedder.py
- `Embedder` Protocol: interfaz `embed(texts) -> np.ndarray` float32 L2-normalizado.
- `BgeM3Embedder`: lazy import de `sentence_transformers` SOLO dentro de `_ensure_loaded()` con `# noqa: PLC0415`. El modelo BAAI/bge-m3 se carga en primera llamada real, nunca en import.
- `FakeEmbedder`: resolución por prioridad (dict mapeado → default_vector → hash SHA-256 determinista). Sin red, sin torch.

### app/dedup/exact.py
- `exact_group(jobs)`: agrupa por `normalize_field(company) + "|" + normalize_field(title)` usando `defaultdict`. Resiliente a variantes de capitalización y acentos.

### app/dedup/semantic.py
- `build_embed_text(job, desc_words=50)`: `f"{title} {company} {snippet}".strip()` — degrada graciosamente con descripción vacía.
- `semantic_cluster(jobs, embedder, umbral=0.85)`: clustering greedy con `E @ E.T` (coseno por dot sobre vectores L2-norm) + `np.clip` obligatorio para mitigar precisión float32.

### app/dedup/merger.py
- `merge_group(group)`: caso trivial (1 job → return as-is); canónica = `max(group, key=lambda j: len(j.description))`; URLs alternativas acumuladas via `canonical.model_copy(update={"urls_alternativas": ...})`. No muta el original.

### tests/dedup/test_dedup_units.py
31 tests en 5 secciones:
1. Invariante lazy-import (anti-torch): `import app.dedup.embedder` y `import app.dedup.semantic` no introducen torch en `sys.modules`.
2. FakeEmbedder: shape, vector constante, vector mapeado, determinismo por hash, lista vacía.
3. exact_group: duplicados exactos, sin duplicados, normalización de acentos, lista vacía, un solo job.
4. build_embed_text + semantic_cluster: texto completo/vacío/corto, cluster único (idénticos), cluster individual (ortogonales), lista vacía, cobertura de índices.
5. merge_group: 1 job, descripción más larga, urls_alternativas acumuladas, URL canónica no duplicada, no-mutación, 3 jobs + None URL.

## Commits

| Commit | Type | Description |
|--------|------|-------------|
| 05611a6 | test | RED: failing tests para embedder + exact + semantic + merger |
| 704002a | feat | GREEN: implementación de los 4 módulos hoja |

## TDD Gate Compliance

- RED commit (05611a6): `test(02-03)` — suite en rojo (ModuleNotFoundError + fallos de importación).
- GREEN commit (704002a): `feat(02-03)` — 31/31 tests verdes; 78/78 suite completa.
- No REFACTOR commit necesario: el código es limpio, con docstrings completos y sin duplicación.

## Deviations from Plan

### Auto-fixed Issues

None — el plan se ejecutó exactamente como estaba especificado.

Notas sobre decisiones de implementación menores:
- `FakeEmbedder.__init__` acepta `dim=4` como parámetro (ya especificado en el plan), plus `default_vector` como argumento explícito para el caso de vector constante. Esto ya estaba en RESEARCH.md Pattern 1.
- `merge_group` lanza `ValueError` si recibe grupo vacío (defensive programming, Rule 2 — error handling). El plan no lo especificaba explícitamente pero es correcto.
- `grep -c "noqa: PLC0415"` devuelve 3 en lugar de 1 porque el comentario aparece en el docstring del método además del import. El criterio es "≥ 1", que se cumple con el import real en la línea 77.

## Verification Results

```
uv run pytest tests/dedup/test_dedup_units.py  → 31 passed
uv run pytest                                  → 78 passed (full suite)
```

Acceptance criteria:
- `grep -c "class Embedder\|class BgeM3Embedder\|class FakeEmbedder" app/dedup/embedder.py` → 3 ✓
- Import de sentence_transformers solo en líneas indentadas (línea 77, dentro de `_ensure_loaded`) ✓
- `grep -c "noqa: PLC0415" app/dedup/embedder.py` → 3 (≥ 1) ✓
- `grep -c "normalize_embeddings=True" app/dedup/embedder.py` → 1 ✓
- `uv run python -c "import app.dedup.embedder; assert 'torch' not in sys.modules"` → PASSED ✓
- `grep -c "def exact_group" app/dedup/exact.py` → 1 ✓
- `grep -c "def semantic_cluster\|def build_embed_text" app/dedup/semantic.py` → 2 ✓
- `grep -c "@ embeddings.T\|np.clip" app/dedup/semantic.py` → 3 (≥ 2) ✓
- `grep -c "def merge_group" app/dedup/merger.py` → 1 ✓
- `grep -c "model_copy" app/dedup/merger.py` → 5 (≥ 1) ✓
- `uv run python -c "import app.dedup.semantic; assert 'torch' not in sys.modules"` → PASSED ✓

## Known Stubs

None — todos los módulos están completamente implementados y funcionales.

## Threat Flags

Ninguna nueva superficie de red ni endpoints introducidos en este plan. Las mitigaciones del threat model se implementaron:

| Threat ID | Mitigación aplicada |
|-----------|---------------------|
| T-02-07 | Lazy import verificado con test de invariante: `import app.dedup.embedder` no introduce torch |
| T-02-08 | BgeM3Embedder solo carga en `_ensure_loaded()`; tests usan FakeEmbedder |
| T-02-09 | `np.clip(sim_matrix, -1.0, 1.0, out=sim_matrix)` aplicado antes de comparar con umbral |

## Self-Check: PASSED
