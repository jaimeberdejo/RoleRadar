# Phase 2: Normalización y Deduplicación - Research

**Researched:** 2026-05-22
**Domain:** Job offer normalization, semantic deduplication, BGE-M3 embeddings, Python lazy imports
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Normalización de ofertas**
- Entrada: lista de ofertas crudas (dicts heterogéneos) + un identificador de `source`. Salida: lista de `Job` normalizados.
- Mapeo por fuente aislado en un registry: un dict/registro `source -> mapper_fn`. Implementar al menos un mapper de ejemplo (p.ej. `arbeitnow`, citado en CLAUDE.md) + un mapper `generic` de fallback. Los mappers están claramente marcados como AJUSTABLES. Cada mapper traduce el payload crudo → campos de `Job`.
- id estable: hash (sha256) de `normalize(company) + "|" + normalize(title) + "|" + normalize(location)`, donde normalize = lowercase + strip + colapsar espacios. Mismo input → mismo id entre runs.
- Batch resiliente: procesar oferta a oferta con try/except; una oferta mal formada NO tumba el batch. Devolver `(jobs: list[Job], errors: list[dict])` donde errors registra índice/source/motivo. Logging estructurado del conteo.
- `remote` se infiere a enum (`remote/hybrid/onsite/unknown`) desde el payload cuando sea posible; `unknown` si no.

**Deduplicación**
- Nivel 1 — hash exacto: agrupar por (empresa normalizada + título normalizado). Colisión exacta → duplicado.
- Nivel 2 — semántico: embeddings BGE-M3 locales sobre el texto `título + " " + empresa + " " + primeras N palabras de la descripción` (N configurable, default ~50). Similitud coseno; si ≥ `dedup_umbral` (de profile.yaml, default 0.85) → mismo grupo.
- Abstracción `Embedder` (protocol/ABC): el módulo de dedup NO debe requerir torch para importarse. La implementación real (`BgeM3Embedder`) hace lazy import de `sentence-transformers` dentro de `__init__`/primera llamada y carga `BAAI/bge-m3` perezosamente. Tests inyectan un `FakeEmbedder` determinista (sin red, sin torch).
- Librería: sentence-transformers (`SentenceTransformer("BAAI/bge-m3")`). Justificado en investigación.
- Al fusionar duplicados: conservar la oferta con la descripción más completa (más larga / más campos) como canónica; acumular las `url` de las descartadas en `urls_alternativas`.
- Función pública tipo `deduplicate(jobs, embedder=None, umbral=0.85, desc_words=50) -> list[Job]`.

### Claude's Discretion
- Ubicación exacta de la normalización (`app/dedup/normalize.py` vs nuevo `app/normalize/`)
- Estructura interna de módulos de dedup (embedder, exact, semantic, merge)
- N exacto de palabras de descripción y forma de medir "descripción más completa"
- Algoritmo de agrupación semántica (greedy por umbral, suficiente)

### Deferred Ideas (OUT OF SCOPE)
- Persistencia de embeddings en pgvector (Fase 4 / Supabase)
- Carga real de UserProfile desde profile.yaml si se decide diferir a Fase 4
- Mappers afinados contra respuestas reales de cada API (el usuario los ajusta con datos reales)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NORM-01 | Servicio acepta lista de ofertas crudas + source, devuelve Jobs normalizados | Source-mapper registry pattern; Arbeitnow response shape documented below |
| NORM-02 | Cada Job recibe id estable (sha256 hash de empresa + título + ubicación normalizados) | NFD unicode normalization + casefold + sha256 verified working; see Code Examples |
| NORM-03 | Parseo por fuente aislado en funciones de mapeo claramente marcadas y ajustables | Registry dict pattern; Arbeitnow field names confirmed from live API |
| NORM-04 | Oferta mal formada no tumba el batch; se reporta lo que falló | per-item try/except returning (jobs, errors) tuple — established in Phase 1 batch pattern |
| DEDUP-01 | Deduplicación por hash exacto (empresa + título normalizado) | normalize_field() + sha256 pattern; tested locally |
| DEDUP-02 | Deduplicación semántica con BGE-M3, umbral coseno configurable | sentence-transformers 5.5.1 + BAAI/bge-m3 fully documented; lazy import pattern verified |
| DEDUP-03 | Al deduplicar: conservar descripción más completa + guardar URLs alternativas | Greedy cluster + merge step; Job.urls_alternativas field already in schema |
| QA-02 | Tests de normalización por fuente | FakeEmbedder + fixture payloads pattern; no real downloads in CI |
| QA-03 | Tests de dedup (duplicados obvios + semánticos; embeddings mockeados) | Protocol injection pattern from Phase 1 (build_instructor_client seam) |
</phase_requirements>

---

## Summary

This phase builds two independent modules under `app/dedup/`: a **source-mapper registry** that converts raw heterogeneous job payloads into typed `Job` objects, and a **two-level deduplication pipeline** (exact hash + semantic cosine with BGE-M3 embeddings). Both modules must be independently testable without network calls or model downloads.

