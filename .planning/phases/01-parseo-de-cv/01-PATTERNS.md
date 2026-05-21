# Phase 1: Parseo de CV - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 9 (4 source + 5 test)
**Analogs found:** 1 / 9 (near-greenfield project; sole analog is `app/models/schemas.py`)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/cv/__init__.py` | module-init | — | `app/models/schemas.py` (style only) | style-only |
| `app/cv/extractor.py` | utility | file-I/O (bytes → str) | no analog — greenfield | none |
| `app/cv/llm_client.py` | service | request-response (LLM API) | no analog — greenfield | none |
| `app/cv/cache.py` | utility | file-I/O (read/write JSON) | no analog — greenfield | none |
| `app/cv/parser.py` | service | transform (orchestrator) | no analog — greenfield | none |
| `tests/conftest.py` | test | — | no analog — greenfield | none |
| `tests/cv/__init__.py` | test | — | no analog — greenfield | none |
| `tests/cv/test_extractor.py` | test | — | no analog — greenfield | none |
| `tests/cv/test_cache.py` | test | — | no analog — greenfield | none |
| `tests/cv/test_parser.py` | test | — | no analog — greenfield | none |

---

## Pattern Assignments

### `app/models/schemas.py` — The Primary Style Reference

This is the **only existing source file** in the project. All new files must follow its
conventions exactly. Key conventions extracted below.

**Imports pattern** (lines 1–11):
```python
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
```

Conventions:
- `from __future__ import annotations` always first
- stdlib imports before third-party imports (PEP 8 order)
- `Optional` from `typing` (not `X | None` syntax, even on Python 3.13)
- `Field(default_factory=list)` for mutable defaults on Pydantic models

**Pydantic v2 model pattern** (lines 92–111):
```python
class Experiencia(BaseModel):
    empresa: str
    rol: str
    duracion: Optional[str] = None
    tecnologias: list[str] = Field(default_factory=list)
    logros: list[str] = Field(default_factory=list)


class Formacion(BaseModel):
    titulo: str
    institucion: Optional[str] = None
    anio: Optional[int] = None


class CVProfile(BaseModel):
    experiencia: list[Experiencia] = Field(default_factory=list)
    skills_tecnicas: list[str] = Field(default_factory=list)
    formacion: list[Formacion] = Field(default_factory=list)
    anios_experiencia_total: Optional[float] = None  # estimado
    dominios: list[str] = Field(default_factory=list)  # ej. ["finanzas", "regulación"]
```

Conventions:
- Field names in **Spanish** (snake_case)
- Comments in Spanish
- `Optional[T] = None` for optional fields
- No validators yet (FASE 1 is data shape only)
- `Field(ge=0, le=100)` for bounded integers (see `Desglose` lines 139–143)
- Enums inherit from `(str, Enum)` — JSON-serializable by default

**Enum pattern** (lines 14–32):
```python
class ModalidadRemoto(str, Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    indiferente = "indiferente"
```

**Serialization pattern** (implied by existing schemas — Pydantic v2):
- Write cache: `profile.model_dump_json(indent=2)`
- Read cache: `CVProfile.model_validate_json(text)`
- Never use `.dict()` (Pydantic v1 API)

---

### `app/cv/__init__.py` (module-init)

**Copy style from:** `app/models/schemas.py` header (docstring convention)

```python
"""
Módulo de parseo de CV.
Interfaz pública: parse_cv(pdf_bytes: bytes) -> CVProfile
"""
from app.cv.parser import parse_cv

__all__ = ["parse_cv"]
```

No analog in codebase. Use the docstring style from `app/models/schemas.py` lines 1–4:
```python
"""
Schemas Pydantic v2 del Agregador de ofertas.
FASE 1 del proyecto: SOLO la forma de los datos (sin lógica todavía).
"""
```

---

### `app/cv/extractor.py` (utility, file-I/O)

**No analog in codebase.** Follow RESEARCH.md Pattern 1 (lines 183–206) and the
code style from `app/models/schemas.py`.

**Imports pattern to copy:**
```python
from __future__ import annotations

import pymupdf
```

**Core pattern** (from RESEARCH.md, lines 193–204):
```python
def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrae todo el texto de un PDF multi-página, en orden de lectura."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages_text = [page.get_text() for page in doc]
    text = "\n\n".join(pages_text).strip()
    if not text:
        raise ValueError(
            "El PDF no contiene capa de texto extraíble. "
            "PDFs escaneados (solo imagen) no están soportados en v1."
        )
    return text
```

**Error handling pattern:** Raise `ValueError` with a descriptive Spanish message when
the PDF has no extractable text. No try/except wrapper — let the caller handle it.

**Anti-pattern to avoid:** `import fitz` — use `import pymupdf` only (RESEARCH.md line 378).

---

### `app/cv/llm_client.py` (service, request-response)

**No analog in codebase.** Follow RESEARCH.md Pattern 2 (lines 210–247) and Pattern 3
code style from `app/models/schemas.py`.

**Imports pattern to copy:**
```python
from __future__ import annotations

import os

import instructor
from anthropic import Anthropic

from app.models.schemas import CVProfile
```

**Core pattern** (from RESEARCH.md, lines 222–246):
```python
def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())


