# Phase 4: API y Persistencia - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 12 new/modified files
**Analogs found:** 8 / 12 (4 greenfield with no codebase analog — FastAPI/SQLite layer is new)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/api/__init__.py` | config | — | `app/cv/__init__.py` | structural |
| `app/api/main.py` | config | request-response | GREENFIELD — see RESEARCH.md Pattern 1 | none |
| `app/api/deps.py` | provider | request-response | `app/scoring/llm.py` + `app/cv/cache.py` | role-match |
| `app/api/routes/__init__.py` | config | — | `app/cv/__init__.py` | structural |
| `app/api/routes/cv.py` | controller | request-response | `app/cv/parser.py` (delegation pattern) | role-match |
| `app/api/routes/profile.py` | controller | request-response | `app/config/loader.py` (delegation) | role-match |
| `app/api/routes/jobs.py` | controller | request-response | `app/dedup/__init__.py` (batch-resilient) | role-match |
| `app/storage/__init__.py` | config | — | `app/scoring/__init__.py` | structural |
| `app/storage/protocol.py` | provider | CRUD | `app/dedup/embedder.py` (Protocol pattern) | exact |
| `app/storage/sqlite.py` | service | CRUD | `app/cv/cache.py` (stdlib I/O, logger, error) | role-match |
| `app/storage/supabase.py` | service | CRUD | `app/storage/sqlite.py` (same Protocol) | role-match |
| `tests/api/conftest.py` | test | request-response | `tests/conftest.py` (mock patterns) | exact |
| `tests/api/test_cv.py` | test | request-response | `tests/cv/test_parser.py` | role-match |
| `tests/api/test_profile.py` | test | request-response | `tests/cv/test_parser.py` | role-match |
| `tests/api/test_jobs.py` | test | request-response | `tests/dedup/test_dedup.py` | role-match |
| `tests/storage/test_sqlite.py` | test | CRUD | `tests/cv/test_cache.py` | role-match |

---

## Pattern Assignments

### `app/api/__init__.py`, `app/api/routes/__init__.py`, `app/storage/__init__.py`

**Analog:** `app/cv/__init__.py`, `app/scoring/__init__.py`

These are minimal package init files. The project convention is a short docstring + explicit `__all__` only when the package is a facade. Follow the scoring pattern — `app/scoring/__init__.py` only re-exports the public symbol with `__all__`:

**Core pattern** (`app/scoring/__init__.py` lines 1-14):
```python
"""Módulo de scoring de ofertas (FASE 3).

Interfaz pública:
    score_job(job, cv_profile, user_profile, client=None) -> JobScore
"""

from app.scoring.scorer import score_job

__all__ = ["score_job"]
```

For `app/storage/__init__.py`, export the `get_storage_backend()` selection function and `Storage` Protocol.

---

### `app/api/main.py` (config, request-response)

**Analog:** GREENFIELD — no existing FastAPI app in codebase.
**Pattern source:** RESEARCH.md Pattern 1 (lifespan + APIRouter), verified against FastAPI 0.136.1 docs.

**Established conventions to carry over from existing codebase:**

Module-level docstring style (`app/cv/parser.py` lines 1-13):
```python
"""
Orquestador público de parseo de CV.

Implementa la interfaz pública `parse_cv(pdf_bytes) -> CVProfile` que:
  1. Comprueba la caché por sha256 del contenido del PDF (CV-03).
  ...
"""
from __future__ import annotations
```

Env-var reading pattern (`app/cv/cache.py` lines 27-29):
```python
def _cache_dir() -> Path:
    """Devuelve el directorio de caché actual, leyendo CV_CACHE_DIR en tiempo de llamada."""
    return Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
```

Apply same lazy env-var read for `SQLITE_DB_PATH` and `SUPABASE_URL`/`SUPABASE_KEY` in lifespan. Do NOT read env vars at module import time.

**Core pattern** (from RESEARCH.md Pattern 1 — use verbatim):
```python
# app/api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import cv, profile, jobs
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        from app.storage.supabase import SupabaseStorage
        storage = SupabaseStorage()
    else:
        from app.storage.sqlite import SQLiteStorage
        db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
        storage = SQLiteStorage(db_path)
        storage.init_db()
    app.state.storage = storage
    yield
    # cleanup if needed