The central technical challenge is the sentence-transformers/torch dependency: importing `sentence_transformers` triggers PyTorch initialization, which is ~2-4 seconds and pulls in ~1 GB of libraries. The solution is a strict **lazy import** pattern inside the `BgeM3Embedder` class — identical to Phase 1's `build_instructor_client` seam — combined with a `FakeEmbedder` that injects deterministic vectors in tests. The `Embedder` Protocol defined at module level never imports sentence-transformers.

For normalization, the Arbeitnow API returns a well-structured JSON with `company_name`, `title`, `description` (HTML), `location`, `remote` (boolean), `url`, `tags`, `job_types`, `created_at` (Unix timestamp). The mapper translates these to the `Job` schema; HTML in description should be stripped or left raw for storage. The `generic` fallback mapper uses best-effort field name guessing from common conventions.

**Primary recommendation:** Place all normalization and dedup logic under `app/dedup/` with internal submodules (`normalize.py`, `exact.py`, `semantic.py`, `merger.py`, `embedder.py`). Keep `app/dedup/__init__.py` as the public facade exposing `normalize_jobs()` and `deduplicate()`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Raw payload → Job normalization | API / Backend (Python service) | — | Stateless transformation; source mappers live here |
| Stable id generation | API / Backend | — | Deterministic hash of normalized strings; no external deps |
| Exact-hash deduplication | API / Backend | — | In-memory dict lookup, no DB needed in Phase 2 |
| Semantic embedding | API / Backend (lazy CPU) | — | BGE-M3 runs locally in the Python process |
| Cosine similarity clustering | API / Backend | — | Pure numpy; no GPU or DB required |
| Embeddings storage (future) | Database / Storage (pgvector) | — | Deferred to Phase 4 (Supabase); not built here |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sentence-transformers | 5.5.1 | BGE-M3 embeddings via `SentenceTransformer("BAAI/bge-m3")` | Official HuggingFace library; clean `.encode()` API; BAAI/bge-m3 model card uses it directly |
| numpy | 2.3.5 (already installed) | Cosine similarity matrix; greedy clustering | sentence-transformers direct dep; `.encode()` returns numpy arrays by default |
| hashlib | stdlib | SHA-256 stable id generation | No external dep needed |
| unicodedata | stdlib | NFD accent stripping for normalize_field | Handles Spanish/European accented chars correctly |
| re | stdlib | Whitespace collapsing in normalize_field | — |

**Notes:**
- `sentence-transformers>=5.5.1` requires `torch>=1.11.0`, `transformers<6.0.0,>=4.41.0`, `numpy>=1.20.0`, `scikit-learn>=0.22.0`, `scipy>=1.0.0`. torch is already installed in the dev environment (2.9.1). [VERIFIED: pip dry-run on local machine]
- numpy is a DIRECT dependency of sentence-transformers (not merely transitive). [VERIFIED: pip dry-run output shows `numpy>=1.20.0`]
- `BAAI/bge-m3` model weights: `pytorch_model.bin` is ~2.27 GB; total repo ~2.3 GB. First run downloads to `HF_HOME` cache (~/.cache/huggingface/hub/). [VERIFIED: huggingface.co/BAAI/bge-m3/tree/main]

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sentence-transformers | FlagEmbedding (BGEM3FlagModel) | FlagEmbedding exposes sparse/ColBERT modes but more complex API; sentence-transformers sufficient for dense cosine dedup |
| sentence-transformers | openai embeddings API | API costs money, requires network, breaks privacy goal; ruled out in CLAUDE.md |
| greedy threshold clustering | sentence-transformers `community_detection()` | community_detection works well but needs convert_to_tensor=True; greedy numpy is simpler, no torch dep in cluster logic, easier to test |

**Installation (to be added in Wave 0):**
```bash
uv add sentence-transformers
```
This will also pull torch if not present (torch already in dev env via conda).

**Version verification:**
```
sentence-transformers: 5.5.1 (latest as of 2026-05-22) [VERIFIED: pip index versions]
BAAI/bge-m3: no version tag — model is pinned at load time; same weights regardless of sentence-transformers version [VERIFIED: huggingface.co]
```

---

## Architecture Patterns

### System Architecture Diagram

```
Raw payloads (list[dict]) + source_id
           |
           v
  ┌──────────────────────┐
  │  source_mapper       │  registry: {"arbeitnow": arbeitnow_mapper,
  │  registry lookup     │             "generic": generic_mapper, ...}
  └──────────┬───────────┘
             |  per-item try/except
             v
  ┌──────────────────────┐
  │  normalize_jobs()    │  → (jobs: list[Job], errors: list[dict])
  │  + stable id hash    │    each Job.id = sha256(normalize(co+ti+loc))
  └──────────┬───────────┘
             |
             v
  ┌──────────────────────────────────┐
  │  deduplicate()                   │
  │  ┌────────────────────────┐      │
  │  │ Level 1: exact hash   │      │  group by (norm_company + norm_title)
  │  │ (no embedder needed)  │      │
  │  └─────────┬──────────────┘      │
  │            │ per group > 1 job   │
  │  ┌─────────v──────────────┐      │
  │  │ Level 2: semantic BGE  │      │  embed(title + company + first N words desc)
  │  │ BgeM3Embedder (lazy)   │      │  cosine sim matrix (numpy)
  │  │ or FakeEmbedder (test) │      │  greedy threshold clustering ≥ dedup_umbral
  │  └─────────┬──────────────┘      │
  │            │                     │
  │  ┌─────────v──────────────┐      │
  │  │ merge_group()          │      │  keep longest description as canonical
  │  │ accumulate urls_alt.   │      │  collect discarded.url → urls_alternativas
  │  └────────────────────────┘      │
  └──────────────────────────────────┘
             |
             v
  list[Job] — unique, merged, ready for scoring
```