def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    """Llama al LLM para extraer un CVProfile estructurado del texto del CV."""
    model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
    return client.messages.create(
        model=model,
        max_tokens=4096,
        system=(
            "Eres un extractor de CVs preciso. "
            "Extrae ÚNICAMENTE lo que aparece explícitamente en el texto. "
            "No inventes datos. Si un campo no aparece, déjalo vacío o None. "
            "Para anios_experiencia_total, estima sumando la duración de los empleos "
            "a partir de las fechas indicadas."
        ),
        messages=[
            {
                "role": "user",
                "content": f"Extrae el CVProfile del siguiente CV:\n\n{raw_text}"
            }
        ],
        response_model=CVProfile,
        max_retries=2,
    )
```

**Critical pitfalls from RESEARCH.md:**
- Use `client.messages.create(...)` NOT `client.create(...)` (RESEARCH.md line 383)
- Model name default: `"claude-haiku-4-5-20251001"` — `claude-3-5-haiku-20241022` is
  deprecated as of Feb 2026 (RESEARCH.md lines 403–407)
- `ANTHROPIC_API_KEY` from `os.getenv()` only — never hardcoded

---

### `app/cv/cache.py` (utility, file-I/O)

**No analog in codebase.** Follow RESEARCH.md Pattern 3 (lines 255–280).

**Imports pattern to copy:**
```python
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.models.schemas import CVProfile
```

**Core pattern** (from RESEARCH.md, lines 265–280):
```python
CACHE_DIR = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))


def pdf_hash(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def load_cached_profile(content_hash: str) -> CVProfile | None:
    cache_file = CACHE_DIR / f"{content_hash}.json"
    if cache_file.exists():
        return CVProfile.model_validate_json(cache_file.read_text())
    return None


def save_cached_profile(content_hash: str, profile: CVProfile) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{content_hash}.json"
    cache_file.write_text(profile.model_dump_json(indent=2))
```

Note: `CACHE_DIR` uses `os.getenv("CV_CACHE_DIR", "data/.cache")` — this makes the
cache location configurable in tests via `monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))`.
RESEARCH.md Open Question 1 (line 519) recommends this approach.

**Serialization rule:** Always `profile.model_dump_json()` / `CVProfile.model_validate_json()`.
Never `json.dumps(profile.dict())` (RESEARCH.md lines 432–436).

---

### `app/cv/parser.py` (service, transform — public interface)

**No analog in codebase.** Follow RESEARCH.md Pattern 4 (lines 284–308).

**Imports pattern to copy:**
```python
from __future__ import annotations

