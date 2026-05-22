# Phase 2: Normalización y Deduplicación - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 10 new files + 1 modified
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/dedup/__init__.py` | service / facade | batch + transform | `app/cv/parser.py` | role-match (public facade over submodules) |
| `app/dedup/normalize.py` | utility | transform | `app/cv/cache.py` (sha256 + stdlib-only pattern) | role-match |
| `app/dedup/mappers.py` | utility | transform | `app/cv/llm_client.py` (injectable factory + Spanish naming) | role-match |
| `app/dedup/embedder.py` | service | transform | `app/cv/llm_client.py` (lazy-import + injectable seam) | **exact** |
| `app/dedup/exact.py` | utility | transform | `app/cv/cache.py` (dict keyed by sha256) | role-match |
| `app/dedup/semantic.py` | utility | transform | `app/cv/llm_client.py` (injectable dependency, pure function body) | role-match |
| `app/dedup/merger.py` | utility | transform | `app/cv/parser.py` (orchestration logic, no external deps) | role-match |
| `tests/dedup/__init__.py` | test | — | `tests/cv/__init__.py` | exact (empty file) |
| `tests/dedup/test_normalize.py` | test | — | `tests/cv/test_llm_client.py` (pure-function tests, no mocks) | role-match |
| `tests/dedup/test_dedup.py` | test | — | `tests/cv/test_parser.py` (injection/patch pattern, monkeypatch) | **exact** |
| `tests/conftest.py` (modified) | test fixture | — | `tests/conftest.py` (session + function fixtures, MagicMock) | **exact** |

---

## Pattern Assignments

### `app/dedup/__init__.py` (service facade, batch + transform)

**Analog:** `app/cv/parser.py`

The facade pattern: thin public module that imports ONLY from its own submodules and exposes the phase's two public functions. No logic lives here beyond orchestration.

**Module docstring pattern** (`app/cv/parser.py` lines 1–13):
```python
"""
Orquestador público de parseo de CV.

Implementa la interfaz pública `parse_cv(pdf_bytes) -> CVProfile` que:
  1. Comprueba la caché por sha256 del contenido del PDF (CV-03).
  2. Si hay hit: devuelve el CVProfile cacheado sin invocar el LLM.
  3. Si no hay hit: extrae texto con pymupdf → llama al LLM (instructor) →
     guarda en caché → devuelve el CVProfile.

Este módulo es el único punto de entrada para consumidores externos (n8n,
endpoints FastAPI). Importa exclusivamente vía los módulos hoja ya construidos
(extractor, cache, llm_client) para mantener responsabilidades separadas.
"""
from __future__ import annotations
```

**Imports pattern** (`app/cv/parser.py` lines 16–19): imports from own submodules only, never from external libraries:
```python
from app.cv.cache import load_cached_profile, pdf_hash, save_cached_profile
from app.cv.extractor import extract_text_from_pdf
from app.cv.llm_client import build_instructor_client, extract_cv_profile
from app.models.schemas import CVProfile
```

**Orchestration body with deferred submodule imports** — for `deduplicate()`, inner imports inside the function body prevent circular imports and keep module-level import graph clean (same reason as lazy import; established in RESEARCH.md facade snippet):
```python
def deduplicate(jobs, embedder=None, umbral=0.85, desc_words=50):
    from app.dedup.exact import exact_group        # inner import — no circular dep
    from app.dedup.semantic import semantic_cluster
    from app.dedup.merger import merge_group
    ...
```

**Logging pattern** (`app/cv/cache.py` line 22): module-level logger, structured messages with `%s` positional args (not f-strings):
```python
import logging
logger = logging.getLogger(__name__)