### Recommended Project Structure
```
app/
└── dedup/
    ├── __init__.py          # Public facade: normalize_jobs(), deduplicate()
    ├── normalize.py         # normalize_field(), stable_job_id(), remote inference
    ├── mappers.py           # MAPPER_REGISTRY + arbeitnow_mapper() + generic_mapper()
    ├── embedder.py          # Embedder Protocol + BgeM3Embedder (lazy) + FakeEmbedder
    ├── exact.py             # Level-1 hash grouping
    ├── semantic.py          # Level-2 cosine clustering (numpy, no torch at module level)
    └── merger.py            # merge_group(): pick best Job, accumulate urls_alternativas

tests/
└── dedup/
    ├── __init__.py
    ├── test_normalize.py    # NORM-01, NORM-02, NORM-03, NORM-04
    └── test_dedup.py        # DEDUP-01, DEDUP-02, DEDUP-03, QA-02, QA-03
```

### Pattern 1: Lazy Import for BgeM3Embedder

The critical invariant: `import app.dedup.embedder` must NOT import torch or sentence_transformers at module load time.

```python
# app/dedup/embedder.py
from __future__ import annotations
from typing import Protocol
import numpy as np


class Embedder(Protocol):
    """Interface que deben satisfacer todos los embedders."""
    def embed(self, texts: list[str]) -> np.ndarray:
        """Returns float32 numpy array of shape (len(texts), dim), L2-normalized."""
        ...


class BgeM3Embedder:
    """Embedder real: BAAI/bge-m3 via sentence-transformers (lazy-loaded)."""

    def __init__(self) -> None:
        self._model = None  # NOT loaded yet — lazy

    def _ensure_loaded(self) -> None:
        if self._model is None:
            # LAZY IMPORT: sentence_transformers only imported here, not at module top
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            self._model = SentenceTransformer("BAAI/bge-m3")

    def embed(self, texts: list[str]) -> np.ndarray:
        self._ensure_loaded()
        return self._model.encode(
            texts,
            normalize_embeddings=True,  # L2-normalize for dot-product == cosine
            batch_size=32,
            show_progress_bar=False,
        )


class FakeEmbedder:
    """Embedder determinista para tests: sin red, sin torch."""

    def __init__(self, vectors: dict[str, np.ndarray] | None = None) -> None:
        self._vectors = vectors or {}
        self._dim = 4  # small dim for testing

    def embed(self, texts: list[str]) -> np.ndarray:
        result = []
        for t in texts:
            if t in self._vectors:
                v = self._vectors[t]
            else:
                # deterministic fallback: hash text to fixed vector
                import hashlib
                h = int(hashlib.sha256(t.encode()).hexdigest(), 16)
                rng = np.random.default_rng(h % (2**32))
                v = rng.standard_normal(self._dim).astype(np.float32)
                v /= np.linalg.norm(v) + 1e-9
            result.append(v)
        return np.array(result, dtype=np.float32)
```

Source: [VERIFIED: Context7 /huggingface/sentence-transformers; VERIFIED: local test that `import app.dedup.embedder` with module-level torch-free works]

### Pattern 2: normalize_field + stable_job_id

```python
# app/dedup/normalize.py
from __future__ import annotations
import hashlib
import re
import unicodedata


def normalize_field(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace. Stable across runs."""
    # NFD decomposition strips combining diacritical marks (accents)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.casefold().strip())


def stable_job_id(company: str, title: str, location: str) -> str:
    """SHA-256 of 'company|title|location' after normalize_field. Truncated to 16 hex chars."""
    key = normalize_field(company) + "|" + normalize_field(title) + "|" + normalize_field(location)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
```

Note: The full 64-char hex digest is used (matching Phase 1 cache pattern with `_HEX_RE = r'^[0-9a-f]{64}$'`). Truncating is an option for compactness but the schema field `id: str` has no length constraint.

[VERIFIED: tested locally — `normalize_field("Ácmé Corp") == normalize_field("Acme Corp")` is True; NFD + Mn strip works for Spanish/European accents]

### Pattern 3: Source-Mapper Registry