from app.cv.cache import load_cached_profile, pdf_hash, save_cached_profile
from app.cv.extractor import extract_text_from_pdf
from app.cv.llm_client import build_instructor_client, extract_cv_profile
from app.models.schemas import CVProfile
```

**Core pattern** (from RESEARCH.md, lines 293–308):
```python
def parse_cv(pdf_bytes: bytes) -> CVProfile:
    """
    Interfaz pública de la fase.
    1. Comprueba caché por sha256.
    2. Si no hay caché: extrae texto con pymupdf → LLM → cachea.
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

---

### `tests/conftest.py` (test fixture — session scope)

**No analog in codebase.** Follow RESEARCH.md Pattern 6 (lines 353–373).

**Pattern to copy:**
```python
import pymupdf
import pytest


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """PDF mínimo con texto de CV conocido, generado en memoria."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Jaime Berdejo - AI Engineer\n"
        "Empresa: Acme Corp | Rol: AI Engineer | 2022-2024\n"
        "Skills: Python, LLMs, FastAPI\n"
        "Formación: Grado Informática, UPC, 2020\n",
        fontsize=12,
    )
    return doc.tobytes()
```

Use `scope="session"` — the PDF generation is expensive and should run once per test
session. Use `pymupdf` (already a core dep) to avoid adding `reportlab` for tests only.

---

### `tests/cv/test_extractor.py` (test, utility)

**No analog in codebase.** Follow RESEARCH.md Wave 0 Gaps (lines 578–586).

**Pattern to copy:**
```python
import pytest
from app.cv.extractor import extract_text_from_pdf


def test_extract_text_returns_string(sample_pdf_bytes: bytes) -> None:
    text = extract_text_from_pdf(sample_pdf_bytes)
    assert isinstance(text, str)
    assert len(text) > 0


def test_extract_text_contains_known_content(sample_pdf_bytes: bytes) -> None:
    text = extract_text_from_pdf(sample_pdf_bytes)
    assert "AI Engineer" in text


def test_extract_text_raises_on_empty_pdf() -> None:
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()  # blank page, no text
    empty_pdf = doc.tobytes()
    with pytest.raises(ValueError, match="capa de texto"):
        extract_text_from_pdf(empty_pdf)
```

---

### `tests/cv/test_cache.py` (test, file-I/O)

**No analog in codebase.**

**Pattern to copy:**
```python
import pytest
from app.cv.cache import load_cached_profile, pdf_hash, save_cached_profile
from app.models.schemas import CVProfile, Experiencia


@pytest.fixture
def sample_profile() -> CVProfile:
    return CVProfile(
        experiencia=[Experiencia(empresa="Acme Corp", rol="AI Engineer", duracion="2 años")],
        skills_tecnicas=["Python", "LLMs"],
        anios_experiencia_total=2.0,
        dominios=["IA"],
    )


def test_cache_roundtrip(tmp_path, monkeypatch, sample_profile: CVProfile) -> None:
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    h = "abc123"
    save_cached_profile(h, sample_profile)
    loaded = load_cached_profile(h)
    assert loaded is not None
    assert loaded.skills_tecnicas == ["Python", "LLMs"]
    assert loaded.anios_experiencia_total == 2.0


def test_cache_miss_returns_none(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    assert load_cached_profile("nonexistent_hash") is None
```

Cache isolation: always use `monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))` to
redirect cache writes away from `data/.cache/` real directory.

---

### `tests/cv/test_parser.py` (test, end-to-end with mocked LLM — QA-01)

**No analog in codebase.** Follow RESEARCH.md Pattern 5 (lines 313–347).

**Pattern to copy:**
```python
from unittest.mock import MagicMock, patch

import pytest

from app.cv.parser import parse_cv
from app.models.schemas import CVProfile, Experiencia

EXPECTED_PROFILE = CVProfile(
    experiencia=[Experiencia(empresa="Acme Corp", rol="AI Engineer", duracion="2 años")],
    skills_tecnicas=["Python", "LLMs"],
    anios_experiencia_total=2.0,
    dominios=["IA"],
)


@pytest.fixture
def mock_llm_client() -> MagicMock:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = EXPECTED_PROFILE
    return mock_client