logger.info(
    "normalize_jobs: source=%s in=%d ok=%d errors=%d",
    source, len(raw_offers), len(jobs), len(errors),
)
```

---

### `app/dedup/normalize.py` (utility, transform)

**Analog:** `app/cv/cache.py`

Pure stdlib module — no external deps. Follows the same pattern of a standalone utility with a clear function contract, `from __future__ import annotations`, and `logging.getLogger(__name__)`.

**Module header pattern** (`app/cv/cache.py` lines 1–24):
```python
"""
Caché de CVProfile en disco, indexada por sha256 de los bytes del PDF.
...
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

from app.models.schemas import CVProfile

logger = logging.getLogger(__name__)

_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
```

**SHA-256 pattern** (`app/cv/cache.py` lines 45–54) — the exact same `hashlib.sha256(...).hexdigest()` pattern to replicate for `stable_job_id()`:
```python
def pdf_hash(pdf_bytes: bytes) -> str:
    """Calcula el sha256 hexadecimal de los bytes del PDF.

    Returns:
        Cadena hexadecimal de 64 caracteres (sha256 digest).
    """
    return hashlib.sha256(pdf_bytes).hexdigest()
```

**Full 64-char hex convention** (`app/cv/cache.py` line 24): Project uses full 64-char hex everywhere; `Job.id` must follow the same:
```python
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
```

**Adapt for `normalize_field()`:** Use `unicodedata` + `re` (stdlib). The RESEARCH.md code example is the definitive implementation — no analog exists for NFD accent stripping but the import style matches cache.py's stdlib-only imports.

---

### `app/dedup/mappers.py` (utility, transform)

**Analog:** `app/cv/llm_client.py`

Functions with injected/configurable dependencies; Spanish naming; clear docstrings marking adjustable parts. The function signature convention `fn(input, dependency) -> TypedOutput` is established.

**Function signature + docstring convention** (`app/cv/llm_client.py` lines 25–31):
```python
def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())


def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    """Llama al LLM para extraer un CVProfile estructurado del texto del CV.

    Args:
        raw_text: Texto plano extraído del PDF del CV.
        client:   Cliente instructor inyectado (real o mock).
    ...
    """
```

**Adapt for mappers:** Each mapper is `mapper_fn(raw: dict, source: str) -> Job`. The registry dict `MAPPER_REGISTRY: dict[str, MapperFn]` provides the injectable seam — tests can register a `FakeMapper` the same way tests inject `FakeEmbedder`.

**Type alias convention:** Use a `TypeAlias` for the mapper callable type (analogous to `instructor.Instructor` as the type in llm_client.py):
```python
from typing import Callable
MapperFn = Callable[[dict, str], Job]
MAPPER_REGISTRY: dict[str, MapperFn] = { ... }
```

---

### `app/dedup/embedder.py` (service, transform) — EXACT ANALOG

**Analog:** `app/cv/llm_client.py`

This is the most direct analog. `BgeM3Embedder` mirrors `build_instructor_client` exactly: the heavy external library (`sentence-transformers`/`torch`) is NEVER imported at module level; it is imported only inside the method that uses it. The injectable seam is the class instance itself (passed as parameter), exactly like `client: instructor.Instructor`.

**Lazy import pattern — THE critical invariant** (`app/cv/llm_client.py` lines 19–21, module-level vs function-level):
```python
# AT MODULE TOP — this IS imported at module level (instructor is already a dep):
import instructor
from anthropic import Anthropic
```

For `embedder.py` the equivalent is: `numpy` CAN be imported at module level (it is a direct dep of sentence-transformers and always available). `sentence_transformers` MUST NOT be imported at module level. The pattern:

```python
# app/dedup/embedder.py — module-level imports (safe, no torch):
from __future__ import annotations
from typing import Protocol
import numpy as np

# sentence_transformers is NEVER imported here — only inside _ensure_loaded()
```

**Injectable dependency seam** (`app/cv/llm_client.py` lines 30–31 + `app/cv/parser.py` lines 44–45):
```python
# In llm_client.py: client is an explicit parameter — caller provides it
def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    ...

# In parser.py: factory called once per parse_cv() invocation
client = build_instructor_client()
profile = extract_cv_profile(raw_text, client)
```

Replicate for dedup: `deduplicate(jobs, embedder=None, ...)` where `embedder=None` triggers `BgeM3Embedder()` lazily. Tests pass `FakeEmbedder()` directly.

**Mock surface for tests** (`tests/conftest.py` lines 67–77): The mock pattern is a `MagicMock` with `.return_value` set. For `FakeEmbedder` the pattern is a real class (not MagicMock) that satisfies the `Embedder` Protocol deterministically — see Shared Patterns section.

---

### `app/dedup/exact.py` (utility, transform)

**Analog:** `app/cv/cache.py`

Simple dict-keyed lookup; stdlib only; pure function returning a grouped result. Follows cache.py's pattern: function receives typed input, validates/groups it, returns typed output.

**Dict grouping pattern** (adapt from cache.py's `pdf_hash` + dict lookup style):
```python
# Equivalent of: cache_dir / f"{content_hash}.json" lookup
# becomes: groups dict keyed by (normalize_field(company) + "|" + normalize_field(title))
from collections import defaultdict
groups: dict[str, list[Job]] = defaultdict(list)
for job in jobs:
    key = normalize_field(job.company) + "|" + normalize_field(job.title)
    groups[key].append(job)
return list(groups.values())
```

**Import style** (`app/cv/cache.py` lines 11–19): stdlib imports first, then project imports:
```python
from __future__ import annotations
import hashlib, logging, os, re
from pathlib import Path
from app.models.schemas import CVProfile
```

---

### `app/dedup/semantic.py` (utility, transform)

**Analog:** `app/cv/llm_client.py`

Pure function that takes an injectable dependency (`embedder: Embedder`) and returns a typed result. No module-level imports of external libraries (numpy is safe; torch is not). The function signature follows the `(data, injected_dependency) -> result` pattern from `extract_cv_profile`.

**Injectable dependency + pure function pattern** (`app/cv/llm_client.py` lines 30–61):
```python
def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    """
    Args:
        raw_text: data input
        client:   injectable dependency — real in production, mock in tests
    Returns:
        Typed output validated by Pydantic
    """
    model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
    return client.messages.create(...)
```

Replicate for `semantic_cluster`:
```python
def semantic_cluster(
    jobs: list[Job],
    embedder: Embedder,        # injectable — FakeEmbedder in tests
    umbral: float = 0.85,
    desc_words: int = 50,
) -> list[list[int]]:
    ...
    embeddings = embedder.embed(texts)    # analogous to client.messages.create(...)
```

**No module-level numpy import required for safety**, but numpy is a direct dependency so it is safe at module level (unlike sentence-transformers). Import normally:
```python
import numpy as np
from app.dedup.embedder import Embedder   # Protocol only — no torch triggered
```

---

### `app/dedup/merger.py` (utility, transform)

**Analog:** `app/cv/parser.py`

Orchestration function with no external dependencies. Takes typed inputs, applies deterministic logic, returns typed output. Minimal imports.

**Orchestration with typed inputs/outputs** (`app/cv/parser.py` lines 22–47):
```python
def parse_cv(pdf_bytes: bytes) -> CVProfile:
    """...
    Args:
        pdf_bytes: Contenido crudo del fichero PDF en memoria.
    Returns:
        CVProfile con la información extraída y validada por Pydantic.
    Raises:
        ValueError: Si el PDF no contiene texto extraíble.
    """
    h = pdf_hash(pdf_bytes)
    cached = load_cached_profile(h)
    if cached is not None:
        return cached
    raw_text = extract_text_from_pdf(pdf_bytes)
    client = build_instructor_client()
    profile = extract_cv_profile(raw_text, client)
    save_cached_profile(h, profile)
    return profile
```

Replicate for `merge_group`:
```python
def merge_group(group: list[Job]) -> Job:
    """Selects canonical Job (longest description) and accumulates urls_alternativas."""
    if len(group) == 1:
        return group[0]
    canonical = max(group, key=lambda j: len(j.description))
    alt_urls = [j.url for j in group if j is not canonical and j.url]
    # Pydantic v2 model_copy(update=...) pattern — see Shared Patterns
    return canonical.model_copy(
        update={"urls_alternativas": list(canonical.urls_alternativas) + alt_urls}
    )
```

---

### `tests/dedup/test_normalize.py` (test, unit)

**Analog:** `tests/cv/test_llm_client.py`

Pure-function tests: no fixtures needed, no monkeypatch, no external deps. Import the function under test directly. Assert on return type and specific field values.

**Pure-function test structure** (`tests/cv/test_llm_client.py` lines 1–70):
```python
"""
Tests para app/cv/llm_client.py.
...
NOTA: NO se llama a la fábrica de cliente real.
"""
from __future__ import annotations
from unittest.mock import MagicMock
from app.cv.llm_client import extract_cv_profile
from app.models.schemas import CVProfile, Experiencia

def test_returns_typed_cvprofile() -> None:
    """extract_cv_profile devuelve el CVProfile que el mock produce (tipado, no str)."""
    mock_client = _make_mock_client()
    result = extract_cv_profile("texto de cv", mock_client)
    assert isinstance(result, CVProfile), f"Se esperaba CVProfile, se obtuvo {type(result)}"
    assert result.skills_tecnicas == ["Python", "LLMs"]
```

For `test_normalize.py`, the tests are even simpler (no mock needed — normalize functions are pure):
```python
def test_stable_id_es_determinista() -> None:
    """Mismo input → mismo id en llamadas sucesivas."""
    id1 = stable_job_id("Acme Corp", "AI Engineer", "Barcelona")
    id2 = stable_job_id("Acme Corp", "AI Engineer", "Barcelona")
    assert id1 == id2

def test_stable_id_es_64_hex() -> None:
    """El id es un sha256 hex de 64 caracteres (consistente con Phase 1)."""
    result = stable_job_id("Acme", "Dev", "Madrid")
    assert len(result) == 64
    assert result == result.lower()
```

---

### `tests/dedup/test_dedup.py` (test, integration-unit)

**Analog:** `tests/cv/test_parser.py`

Uses monkeypatch for env vars if needed, patches internal factory at its import-site (not definition-site), and receives fixtures from conftest. The key pattern: inject the fake dependency via the public function parameter (not via `patch`) because `deduplicate(embedder=fake)` is explicit — cleaner than `patch("app.dedup.__init__.BgeM3Embedder")`.

**Import-site patching pattern** (`tests/cv/test_parser.py` lines 40–41):
```python
# Patch at the import site (where it is used), not at the definition site
with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
    result = parse_cv(sample_pdf_bytes)
```

For `test_dedup.py`, since `deduplicate()` accepts `embedder` as an explicit parameter, direct injection is preferred over patching:
```python
# Direct injection — cleaner than patch() when the seam is an explicit parameter
result = deduplicate(jobs, embedder=fake_embedder, umbral=0.85)
```

**Fixture usage from conftest** (`tests/cv/test_parser.py` lines 26–43):
```python
def test_parse_cv_returns_cv_profile(
    sample_pdf_bytes: bytes,       # session fixture from conftest
    mock_llm_client: MagicMock,    # function fixture from conftest
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))
    ...
    assert isinstance(result, CVProfile)
    assert result.skills_tecnicas == ["Python", "LLMs"]
```

Replicate — fixtures in `tests/conftest.py` (added this phase): `fake_embedder`, `sample_arbeitnow_payload`, `sample_jobs`.

---

### `tests/conftest.py` (modified — add dedup fixtures)

**Analog:** `tests/conftest.py` (existing, lines 1–77)

Add fixtures below the existing CV fixtures. Follow the exact same docstring + scope + type annotation conventions.

**Existing fixture pattern to replicate** (`tests/conftest.py` lines 43–60, 67–77):
```python
@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Genera un PDF mínimo con texto de CV conocido, en memoria (sin escritura a disco).

    El texto incluye literales conocidos ("AI Engineer", "Acme Corp", "Python", "LLMs")
    que los tests de extractor y parser pueden afirmar explícitamente.
    """
    ...