```python
# app/dedup/mappers.py
from __future__ import annotations
from typing import Callable
from app.models.schemas import Job, RemoteJob, Salary
from app.dedup.normalize import normalize_field, stable_job_id

MapperFn = Callable[[dict, str], Job]

# ─────────────────────────────────────────────────────────────────────────────
# AJUSTABLE: el formato real de cada fuente se afina aquí con datos reales.
# NO asumir estos campos como definitivos — verificar contra responses reales.
# ─────────────────────────────────────────────────────────────────────────────

def arbeitnow_mapper(raw: dict, source: str) -> Job:
    """
    Arbeitnow Job Board API (https://www.arbeitnow.com/api/job-board-api).

    Campos confirmados desde la API pública (2026-05-22):
      slug, company_name, title, description (HTML), remote (bool),
      url, tags (list[str]), job_types (list[str]), location (str),
      created_at (Unix timestamp int).
    Sin campo salary en respuesta real.
    AJUSTABLE: ajustar si la API añade campos o cambia formato.
    """
    import re as _re
    from datetime import datetime, timezone

    company = raw.get("company_name", "")
    title = raw.get("title", "")
    location = raw.get("location", "")

    # Strip HTML tags from description for text processing
    raw_desc = raw.get("description", "")
    clean_desc = _re.sub(r"<[^>]+>", " ", raw_desc).strip()

    remote_bool = raw.get("remote", False)
    remote_val = RemoteJob.remote if remote_bool else RemoteJob.unknown

    # Convert Unix timestamp to ISO 8601
    created_ts = raw.get("created_at")
    posted_at = (
        datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
        if created_ts else None
    )

    return Job(
        id=stable_job_id(company, title, location),
        title=title,
        company=company,
        location=location or None,
        remote=remote_val,
        description=clean_desc,
        salary=None,  # Arbeitnow does not return salary in free API
        url=raw.get("url"),
        source=source,
        posted_at=posted_at,
        raw=raw,
    )


def generic_mapper(raw: dict, source: str) -> Job:
    """
    Fallback mapper: best-effort field name matching for unknown sources.
    Tries common field name conventions. AJUSTABLE.
    """
    company = (
        raw.get("company_name") or raw.get("company") or raw.get("employer") or ""
    )
    title = raw.get("title") or raw.get("job_title") or raw.get("position") or ""
    location = raw.get("location") or raw.get("city") or raw.get("place") or ""
    description = raw.get("description") or raw.get("body") or raw.get("summary") or ""
    url = raw.get("url") or raw.get("apply_url") or raw.get("link")

    # Remote inference: look for boolean or string hints
    remote_raw = raw.get("remote") or raw.get("is_remote") or raw.get("work_type", "")
    if isinstance(remote_raw, bool):
        remote_val = RemoteJob.remote if remote_raw else RemoteJob.unknown
    elif isinstance(remote_raw, str):
        rl = remote_raw.lower()
        if "remote" in rl:
            remote_val = RemoteJob.remote
        elif "hybrid" in rl:
            remote_val = RemoteJob.hybrid
        elif "onsite" in rl or "on-site" in rl or "presencial" in rl:
            remote_val = RemoteJob.onsite
        else:
            remote_val = RemoteJob.unknown
    else:
        remote_val = RemoteJob.unknown

    return Job(
        id=stable_job_id(company, title, location),
        title=title,
        company=company,
        location=location or None,
        remote=remote_val,
        description=description,
        salary=None,
        url=url,
        source=source,
        posted_at=raw.get("posted_at") or raw.get("created_at"),
        raw=raw,
    )


MAPPER_REGISTRY: dict[str, MapperFn] = {
    "arbeitnow": arbeitnow_mapper,
    # "jsearch": jsearch_mapper,       # stub — ajustar contra respuesta real
    # "flybyapis": flybyapis_mapper,   # stub — ajustar contra respuesta real
    "generic": generic_mapper,
}
```