app = FastAPI(title="BuscadorDeEmpleo", lifespan=lifespan)
app.include_router(cv.router)
app.include_router(profile.router)
app.include_router(jobs.router)
```

Note: storage imports inside lifespan body — same deferred import pattern used in `app/dedup/__init__.py` lines 106-109 to avoid torch-at-import. Apply here to avoid circular import and to keep the app importable without triggering SQLite setup.

---

### `app/api/deps.py` (provider, request-response)

**Analog:** `app/scoring/llm.py` (build_instructor_client seam) + `app/cv/cache.py` (cache dir reading)

**LLM client factory pattern** (`app/scoring/llm.py` lines 38-40):
```python
def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())
```

**CV client factory pattern** (`app/cv/llm_client.py` lines 25-27):
```python
def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre Anthropic. Inyectable para tests."""
    return instructor.from_anthropic(Anthropic())
```

Both modules use the identical factory name. In `deps.py`, alias them with distinct names:

```python
# app/api/deps.py
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import HTTPException, Request

from app.models.schemas import CVProfile

logger = logging.getLogger(__name__)


def get_storage(request: Request):
    """Lee el singleton Storage desde app.state (inicializado en lifespan)."""
    return request.app.state.storage


def get_cv_llm_client():
    """Cliente LLM para parseo de CV. Reemplazable en tests via dependency_overrides."""
    from app.cv.llm_client import build_instructor_client
    return build_instructor_client()


def get_scoring_llm_client():
    """Cliente LLM para scoring. Reemplazable en tests via dependency_overrides."""
    from app.scoring.llm import build_instructor_client
    return build_instructor_client()


def get_embedder():
    """BGE-M3 embedder. Import DEFERIDO — nunca dispara torch al importar el módulo."""
    from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
    return BgeM3Embedder()


def get_cached_cv_profile() -> CVProfile:
    """Devuelve el CVProfile cacheado o lanza 404 con instrucción clara.
    
    Lee data/.cache/_current para encontrar el hash activo (escrito por /cv/parse).
    """
    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    current_file = cache_dir / "_current"
    if not current_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No hay CVProfile cacheado. Llama a POST /cv/parse primero.",
        )
    content_hash = current_file.read_text(encoding="utf-8").strip()
    profile_file = cache_dir / f"{content_hash}.json"
    if not profile_file.exists():
        raise HTTPException(
            status_code=404,
            detail="CVProfile cacheado no encontrado. Llama a POST /cv/parse primero.",
        )
    return CVProfile.model_validate_json(profile_file.read_text(encoding="utf-8"))
```

**Deferred import pattern** (established in `app/dedup/__init__.py` lines 105-109):
```python
    # Imports deferidos: evitan arrastrar numpy/torch al importar app.dedup (T-02-11)
    from app.dedup.exact import exact_group  # noqa: PLC0415
    from app.dedup.semantic import semantic_cluster  # noqa: PLC0415
    from app.dedup.merger import merge_group  # noqa: PLC0415
    from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
```

Use `# noqa: PLC0415` on every deferred import inside function bodies — this is an established project convention.

---

### `app/api/routes/cv.py` (controller, request-response)

**Analog:** `app/cv/parser.py` (delegation to `parse_cv`) + `app/cv/cache.py` (`save_cached_profile` / `_cache_dir`)

**Delegation pattern** (`app/cv/parser.py` lines 22-47): the route delegates entirely to `parse_cv()` and only adds HTTP-layer concerns (content-type check, HTTPException wrapping, _current file write).

**Logging pattern** (`app/cv/cache.py` lines 21-22 and `app/config/loader.py` lines 18-19):
```python
import logging
logger = logging.getLogger(__name__)
```

Use `logging.getLogger(__name__)` in every route file — consistent with all existing modules.

**Core pattern:**
```python
# app/api/routes/cv.py
from __future__ import annotations

import logging
import os
from pathlib import Path

import instructor
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_cv_llm_client
from app.cv.cache import pdf_hash, save_cached_profile
from app.cv.parser import parse_cv
from app.models.schemas import CVProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("/parse", response_model=CVProfile)
async def parse_cv_endpoint(
    file: UploadFile = File(..., description="CV en formato PDF"),
    client: instructor.Instructor = Depends(get_cv_llm_client),
) -> CVProfile:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Solo se aceptan ficheros PDF.")
    pdf_bytes = await file.read()  # await ES OBLIGATORIO — UploadFile.read() es corrutina
    try:
        profile = parse_cv(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Escribir _current con el hash activo para que get_cached_cv_profile lo encuentre
    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "_current").write_text(pdf_hash(pdf_bytes), encoding="utf-8")
    logger.info("CV parseado y cacheado. Skills: %d", len(profile.skills_tecnicas))
    return profile
```

**Error handling pattern** (`app/config/loader.py` lines 52-62):
```python
    try:
        profile = UserProfile.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"profile.yaml inválido:\n{e}") from e
```

Routes catch domain exceptions (`ValueError`, `FileNotFoundError`) and re-raise as `HTTPException`. Do NOT let Pydantic ValidationError propagate unhandled — FastAPI converts it to 422 automatically when it comes from request body parsing, but not from internal calls.

---

### `app/api/routes/profile.py` (controller, request-response)

**Analog:** `app/config/loader.py` (delegation to `load_user_profile`)

**Core pattern:**
```python
# app/api/routes/profile.py
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.config.loader import load_user_profile
from app.models.schemas import UserProfile

logger = logging.getLogger(__name__)
router = APIRouter(prefix="", tags=["profile"])


@router.get("/profile", response_model=UserProfile)
def get_profile() -> UserProfile:
    """Devuelve el UserProfile cargado desde data/profile.yaml."""
    try:
        return load_user_profile()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

Use `def` (sync) not `async def` — `load_user_profile` does blocking file I/O. FastAPI runs sync endpoints in its threadpool automatically. This is the established project convention for all non-file-upload endpoints.

---

### `app/api/routes/jobs.py` (controller, request-response)

**Analog:** `app/dedup/__init__.py` (batch-resilient normalize_jobs) + `app/scoring/scorer.py` (score_job delegation)

**Batch-resilient pattern** (`app/dedup/__init__.py` lines 44-60):
```python
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
```

Apply same `try/except Exception` + append-to-errors pattern in `/jobs/process` when iterating over scoring — one bad offer must not kill the batch.

**Logging pattern** (`app/scoring/scorer.py` lines 104-110):
```python
    logger.info(
        "score_job: job=%s score=%d recommendation=%s deal_breaker=%s",
        job.id,
        score_total,
        recommendation.value,
        deal_breaker_cual,
    )
```

Use `logger.info(format, *args)` — positional args, not f-strings in logger calls. Consistent across all existing modules.

**Core structure for `/jobs/process`:**
```python
# app/api/routes/jobs.py (excerpt — /jobs/process)
@router.post("/jobs/process", response_model=ProcessResponse)
def process_jobs(
    body: ProcessRequest,
    cv_profile: CVProfile = Depends(get_cached_cv_profile),
    user_profile: UserProfile = Depends(get_user_profile_dep),
    scoring_client: instructor.Instructor = Depends(get_scoring_llm_client),
    embedder = Depends(get_embedder),
    storage = Depends(get_storage),
) -> ProcessResponse:
    # 1. Normalizar todas las fuentes
    all_jobs: list[Job] = []
    all_errors: list[dict] = []
    for source_block in body.sources:
        jobs, errors = normalize_jobs(source_block.offers, source_block.source)
        all_jobs.extend(jobs)
        all_errors.extend(errors)

    # 2. Deduplicar
    unique_jobs = deduplicate(all_jobs, embedder=embedder, umbral=user_profile.dedup_umbral)

    # 3. Score (batch-resiliente: un error no tumba el batch)
    scored: list[ScoredJobConVisto] = []
    for job in unique_jobs:
        ya_visto = storage.was_seen(job.id)
        try:
            score = score_job(job, cv_profile, user_profile, client=scoring_client)
            scored.append(ScoredJobConVisto(job=job, score=score, ya_visto=ya_visto))
        except Exception as exc:  # noqa: BLE001
            all_errors.append({"job_id": job.id, "error": str(exc)})
            logger.warning("Error puntuando oferta %s: %s", job.id, exc)

    # 4. Persistir y ordenar
    storage.upsert_scored_jobs([ScoredJob(job=s.job, score=s.score) for s in scored])
    scored.sort(key=lambda s: s.score.score_total, reverse=True)

    logger.info(
        "process_jobs: entradas=%d unicos=%d puntuados=%d errores=%d",
        sum(len(b.offers) for b in body.sources),
        len(unique_jobs),
        len(scored),
        len(all_errors),
    )
    return ProcessResponse(results=scored, errors=all_errors)
```

**Request/response model naming convention** (Spanish nouns, Pydantic v2 BaseModel, from `app/models/schemas.py`):

The existing models use Spanish field names (`datos_personales`, `ranking_puestos`, `deal_breakers`) and English model class names (`UserProfile`, `CVProfile`, `Job`). Apply the same mixed convention for API request/response models — English class names, Spanish field names where they are domain-specific, English where they match HTTP conventions (`source`, `offers`, `errors`, `limit`, `offset`).

Define in `app/api/routes/jobs.py` (or a separate `app/api/models.py`):
```python
class SourceBlock(BaseModel):
    source: str
    offers: list[dict]

class ProcessRequest(BaseModel):
    sources: list[SourceBlock]

class ScoredJobConVisto(BaseModel):
    job: Job
    score: JobScore
    ya_visto: bool = False

class ProcessResponse(BaseModel):
    results: list[ScoredJobConVisto]
    errors: list[dict] = Field(default_factory=list)

class NormalizeRequest(BaseModel):
    source: str
    offers: list[dict]

class NormalizeResponse(BaseModel):
    jobs: list[Job]
    errors: list[dict] = Field(default_factory=list)
```

---

### `app/storage/protocol.py` (provider, CRUD)

**Analog:** `app/dedup/embedder.py` — the existing `Embedder` Protocol (lines 29-48)

**Protocol pattern** (`app/dedup/embedder.py` lines 29-48):
```python
from typing import Protocol

class Embedder(Protocol):
    """Interfaz que deben satisfacer todos los embedders.

    Contratos:
    - embed(texts) devuelve un array float32 de shape (len(texts), dim).
    - Los vectores son L2-normalizados: dot(v, v) == 1.0.
    - Mismo texto → mismo vector (determinismo).
    """

    def embed(self, texts: list[str]) -> np.ndarray:
        """..."""
        ...
```

Apply identical structure for `Storage` — `typing.Protocol` (not ABC), docstring with contracts, `...` body for each method, `@runtime_checkable` decorator so `isinstance(obj, Storage)` works in the selection logic:

```python
# app/storage/protocol.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from app.models.schemas import ScoredJob

@runtime_checkable
class Storage(Protocol):
    """Interfaz de persistencia. SQLiteStorage y SupabaseStorage deben satisfacerla.

    Contratos:
    - upsert_scored_jobs: idempotente por job.id; actualiza si ya existe.
    - was_seen: True si el job_id fue persistido en un run anterior.
    - get_history: paginable con limit/offset; devuelve dicts serializables a JSON.
    """

    def init_db(self) -> None: ...
    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None: ...
    def was_seen(self, job_id: str) -> bool: ...
    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
```

No imports of numpy or torch needed — pure typing.

---

### `app/storage/sqlite.py` (service, CRUD)

**Analog:** `app/cv/cache.py` — closest existing file for stdlib I/O patterns, logger, error handling, Pydantic v2 JSON round-trip.

**Logger + module docstring** (`app/cv/cache.py` lines 1-22):
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
```

Apply same structure: `from __future__ import annotations`, `logging.getLogger(__name__)`, `import os` for env vars.

**Pydantic v2 JSON round-trip** (`app/cv/cache.py` lines 75 and 106):
```python
# Deserializar:
return CVProfile.model_validate_json(cache_file.read_text(encoding="utf-8"))
# Serializar:
cache_file.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
```

For SQLite TEXT column: `score.model_dump_json()` to store, `JobScore.model_validate_json(row["score_json"])` to load. Never use `.dict()` or `.json()` — Pydantic v1 API.

**Error handling** (`app/cv/cache.py` lines 73-86):
```python
    try:
        return CVProfile.model_validate_json(cache_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Caché corrupta para hash %s, se ignorará y se eliminará: %s",
            content_hash,
            exc,
        )
        try:
            cache_file.unlink(missing_ok=True)
        except OSError:
            pass
        return None
```

Apply same `try/except Exception` with `logger.warning(format, arg1, arg2)` pattern when loading history rows that fail to deserialize.

**Core SQLite pattern** (RESEARCH.md Pattern 4 — use verbatim, established in research):
```python
# app/storage/sqlite.py
import sqlite3
import json
import logging
from datetime import datetime, timezone
from app.models.schemas import ScoredJob, JobScore

logger = logging.getLogger(__name__)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class SQLiteStorage:
    def __init__(self, db_path: str = "data/jobs.db"):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False: FastAPI corre endpoints sync en un threadpool.
        # Conexión-por-llamada (nuevo sqlite3.connect en cada _connect()) es
        # la forma más simple y segura de thread-safety a esta escala.
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    remote TEXT,
                    url TEXT,
                    source TEXT,
                    score_total INTEGER,
                    recommendation TEXT,
                    score_json TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    seen INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None:
        now = _now_iso()
        with self._connect() as conn:
            for item in scored:
                job, score = item.job, item.score
                conn.execute("""
                    INSERT INTO jobs
                        (id, title, company, location, remote, url, source,
                         score_total, recommendation, score_json, first_seen, last_seen, seen)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)
                    ON CONFLICT(id) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        score_total = excluded.score_total,
                        recommendation = excluded.recommendation,
                        score_json = excluded.score_json
                """, (
                    job.id, job.title, job.company, job.location,
                    job.remote.value if job.remote else None,
                    job.url, job.source, score.score_total,
                    score.recommendation.value,
                    score.model_dump_json(),  # Pydantic v2 — serialize enums correctly
                    now, now,
                ))
            conn.commit()
        logger.info("upsert_scored_jobs: %d ofertas persistidas", len(scored))

    def was_seen(self, job_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return row is not None

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        result = []
        for row in rows:
            try:
                score = JobScore.model_validate_json(row["score_json"])
                result.append({
                    "id": row["id"],
                    "title": row["title"],
                    "company": row["company"],
                    "score_total": row["score_total"],
                    "recommendation": row["recommendation"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "score": score.model_dump(),
                })
            except Exception as exc:
                logger.warning("Error deserializando oferta %s: %s", row["id"], exc)
        return result
```

Key SQLite rules enforced:
- `ON CONFLICT(id) DO UPDATE SET` (NOT `INSERT OR REPLACE` — would lose `first_seen`)
- `conn.row_factory = sqlite3.Row` — column access by name
- Single transaction for bulk upsert (`with self._connect() as conn:` wraps all inserts)
- `check_same_thread=False` always present

---

### `app/storage/supabase.py` (service, CRUD — skeleton)

**Analog:** `app/storage/sqlite.py` (same Protocol interface)

Minimum viable skeleton — same method signatures, `NotImplementedError` body, with a comment documenting the Supabase client import needed:

```python
# app/storage/supabase.py
from __future__ import annotations

import logging
from app.models.schemas import ScoredJob

logger = logging.getLogger(__name__)


class SupabaseStorage:
    """Skeleton de Storage sobre Supabase/pgvector.
    
    Implementa el mismo Protocol que SQLiteStorage.
    Seleccionado cuando SUPABASE_URL y SUPABASE_KEY están en el entorno.
    Implementación real diferida a Fase 5.
    """

    def __init__(self) -> None:
        # from supabase import create_client  # cuando se implemente
        logger.warning("SupabaseStorage: skeleton — no persiste nada todavía.")

    def init_db(self) -> None:
        pass  # Supabase tables managed via migrations

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None:
        raise NotImplementedError("SupabaseStorage no implementado aún.")

    def was_seen(self, job_id: str) -> bool:
        raise NotImplementedError("SupabaseStorage no implementado aún.")

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        raise NotImplementedError("SupabaseStorage no implementado aún.")
```

---

### `tests/api/conftest.py` (test, request-response)

**Analog:** `tests/conftest.py` — the existing mock patterns are the strongest analog (lines 80-91 and 235-249).

**MagicMock client pattern** (`tests/conftest.py` lines 80-91):
```python
@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Devuelve un MagicMock que imita la superficie de instructor.from_anthropic().

    El método .messages.create() devuelve EXPECTED_PROFILE de forma determinista.
    """
    mock_client = MagicMock()
    mock_client.messages.create.return_value = EXPECTED_PROFILE
    return mock_client