@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Devuelve un MagicMock que imita la superficie de instructor.from_anthropic().

    El método .messages.create() devuelve EXPECTED_PROFILE de forma determinista,
    permitiendo que los tests de parser.py parcheen build_instructor_client sin
    realizar llamadas reales a la API de Anthropic.
    """
    mock_client = MagicMock()
    mock_client.messages.create.return_value = EXPECTED_PROFILE
    return mock_client
```

New fixtures to add follow the same docstring style. `FakeEmbedder` is a real class (not `MagicMock`) because it needs a real `.embed()` method that returns numpy arrays:
```python
@pytest.fixture
def fake_embedder_ortogonal() -> FakeEmbedder:
    """FakeEmbedder con vectores ortogonales: similitud cero entre cualquier par.
    Verifica que trabajos distintos NO se fusionan con umbral 0.85.
    """
    ...

@pytest.fixture
def sample_arbeitnow_payload() -> dict:
    """Payload de ejemplo con el shape real de Arbeitnow (campos verificados 2026-05-22)."""
    return {
        "slug": "ai-engineer-techcorp-12345",
        "company_name": "TechCorp GmbH",
        "title": "AI Engineer",
        "description": "<h2>About</h2><p>We build AI.</p>",
        "remote": False,
        "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
        "tags": ["Engineering"],
        "job_types": ["berufserfahren"],
        "location": "Berlin",
        "created_at": 1716350400,
    }
```

---

## Shared Patterns

### `from __future__ import annotations` header
**Source:** Every file in `app/cv/` (lines 1 of each)
**Apply to:** Every new `.py` file in `app/dedup/` and `tests/dedup/`
```python
from __future__ import annotations
```

### Logging — module-level logger, structured format
**Source:** `app/cv/cache.py` line 22
**Apply to:** `app/dedup/__init__.py`, `app/dedup/normalize.py`
```python
import logging
logger = logging.getLogger(__name__)

# Usage — %s format, never f-strings in logger calls:
logger.info("normalize_jobs: source=%s in=%d ok=%d errors=%d", source, len(raw_offers), len(jobs), len(errors))
logger.warning("Caché corrupta para hash %s, se ignorará y se eliminará: %s", content_hash, exc)
```

### Pydantic v2 model_copy for immutable updates
**Source:** `app/models/schemas.py` — Job is a Pydantic v2 BaseModel
**Apply to:** `app/dedup/merger.py` (when building merged Job with new `urls_alternativas`)
```python
# Pydantic v2: model_copy(update={...}) returns a new instance
canonical = job.model_copy(update={"urls_alternativas": new_list})
# NOT: canonical.urls_alternativas = new_list  (would mutate the original)
```

### Batch-resilient try/except pattern with error accumulation
**Source:** RESEARCH.md Code Examples (verified pattern, no existing Phase 1 analog — this is new to Phase 2)
**Apply to:** `app/dedup/__init__.py` `normalize_jobs()`
```python
jobs: list[Job] = []
errors: list[dict] = []
for idx, raw in enumerate(raw_offers):
    try:
        jobs.append(mapper(raw, source))
    except Exception as exc:  # noqa: BLE001
        errors.append({"index": idx, "source": source, "error": str(exc)})
return jobs, errors
```

### Lazy import inside method — THE anti-torch pattern
**Source:** `app/cv/llm_client.py` lines 19–21 (contrasted: those imports ARE at module level; the pattern to replicate is to move them INSIDE the method for sentence-transformers)
**Apply to:** `app/dedup/embedder.py` `BgeM3Embedder._ensure_loaded()`
```python
def _ensure_loaded(self) -> None:
    if self._model is None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        self._model = SentenceTransformer("BAAI/bge-m3")
```
The `# noqa: PLC0415` comment suppresses the linter warning for non-top-level imports — this is the accepted project pattern for lazy imports (established by the `# noqa: BLE001` pattern in existing code).

### Import-site patching for tests
**Source:** `tests/cv/test_parser.py` lines 40–41
**Apply to:** `tests/dedup/test_dedup.py` if patching `BgeM3Embedder` factory
```python
# Patch at the call site (app.cv.parser), not at the definition site (app.cv.llm_client)
with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
    result = parse_cv(sample_pdf_bytes)
```

### Type hints — complete, Pydantic v2 style
**Source:** `app/models/schemas.py` lines 122–134
**Apply to:** All new files
```python
from typing import Optional
from pydantic import BaseModel, Field

class Job(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    remote: RemoteJob = RemoteJob.unknown
    description: str = ""
    salary: Optional[Salary] = None
    url: Optional[str] = None
    source: str
    posted_at: Optional[str] = None
    raw: dict = Field(default_factory=dict)
    urls_alternativas: list[str] = Field(default_factory=list)
```

### Spanish naming convention
**Source:** `app/models/schemas.py` (all field names in Spanish), `app/cv/llm_client.py` (docstrings in Spanish)
**Apply to:** All new files — field names, variable names, and docstrings in Spanish; function/class names in English (consistent with existing code: `normalize_field`, `stable_job_id`, `exact_group`, `merge_group` are English names; their docstrings and variable names are Spanish)

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/dedup/normalize.py` (NFD accent stripping) | utility | transform | No Unicode normalization exists in codebase; pattern comes from RESEARCH.md (stdlib `unicodedata` — low risk) |

All other files have clear analogs from Phase 1's `app/cv/` module.

---

## Key Observations for Planner

1. **`app/dedup/embedder.py` is the most critical file** — the lazy import invariant (`sentence_transformers` only inside `_ensure_loaded()`) must be enforced. Any test that imports `app.dedup.embedder` must NOT trigger torch initialization. Verify with a standalone `import app.dedup.embedder` timing check.

2. **`tests/conftest.py` must be modified, not replaced** — the existing CV fixtures (`sample_pdf_bytes`, `mock_llm_client`, `EXPECTED_PROFILE`) must be preserved. New dedup fixtures are appended below the separator comment line.

3. **`FakeEmbedder` ships in `app/dedup/embedder.py`**, not in tests/ — this follows the Phase 1 pattern where `build_instructor_client` (the seam) lives in `app/cv/llm_client.py` and tests import it from there. Tests import `FakeEmbedder` from `app.dedup.embedder`.

4. **`Job.urls_alternativas`** is already defined in `app/models/schemas.py` line 134 — no schema change needed. The merger populates this field via `model_copy(update=...)`.

5. **Full 64-char hex for `Job.id`** — consistent with `_HEX_RE = re.compile(r"^[0-9a-f]{64}$")` in `app/cv/cache.py` line 24. Do not truncate.

6. **`dedup_umbral` default wiring** — `UserProfile.dedup_umbral = 0.85` is already in schemas.py line 88. For Phase 2, pass it as a default parameter `deduplicate(..., umbral=0.85)`. Wiring to a loaded `UserProfile` instance is deferred to Phase 4.

---

## Metadata

**Analog search scope:** `app/cv/`, `app/models/`, `tests/cv/`, `tests/conftest.py`
**Files scanned:** 7 source files (all Phase 1 files read in full)
**Pattern extraction date:** 2026-05-22