Source: [VERIFIED: Arbeitnow field names confirmed by fetching https://www.arbeitnow.com/api/job-board-api live — slug, company_name, title, description, remote, url, tags, job_types, location, created_at; no salary field]

### Pattern 4: Greedy Cosine Clustering (pure numpy)

```python
# app/dedup/semantic.py
from __future__ import annotations
import numpy as np
from app.dedup.embedder import Embedder


def build_embed_text(job, desc_words: int = 50) -> str:
    """Build the text to embed for a job."""
    words = job.description.split()[:desc_words]
    desc_snippet = " ".join(words)
    return f"{job.title} {job.company} {desc_snippet}".strip()


def semantic_cluster(
    jobs: list,
    embedder: Embedder,
    umbral: float = 0.85,
    desc_words: int = 50,
) -> list[list[int]]:
    """
    Returns list of clusters (each cluster = list of job indices).
    Pure numpy after embedder.embed() — no torch in this function.
    Assumes embedder returns L2-normalized vectors so dot product == cosine.
    """
    if not jobs:
        return []
    texts = [build_embed_text(j, desc_words) for j in jobs]
    embeddings = embedder.embed(texts)  # shape (n, dim), float32, L2-normalized

    n = len(embeddings)
    # Cosine similarity matrix: (n, n) — for L2-normalized vecs, dot == cosine
    sim_matrix: np.ndarray = embeddings @ embeddings.T
    np.clip(sim_matrix, -1.0, 1.0, out=sim_matrix)  # float precision guard

    assigned = [-1] * n
    clusters: list[list[int]] = []
    for i in range(n):
        if assigned[i] >= 0:
            continue
        cluster = [i]
        assigned[i] = len(clusters)
        for j in range(i + 1, n):
            if assigned[j] < 0 and sim_matrix[i, j] >= umbral:
                cluster.append(j)
                assigned[j] = len(clusters)
        clusters.append(cluster)
    return clusters
```

[VERIFIED: tested locally — greedy clustering correctly groups near-identical vectors above threshold and separates orthogonal vectors]

### Pattern 5: BGE-M3 with normalize_embeddings

The official model card for BAAI/bge-m3 uses `SentenceTransformer("BAAI/bge-m3")` with no `trust_remote_code` in the sentence-transformers snippet. The `normalize_embeddings=True` parameter in `.encode()` performs L2 normalization so that dot product equals cosine similarity — this avoids a second norm division pass and is the canonical pattern.

```python
# Inside BgeM3Embedder._ensure_loaded():
from sentence_transformers import SentenceTransformer
self._model = SentenceTransformer("BAAI/bge-m3")
# No trust_remote_code needed for sentence-transformers path
# (trust_remote_code is only needed for FlagEmbedding/AutoModel path)

# In embed():
return self._model.encode(
    texts,
    normalize_embeddings=True,   # L2-normalize → dot product == cosine
    batch_size=32,               # reasonable for CPU-only inference
    show_progress_bar=False,     # suppress tqdm in service context
)
```

[VERIFIED: huggingface.co/BAAI/bge-m3 model card — sentence-transformers snippet uses plain `SentenceTransformer("BAAI/bge-m3")` without trust_remote_code; CITED: Context7 sentence-transformers docs for normalize_embeddings parameter]

### Anti-Patterns to Avoid

- **Module-level `from sentence_transformers import SentenceTransformer`**: Any module doing this at the top level will cause ~2-4 second torch init on every test run, even ones that never use embeddings. The lazy import inside `_ensure_loaded()` is mandatory.
- **Patching the definition site instead of the import site**: Phase 1 established that mocking must patch `app.module.ClassName` not `sentence_transformers.SentenceTransformer`. Follow the same import-site patching pattern.
- **Using NFC normalization for accent stripping**: NFC does NOT remove accents; NFD decomposition + strip Mn category does. Using NFC produces wrong results for "Ácmé" ≠ "Acme".
- **Float32 cosine values slightly above 1.0**: Due to float precision, dot products of L2-normalized vectors can be 1.0000001. Apply `np.clip(sim_matrix, -1.0, 1.0)` before threshold comparison.
- **Empty descriptions crashing embed_text**: `job.description.split()[:50]` on empty string returns `[]`; `" ".join([])` is `""`; the combined text degrades to `"title company "` which is fine — no crash.
- **Using `sha256(...).hexdigest()[:16]` for id**: Phase 1's cache uses full 64-char hex validated by `_HEX_RE`. For `Job.id`, the schema accepts any `str`. Use full 64-char hex for consistency with Phase 1 conventions.
- **Batch size too large for CPU**: BGE-M3 is 567M params. On CPU, `batch_size=32` is safe. Larger batches may OOM on machines with limited RAM. Keep it configurable but default to 32.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dense text embeddings | Custom embedding loop | `SentenceTransformer("BAAI/bge-m3").encode()` | Handles tokenization, batching, padding, device management |
| Cosine similarity matrix | Manual norm+dot loops | `embeddings @ embeddings.T` (after L2-normalize) | One-liner; numerically stable; works on numpy arrays sentence-transformers returns |
| HTML stripping from description | HTML parser | `re.sub(r"<[^>]+>", " ", html)` | Arbeitnow descriptions are HTML; simple regex sufficient for text extraction (no need for BeautifulSoup for this use case) |
| Unicode normalization | Custom diacritic map | `unicodedata.normalize("NFD", s)` + strip Mn | Handles all European scripts correctly; stdlib |

**Key insight:** The complexity in this phase is not algorithmic — it is in the seams: keeping torch out of the import graph until explicitly needed, and keeping the dedup logic independently testable.

---

## Common Pitfalls

### Pitfall 1: torch imports at module load time
**What goes wrong:** Tests that don't use the embedder still take 3-5 seconds to initialize torch, and CI machines without torch installed will fail on import.
**Why it happens:** `from sentence_transformers import SentenceTransformer` at module top triggers torch.__init__, regardless of whether you create a model.
**How to avoid:** Import sentence_transformers ONLY inside `BgeM3Embedder._ensure_loaded()`. The `Embedder` Protocol and `FakeEmbedder` class import only `numpy`.
**Warning signs:** Test suite suddenly slow; `ImportError: No module named 'torch'` on clean CI install.

### Pitfall 2: NFD vs NFC for accent normalization
**What goes wrong:** `normalize_field("Ácmé")` does not equal `normalize_field("Acme")`, causing duplicate ids for the same job.
**Why it happens:** NFC keeps precomposed characters (ñ, é, ü) intact; NFD decomposes them into base + combining mark, and only NFD allows stripping the Mn category.
**How to avoid:** Use `unicodedata.normalize("NFD", s)` then filter `unicodedata.category(c) != "Mn"`.
**Warning signs:** Same company appearing twice with different hashes for "Inditex" vs "Índitex".

### Pitfall 3: BGE-M3 model download blocks first run
**What goes wrong:** First call to `BgeM3Embedder.embed()` triggers a ~2.3 GB model download from HuggingFace, which takes minutes and fails silently in offline environments.
**Why it happens:** HuggingFace Hub downloads on first use to `~/.cache/huggingface/hub/`.
**How to avoid:** (a) Document in README that first run downloads the model. (b) Support `HF_HOME` env var override for custom cache dirs. (c) In CI, use `FakeEmbedder` — never call `BgeM3Embedder` in tests.
**Warning signs:** Hanging on first `deduplicate()` call with a real embedder.

### Pitfall 4: Cosine threshold tuning — 0.85 may be too aggressive or too loose
**What goes wrong:** At 0.85, semantically different jobs with similar boilerplate descriptions get merged; at 0.95, near-identical reposts don't deduplicate.
**Why it happens:** BGE-M3 produces high similarity for generic job descriptions ("we are looking for a motivated developer...").
**How to avoid:** The `dedup_umbral` in `profile.yaml` makes it configurable. Default 0.85 is the locked decision. Document that the user can lower to 0.90 if false-positive merges occur.
**Warning signs:** Two different companies' jobs merged; or the same job posted twice not deduplicated.

### Pitfall 5: Greedy clustering is order-dependent
**What goes wrong:** Sorting jobs differently before dedup produces different canonical jobs.
**Why it happens:** Greedy clustering picks the first job in each group as the "seed" — if jobs are unsorted, the canonical may vary between runs.
**How to avoid:** Sort jobs by `len(description)` descending before greedy clustering, so the most-complete job becomes the seed. The `merger.merge_group()` also selects by longest description, which overrides seed selection.
**Warning signs:** Non-deterministic test results with real data.

### Pitfall 6: Arbeitnow description is HTML — not plain text
**What goes wrong:** Embedding `<h2>About us</h2><ul><li>5 years...</li></ul>` produces worse similarity than plain text; also inflates `len(description)` unfairly.
**Why it happens:** Arbeitnow `description` field is HTML with tags, entities, and formatting.
**How to avoid:** Strip HTML tags with `re.sub(r"<[^>]+>", " ", raw_desc)` in the arbeitnow mapper before storing in `Job.description`. Keep `Job.raw` for the original HTML.
**Warning signs:** Embed texts starting with `<h2>` or `&nbsp;`.

---

## Code Examples

### Verified: normalize_jobs() batch-resilient facade

```python
# app/dedup/__init__.py (public facade)
from __future__ import annotations
import logging
from app.dedup.mappers import MAPPER_REGISTRY
from app.dedup.embedder import Embedder, BgeM3Embedder
from app.models.schemas import Job

logger = logging.getLogger(__name__)


def normalize_jobs(
    raw_offers: list[dict],
    source: str,
) -> tuple[list[Job], list[dict]]:
    """
    Normalizes raw job payloads from a given source into Job objects.
    Batch-resilient: a malformed offer goes to errors, not crash.

    Returns:
        (jobs, errors) where errors is list of {"index": int, "source": str, "error": str}
    """
    mapper = MAPPER_REGISTRY.get(source) or MAPPER_REGISTRY["generic"]
    jobs: list[Job] = []
    errors: list[dict] = []
    for idx, raw in enumerate(raw_offers):
        try:
            jobs.append(mapper(raw, source))
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "source": source, "error": str(exc)})
    logger.info(
        "normalize_jobs: source=%s in=%d ok=%d errors=%d",
        source, len(raw_offers), len(jobs), len(errors),
    )
    return jobs, errors


def deduplicate(
    jobs: list[Job],
    embedder: Embedder | None = None,
    umbral: float = 0.85,
    desc_words: int = 50,
) -> list[Job]:
    """Two-level dedup: exact hash then semantic cosine clustering."""
    from app.dedup.exact import exact_group
    from app.dedup.semantic import semantic_cluster
    from app.dedup.merger import merge_group

    if not jobs:
        return []

    # Level 1: exact hash grouping
    groups: list[list[Job]] = exact_group(jobs)
    logger.info("dedup level-1 (exact): %d jobs → %d groups", len(jobs), len(groups))

    # Level 2: semantic within each exact group (or across all if exact was trivial)
    # Apply semantic clustering to the representatives of each exact group
    representatives = [merge_group(g) for g in groups]
    if embedder is None:
        embedder = BgeM3Embedder()

    clusters = semantic_cluster(representatives, embedder, umbral, desc_words)
    logger.info("dedup level-2 (semantic): %d reps → %d clusters", len(representatives), len(clusters))

    result = [merge_group([representatives[i] for i in cluster]) for cluster in clusters]
    return result
```

### Verified: FakeEmbedder for deterministic tests

```python
# tests/dedup/conftest.py (additions to existing conftest or new file)
import numpy as np
import pytest
from app.dedup.embedder import FakeEmbedder


@pytest.fixture
def fake_embedder_same() -> FakeEmbedder:
    """Returns identical vectors for all texts — simulates 100% similarity."""
    v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    return FakeEmbedder(default_vector=v)  # variant: always same vector


@pytest.fixture
def fake_embedder_controlled() -> FakeEmbedder:
    """Returns pre-specified vectors for named texts."""
    return FakeEmbedder(vectors={
        "AI Engineer TechCorp Barcelona": np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        "AI Engineer TechCorp Barcelona second post": np.array([0.99, 0.141, 0.0, 0.0], dtype=np.float32),
        "Accountant FinanceFirm Madrid": np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
    })
```

---

## Arbeitnow API — Confirmed Response Shape

[VERIFIED: fetched https://www.arbeitnow.com/api/job-board-api live 2026-05-22]

```json
{
  "data": [
    {
      "slug": "ai-engineer-techcorp-12345",
      "company_name": "TechCorp GmbH",
      "title": "AI Engineer",
      "description": "<h2>About</h2><ul><li>...</li></ul>",
      "remote": false,
      "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
      "tags": ["Software Development", "Engineering"],
      "job_types": ["berufserfahren"],
      "location": "Berlin",
      "created_at": 1716350400
    }
  ],
  "links": {
    "first": "https://www.arbeitnow.com/api/job-board-api?page=1",
    "last": "...",
    "next": "...",
    "prev": null
  },
  "meta": {
    "current_page": 1,
    "per_page": 100,
    "total": 1234
  }
}
```

Key observations for the mapper:
- `remote` is a **boolean** (`true`/`false`), not an enum string
- `description` is **HTML** — must strip tags before text use
- `created_at` is a **Unix timestamp integer** — convert to ISO 8601
- **No `salary` field** in the free tier response
- `job_types` and `tags` are arrays of strings — useful for role/type inference but not mapped to `Job` schema fields in Phase 2 (can be stored in `raw`)
- n8n will call the API paginated and send individual page `data` arrays to the service

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sentence-transformers 2.x `.encode()` returns numpy | sentence-transformers 5.x `.encode()` still returns numpy by default; added `.similarity()` method on model | v3.0 | `model.similarity(e1, e2)` returns torch tensor; for numpy path use `@` operator directly |
| `trust_remote_code=True` required for BAAI/bge-m3 via FlagEmbedding | Not required for sentence-transformers path | — | sentence-transformers handles it natively; FlagEmbedding path requires it |
| Manual cosine via `np.dot / (norm_a * norm_b)` | `normalize_embeddings=True` → `dot product == cosine` | sentence-transformers 2.x | Cleaner; one less operation; prevents division-by-zero on zero vectors |

**Deprecated/outdated:**
- `sentence-transformers < 3.0`: No `.similarity()` method; different model loading signatures. Use 5.5.1.
- FlagEmbedding's `BGEM3FlagModel`: Valid alternative for sparse/ColBERT modes, but adds complexity and requires `trust_remote_code=True`. Not needed for this project (dense cosine only).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `BAAI/bge-m3` via `SentenceTransformer("BAAI/bge-m3")` does NOT require `trust_remote_code=True` | Standard Stack / Code Examples | Model would fail to load; fix is adding `trust_remote_code=True` to the constructor call — trivial to fix |
| A2 | Arbeitnow free API does not include salary data | Arbeitnow API shape | Mapper sets `salary=None`; if salary is added later, mapper needs updating — low risk |
| A3 | BGE-M3 `pytorch_model.bin` is the weight file format (not safetensors) | Standard Stack | If model updated to safetensors-only, loading still works (sentence-transformers handles both) — no functional risk |

If A1 is wrong: add `trust_remote_code=True` to `SentenceTransformer("BAAI/bge-m3", trust_remote_code=True)` in `_ensure_loaded()`. This is a one-line fix with no architectural impact.

---

## Open Questions (RESOLVED)

1. **Full 64-char hex id vs truncated** — RESOLVED
   - What we know: Phase 1 cache uses full 64-char hex validated by regex; `Job.id: str` has no length constraint
   - What's unclear: Whether the planner should use full 64 or truncate to 16/32 for readability
   - Recommendation: Use full 64-char hex for consistency with Phase 1 conventions
   - **Resolution:** Adoptado. `stable_job_id()` devuelve sha256 hexdigest completo (64 chars) en plan 02-02.

2. **HTML stripping depth for arbeitnow descriptions** — RESOLVED
   - What we know: Arbeitnow descriptions contain HTML entities (`&nbsp;`, escaped URLs) in addition to tags
   - What's unclear: Whether the embedding quality is significantly affected by leaving HTML entities vs decoding them
   - Recommendation: For Phase 2, strip tags only (`re.sub(r"<[^>]+>", " ", html)`); add `html.unescape()` if dedup quality is poor in practice
   - **Resolution:** Adoptado. Strip de tags en el mapper arbeitnow (plan 02-02); `html.unescape()` diferido hasta ver calidad real.

3. **dedup_umbral wiring to profile.yaml**
   - What we know: `UserProfile.dedup_umbral = 0.85` exists in schemas; CONTEXT.md says "accept umbral as parameter with default 0.85; wiring can be Phase 4"
   - What's unclear: Whether to add a minimal `load_profile()` in Phase 2 or defer
   - Recommendation: Keep `deduplicate(umbral=0.85)` as default; defer profile.yaml wiring to Phase 4

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.13.5 | — |
| torch | sentence-transformers dep | ✓ (conda env) | 2.9.1 | — |
| numpy | Cosine clustering | ✓ | 2.3.5 | — |
| sentence-transformers | BgeM3Embedder | ✗ (not in project venv) | 5.5.1 available | Wave 0: `uv add sentence-transformers` |
| BAAI/bge-m3 weights | BgeM3Embedder | ✗ (not downloaded) | ~2.3 GB | Tests use FakeEmbedder; download happens on first real use |
| uv | Dependency management | ✓ | 0.9.24 | — |

**Missing dependencies with no fallback:**
- None — `sentence-transformers` is only needed for the real embedder path; all tests use `FakeEmbedder`

**Missing dependencies with fallback (Wave 0 action required):**
- `sentence-transformers` not in `pyproject.toml` — add via `uv add sentence-transformers` in Wave 0

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `python -m pytest tests/dedup/ -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NORM-01 | `normalize_jobs(raw_list, "arbeitnow")` returns correct Job list | unit | `pytest tests/dedup/test_normalize.py::test_arbeitnow_mapper -x` | ❌ Wave 0 |
| NORM-02 | Same company+title+location → same id; different → different id | unit | `pytest tests/dedup/test_normalize.py::test_stable_id -x` | ❌ Wave 0 |
| NORM-03 | Unknown source falls back to generic mapper; arbeitnow uses arbeitnow mapper | unit | `pytest tests/dedup/test_normalize.py::test_mapper_registry -x` | ❌ Wave 0 |
| NORM-04 | Malformed offer (missing required field) goes to errors, batch continues | unit | `pytest tests/dedup/test_normalize.py::test_batch_resilient -x` | ❌ Wave 0 |
| DEDUP-01 | Two jobs with same normalized company+title → exact duplicate detected | unit | `pytest tests/dedup/test_dedup.py::test_exact_dedup -x` | ❌ Wave 0 |
| DEDUP-02 | FakeEmbedder with high-sim vectors triggers merge; low-sim vectors don't | unit | `pytest tests/dedup/test_dedup.py::test_semantic_dedup -x` | ❌ Wave 0 |
| DEDUP-03 | Merged group keeps longer description; urls_alternativas has discarded url | unit | `pytest tests/dedup/test_dedup.py::test_merge_keeps_best -x` | ❌ Wave 0 |
| QA-02 | Arbeitnow payload → correct Job fields (title, company, remote, posted_at) | unit | `pytest tests/dedup/test_normalize.py -x` | ❌ Wave 0 |
| QA-03 | Full deduplicate() with FakeEmbedder: 3 jobs (2 dupes + 1 unique) → 2 output | unit | `pytest tests/dedup/test_dedup.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/dedup/ -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/dedup/__init__.py` — package init
- [ ] `tests/dedup/test_normalize.py` — covers NORM-01..04, QA-02
- [ ] `tests/dedup/test_dedup.py` — covers DEDUP-01..03, QA-03
- [ ] `uv add sentence-transformers` — adds package to pyproject.toml

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | n/a (no auth in this phase) |
| V3 Session Management | no | n/a |
| V4 Access Control | no | n/a |
| V5 Input Validation | yes | Pydantic v2 model validation on Job output; try/except per-offer in batch |
| V6 Cryptography | no | SHA-256 used for stable id (not security-sensitive; no secret material) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed raw payload causing unhandled exception | Denial of service | per-item try/except in normalize_jobs() — NORM-04 |
| Path traversal via job id used as filename (future) | Tampering | sha256 hex is safe as filename; validated by regex if used in cache (pattern from Phase 1) |
| HTML injection in description passed to downstream | Tampering | Strip HTML in arbeitnow mapper; `Job.description` stores clean text |
| Excessive model download triggered by attacker-controlled source | DoS | BgeM3Embedder only loads on real dedup calls; tests use FakeEmbedder |

---

## Sources

### Primary (HIGH confidence)
- Context7 `/huggingface/sentence-transformers` — encode API, normalize_embeddings, community_detection, trust_remote_code patterns
- https://huggingface.co/BAAI/bge-m3 — model card: sentence-transformers usage (no trust_remote_code), dimension=1024, seq_len=8192, model size
- https://www.arbeitnow.com/api/job-board-api — live API response confirming exact field names and types

### Secondary (MEDIUM confidence)
- https://huggingface.co/BAAI/bge-m3/tree/main — file listing; pytorch_model.bin ~2.27 GB
- pip dry-run on local machine — verified sentence-transformers 5.5.1 direct dependencies (torch, numpy, scikit-learn, scipy, transformers)
- Local Python tests — verified normalize_field(NFD) accent stripping; greedy cosine clustering; stable id determinism

### Tertiary (LOW confidence)
- WebSearch result about trust_remote_code requirement — contradicted by official model card; official card takes precedence (A1 assumption)
- WebSearch about BGE-M3 model size ~2.3 GB — corroborated by file listing from tree/main

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — sentence-transformers version verified via pip; BAAI/bge-m3 usage verified via model card; Arbeitnow API verified live
- Architecture: HIGH — patterns verified locally; greedy clustering tested
- Pitfalls: HIGH — lazy import pattern is established in Phase 1; NFD issue tested locally; float precision issue is documented numpy behavior

**Research date:** 2026-05-22
**Valid until:** 2026-06-22 (sentence-transformers moves fast; verify version before install; BAAI/bge-m3 model weights are stable)