```

**make_scoring_client factory** (`tests/conftest.py` lines 235-249):
```python
def make_scoring_client(assessment: LLMJobAssessment) -> MagicMock:
    mock_client = MagicMock()
    mock_client.messages.create.return_value = assessment
    return mock_client
```

**Deferred FakeEmbedder import** (`tests/conftest.py` lines 113-117):
```python
    from app.dedup.embedder import FakeEmbedder  # import deferido — módulo creado en Plan 03
    vector_unidad = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    return FakeEmbedder(default_vector=vector_unidad)
```

**Core TestClient fixture with dependency_overrides:**
```python
# tests/api/conftest.py
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.deps import (
    get_cv_llm_client,
    get_embedder,
    get_scoring_llm_client,
    get_storage,
    get_cached_cv_profile,
)
from tests.conftest import make_scoring_client, EXPECTED_ASSESSMENT, EXPECTED_PROFILE


class FakeStorage:
    """Storage en memoria para tests — sin disco, sin SQLite."""
    def __init__(self):
        self._seen: set[str] = set()
        self._jobs: list[dict] = []

    def init_db(self): pass

    def upsert_scored_jobs(self, scored):
        for item in scored:
            self._seen.add(item.job.id)

    def was_seen(self, job_id: str) -> bool:
        return job_id in self._seen

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        return self._jobs[offset:offset + limit]