def test_parse_cv_returns_cv_profile(
    sample_pdf_bytes: bytes,
    mock_llm_client: MagicMock,
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))

    with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
        result = parse_cv(sample_pdf_bytes)

    assert isinstance(result, CVProfile)
    assert result.skills_tecnicas == ["Python", "LLMs"]


def test_parse_cv_cache_avoids_llm_second_call(
    sample_pdf_bytes: bytes,
    mock_llm_client: MagicMock,
    tmp_path,
    monkeypatch,
) -> None:
    """Segunda llamada con el mismo PDF no invoca el LLM (QA-01 / CV-03)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))

    with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
        parse_cv(sample_pdf_bytes)
        parse_cv(sample_pdf_bytes)

    assert mock_llm_client.messages.create.call_count == 1
```

Mock target: `"app.cv.parser.build_instructor_client"` — patch at the import site
in `parser.py`, not at the definition site in `llm_client.py`.

---

## Shared Patterns

### Type Hints
**Source:** `app/models/schemas.py` (entire file)
**Apply to:** All new files in `app/cv/`

- Full type hints on every function signature (parameters and return type)
- `from __future__ import annotations` at top of every file
- `Optional[T]` from `typing` (not `T | None`)
- Return type annotation on every function, including `-> None`

### Environment Variables
**Source:** CLAUDE.md (stack section) + RESEARCH.md (lines 380–382)
**Apply to:** `app/cv/llm_client.py`, `app/cv/cache.py`

```python
import os
# Pattern: os.getenv("VAR_NAME", "default_value")
model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
cache_dir = os.getenv("CV_CACHE_DIR", "data/.cache")
```

Never hardcode API keys or paths. Always provide a sensible default.

### Docstrings
**Source:** `app/models/schemas.py` (module docstring lines 1–4, inline comments)
**Apply to:** All new files

- Module-level docstring in Spanish describing the module's role
- Function docstrings in Spanish
- Inline comments in Spanish

### Pydantic v2 Serialization
**Source:** `app/models/schemas.py` (implied by schema definitions)
**Apply to:** `app/cv/cache.py`, any code that serializes/deserializes `CVProfile`

```python
# Write
cache_file.write_text(profile.model_dump_json(indent=2))

# Read
CVProfile.model_validate_json(cache_file.read_text())
```

Never use `.dict()`, `.json()`, or `json.dumps()` on Pydantic models.

### Test Isolation
**Source:** RESEARCH.md Common Pitfalls #5 (lines 427–431)
**Apply to:** All test files that touch `app/cv/cache.py`

```python
# In every test that exercises cache
monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))
```

This prevents test runs from writing to the real `data/.cache/` directory.

---

## No Analog Found

All files for this phase are greenfield. The single existing source analog is
`app/models/schemas.py`, which serves only as a **code-style reference** (imports,
type hints, Pydantic v2 usage, Spanish naming). No behavioral analog exists.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/cv/extractor.py` | utility | file-I/O | No PDF-processing code exists yet |
| `app/cv/llm_client.py` | service | request-response | No LLM client code exists yet |
| `app/cv/cache.py` | utility | file-I/O | No caching code exists yet |
| `app/cv/parser.py` | service | transform | No orchestrator code exists yet |
| `tests/conftest.py` | test | — | No tests exist yet |
| `tests/cv/test_extractor.py` | test | — | No tests exist yet |
| `tests/cv/test_cache.py` | test | — | No tests exist yet |
| `tests/cv/test_parser.py` | test | — | No tests exist yet |

For all greenfield files: use RESEARCH.md patterns as the authoritative code reference,
and `app/models/schemas.py` as the code-style reference (imports, naming, type hints).

---

## Metadata

**Analog search scope:** `/Users/jaimeberdejosanchez/projects/BuscadorDeEmpleo/app/`
**Files scanned:** 1 source file (`app/models/schemas.py`), 1 config (`pyproject.toml`), 1 data file (`data/profile.yaml`)
**Empty dirs confirmed:** `app/cv/`, `app/api/`, `app/config/`, `app/dedup/`, `app/scoring/`, `app/storage/`, `tests/`
**Pattern extraction date:** 2026-05-22