@pytest.fixture
def api_client():
    fake_store = FakeStorage()
    mock_scoring = make_scoring_client(EXPECTED_ASSESSMENT)
    mock_cv = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    mock_cv.messages.create.return_value = EXPECTED_PROFILE

    import numpy as np
    from app.dedup.embedder import FakeEmbedder  # import deferido — anti-torch
    fake_embedder = FakeEmbedder(default_vector=np.array([1., 0., 0., 0.], dtype=np.float32))

    app.dependency_overrides[get_storage] = lambda: fake_store
    app.dependency_overrides[get_scoring_llm_client] = lambda: mock_scoring
    app.dependency_overrides[get_cv_llm_client] = lambda: mock_cv
    app.dependency_overrides[get_embedder] = lambda: fake_embedder

    with TestClient(app) as client:
        yield client

    app.dependency_overrides = {}  # CRÍTICO: reset para evitar polución entre tests


@pytest.fixture
def api_client_with_cv(api_client, tmp_path, monkeypatch):
    """api_client con CVProfile cacheado (para endpoints que requieren /cv/parse)."""
    from app.models.schemas import CVProfile
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    (tmp_path / "_current").write_text("a" * 64, encoding="utf-8")
    (tmp_path / ("a" * 64 + ".json")).write_text(
        EXPECTED_PROFILE.model_dump_json(), encoding="utf-8"
    )
    # Sobrescribir get_cached_cv_profile para devolver EXPECTED_PROFILE directamente
    app.dependency_overrides[get_cached_cv_profile] = lambda: EXPECTED_PROFILE
    yield api_client
    app.dependency_overrides = {}
```

**Critical teardown rule:** `app.dependency_overrides = {}` after every fixture `yield`. Established anti-pattern from RESEARCH.md Pitfall 7.

---

### `tests/api/test_cv.py`, `tests/api/test_profile.py`, `tests/api/test_jobs.py` (test, request-response)

**Analog:** `tests/cv/test_parser.py`, `tests/dedup/test_dedup.py`

**Test file structure** (from `tests/cv/test_cache.py` and `tests/cv/test_parser.py` — consistent project convention):
- `from __future__ import annotations`
- Imports: `pytest`, then `app.*`, then test-local helpers
- Fixtures injected as function parameters
- Assertion messages in Spanish or brief English
- Test function names: `test_<endpoint>_<scenario>` (e.g., `test_process_jobs_ordena_por_score`, `test_process_jobs_ya_visto_segundo_run`)

**TestClient call pattern** (RESEARCH.md Code Examples):
```python
def test_get_profile(api_client):
    response = api_client.get("/profile")
    assert response.status_code == 200
    data = response.json()
    assert "datos_personales" in data

def test_parse_cv(api_client, sample_pdf_bytes):
    response = api_client.post(
        "/cv/parse",
        files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200

def test_process_requires_cv_profile(api_client):
    """Sin CVProfile cacheado → 404 con mensaje claro."""
    response = api_client.post("/jobs/process", json={"sources": []})
    assert response.status_code == 404
    assert "cv/parse" in response.json()["detail"].lower()
```

---

### `tests/storage/test_sqlite.py` (test, CRUD)

**Analog:** `tests/cv/test_cache.py` — file I/O tests with `tmp_path` and `monkeypatch.setenv`.

**tmp_path + monkeypatch pattern** (established in `tests/cv/test_cache.py`):
```python
def test_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    save_cached_profile(H, PROFILE)
    loaded = load_cached_profile(H)
    assert loaded == PROFILE
```

Apply same: `tmp_path` for SQLite DB path, no `monkeypatch.setenv` needed (pass path directly to `SQLiteStorage(str(tmp_path / "test.db"))`):

```python
# tests/storage/test_sqlite.py
import pytest
from app.storage.sqlite import SQLiteStorage
from app.models.schemas import ScoredJob, Job, JobScore, Desglose, Recommendation, RemoteJob


@pytest.fixture
def db(tmp_path):
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    return storage


def test_upsert_y_was_seen(db, ...):
    assert not db.was_seen("job-1")
    db.upsert_scored_jobs([...])
    assert db.was_seen("job-1")

def test_upsert_preserva_first_seen(db, ...):
    db.upsert_scored_jobs([item])
    first = db.get_history()[0]["first_seen"]
    db.upsert_scored_jobs([item])  # segundo upsert
    assert db.get_history()[0]["first_seen"] == first  # first_seen NO cambia

def test_get_history_paginacion(db, ...):
    # insertar 5, pedir limit=2 offset=2 → 2 resultados
    ...
```

---

## Shared Patterns

### Module header (applies to all new files)
**Source:** `app/cv/cache.py` lines 1-22, `app/scoring/scorer.py` lines 1-19
```python
"""
<Descripción en español de lo que hace el módulo>.

Expone:
- <función_publica>: <qué hace>
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)
```

Apply to: all `app/api/`, `app/storage/` files.

### Env var reading (lazy, never at module level)
**Source:** `app/cv/cache.py` lines 27-29
```python
def _cache_dir() -> Path:
    """Devuelve el directorio de caché actual, leyendo CV_CACHE_DIR en tiempo de llamada."""
    return Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
```

Apply to: `app/api/deps.py` (`get_cached_cv_profile`), `app/api/main.py` (inside `lifespan`).

### Deferred heavy imports (anti-torch invariant)
**Source:** `app/dedup/__init__.py` lines 105-109
```python
    from app.dedup.exact import exact_group  # noqa: PLC0415
    from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
```

Apply to: `app/api/deps.py` (`get_embedder`), `app/api/main.py` (storage imports inside `lifespan`).

### Error handling: domain exceptions → HTTPException
**Source:** `app/config/loader.py` lines 52-61 (ValueError/FileNotFoundError raises)
**Apply to:** All route handlers. Catch `ValueError` → 400, `FileNotFoundError` → 404, unexpected → let propagate (FastAPI returns 500).

### Pydantic v2 JSON round-trip
**Source:** `app/cv/cache.py` lines 75 and 106
```python
# Serializar: model.model_dump_json()
# Deserializar: Model.model_validate_json(json_str)
```

Apply to: `app/storage/sqlite.py` (`score_json` column), `app/api/deps.py` (`get_cached_cv_profile`).

### Structured logging (positional args, not f-strings)
**Source:** `app/dedup/__init__.py` lines 53-58, `app/scoring/scorer.py` lines 104-110
```python
logger.info(
    "normalize_jobs: source=%s in=%d ok=%d errors=%d",
    source, len(raw_offers), len(jobs), len(errors),
)
```

Apply to: all route handlers and storage methods. Log entry counts (entradas, duplicados detectados, puntuadas, errores).

### `__all__` export list in package `__init__.py`
**Source:** `app/dedup/__init__.py` line 25
```python
__all__ = ["normalize_jobs", "deduplicate"]
```

Apply to: `app/storage/__init__.py` (export `Storage`, `get_storage_backend`).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `app/api/main.py` | config | request-response | No existing FastAPI app in codebase — greenfield. Use RESEARCH.md Pattern 1 verbatim for lifespan + router registration. |
| `app/api/routes/jobs.py` (orchestration logic) | controller | request-response | No existing orchestration combining normalize+dedup+score+persist in a single function. Pattern assembled from individual analogs (dedup/__init__.py + scoring/scorer.py + storage). |

For both files, RESEARCH.md Patterns 1-5 are the authoritative references, cross-validated with the existing codebase conventions above.

---

## Metadata

**Analog search scope:** `app/cv/`, `app/dedup/`, `app/scoring/`, `app/config/`, `app/models/`, `tests/`
**Files scanned:** 22 Python files (full reads: 12; targeted reads: 0 — all files were under 200 lines)
**Pattern extraction date:** 2026-05-22
