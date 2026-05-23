# Phase 5: Observabilidad, Robustez y Docs n8n - Pattern Map

**Mapped:** 2026-05-23
**Files analyzed:** 12 new/modified files
**Analogs found:** 11 / 12

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/obs/__init__.py` | utility (package init) | — | `app/dedup/__init__.py` (re-exports + docstring) | exact |
| `app/obs/logging_config.py` | utility | — | stdlib `logging` usage in `app/api/main.py` + `app/api/routes/jobs.py` | role-match |
| `app/obs/tracing.py` | utility (optional dep stub) | request-response | `app/dedup/embedder.py` (`_ensure_loaded` lazy import pattern) + `app/dedup/__init__.py` (deferred imports with `# noqa: PLC0415`) | exact |
| `app/errors.py` | utility (domain exceptions) | — | no direct analog — simple `Exception` subclasses | no-analog |
| `app/api/main.py` (modify) | config/wiring | request-response | itself — add `configure_logging()` to lifespan + `@app.exception_handler` registrations | self-modify |
| `app/scoring/llm.py` (modify) | service | request-response | `app/dedup/__init__.py` deferred import pattern; wrap `assess_job` with `trace_llm` | role-match |
| `app/cv/llm_client.py` (modify) | service | request-response | same as `app/scoring/llm.py` — same `client.messages.create` call shape | exact |
| `app/api/routes/jobs.py` (modify) | controller | request-response | itself — add `llm_calls` counter to existing loop in `process_jobs` | self-modify |
| `tests/obs/__init__.py` | test | — | `tests/__init__.py` (empty package init) | exact |
| `tests/obs/test_logging.py` | test | — | `tests/api/conftest.py` + existing test files (caplog pattern) | role-match |
| `tests/obs/test_tracing.py` | test | — | `tests/conftest.py` (mock pattern + `monkeypatch.setenv`) | role-match |
| `tests/api/test_exception_handlers.py` | test | request-response | `tests/api/conftest.py` (`api_client` fixture + `TestClient`) | exact |
| `tests/api/test_examples.py` | test | request-response | `tests/api/conftest.py` (`api_client_with_cv` fixture pattern) | exact |
| `examples/arbeitnow_offers.json` | documentation/DX | — | `tests/conftest.py` `sample_arbeitnow_payload` fixture (canonical field reference) | role-match |
| `examples/generic_offers.json` | documentation/DX | — | `tests/conftest.py` `sample_generic_payload` fixture | role-match |
| `examples/process_request.json` | documentation/DX | — | `05-RESEARCH.md` exact `/jobs/process` contract section | role-match |

---

## Pattern Assignments

### `app/obs/__init__.py` (utility, package init)

**Analog:** `app/dedup/__init__.py` lines 1-25

**Package docstring + re-exports pattern:**
```python
# app/dedup/__init__.py lines 1-15
"""
Paquete de deduplicación y normalización de ofertas de empleo.

Fachada pública:
  - normalize_jobs: ...
  - deduplicate: ...
"""
from __future__ import annotations

import logging
...
__all__ = ["normalize_jobs", "deduplicate"]
```

**Apply:** Same structure — brief module docstring, `from __future__ import annotations`, re-export the public symbols (`configure_logging`, `trace_llm`) with `__all__` if desired, or leave empty with just a docstring. Project convention is to keep `__init__.py` files non-empty with a clear docstring.

---

### `app/obs/logging_config.py` (utility, configure_logging)

**Analog:** `app/api/main.py` lines 1-23 + `app/api/routes/jobs.py` lines 1-27

**Imports pattern** (`app/api/main.py` lines 13-23):
```python
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)
```

**Existing logging call pattern** (`app/api/main.py` lines 41-42):
```python
logger.info("lifespan: usando SQLiteStorage en %s", db_path)
```

**Existing structured log format** (`app/api/routes/jobs.py` lines 122-128):
```python
logger.info(
    "normalize_endpoint: source=%s in=%d ok=%d errors=%d",
    body.source,
    len(body.offers),
    len(jobs),
    len(errors),
)
```

**Core pattern to implement** (from `05-RESEARCH.md` Pattern 3):
```python
import logging
import sys

def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logging con formato key=value consistente.
    Idempotente: si el root logger ya tiene handlers, no duplica."""
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado — Pitfall 3 en RESEARCH.md
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    ))
    root.addHandler(handler)
    root.setLevel(level)
```

**Wire into lifespan** (`app/api/main.py` lines 27-43 — the lifespan to modify):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415
    # ADD BEFORE storage init:
    from app.obs.logging_config import configure_logging  # noqa: PLC0415
    configure_logging()
    ...
```

---

### `app/obs/tracing.py` (utility, optional-dep no-op stub)

**Primary analog:** `app/dedup/embedder.py` lines 68-80 (`_ensure_loaded` — lazy import of heavy dep)

**Lazy import with `# noqa: PLC0415`** (`app/dedup/embedder.py` lines 76-79):
```python
def _ensure_loaded(self) -> None:
    if self._model is None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        logger.info("Cargando modelo BAAI/bge-m3 (primera llamada)...")
        self._model = SentenceTransformer("BAAI/bge-m3")
```

**Secondary analog:** `app/dedup/__init__.py` lines 105-109 (deferred imports in function body):
```python
# Imports deferidos: evitan arrastrar numpy/torch al importar app.dedup (T-02-11)
from app.dedup.exact import exact_group  # noqa: PLC0415
from app.dedup.semantic import semantic_cluster  # noqa: PLC0415
from app.dedup.merger import merge_group  # noqa: PLC0415
from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
```

**Core pattern to implement** (from `05-RESEARCH.md` Pattern 1):
```python
# app/obs/tracing.py
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator

_LANGFUSE_CONFIGURED = (
    bool(os.environ.get("LANGFUSE_PUBLIC_KEY"))
    and bool(os.environ.get("LANGFUSE_SECRET_KEY"))
)

@contextmanager
def trace_llm(name: str, **meta: Any) -> Generator[None, None, None]:
    """Context manager que traza una llamada LLM con Langfuse (si está disponible).

    No-op silencioso cuando langfuse no instalado o env vars ausentes.
    """
    if not _LANGFUSE_CONFIGURED:
        yield
        return

    try:
        from langfuse import Langfuse  # noqa: PLC0415 — import perezoso/opcional
    except ImportError:
        yield
        return

    lf = Langfuse()
    with lf.start_as_current_observation(name=name, as_type="generation", metadata=meta):
        yield
```

**Key design notes from analogs:**
- The `# noqa: PLC0415` comment is the project convention for all non-top-level imports — copy it exactly.
- The module docstring of `app/dedup/embedder.py` (lines 1-17) explicitly names the invariant ("Importar este módulo NO debe importar torch"). Mirror this: "Importar este módulo NO debe importar langfuse".
- Double-guard: check env vars first (`_LANGFUSE_CONFIGURED`), then `try/except ImportError` — this is the established pattern for optional deps in this project.

---

### `app/errors.py` (utility, domain exception hierarchy)

**No direct analog** in the codebase — the project currently uses bare `Exception` catches (`except Exception as exc: # noqa: BLE001`). The exception hierarchy is new.

**Existing exception surface to align with** (`app/api/routes/jobs.py` lines 164, 227):
```python
except Exception as exc:  # noqa: BLE001
    logger.warning("process_jobs: error puntuando job=%s: %s", job.id, exc)
```

**Pattern from `05-RESEARCH.md` Code Examples:**
```python
class BuscadorError(Exception):
    """Base exception para todos los errores de dominio de BuscadorDeEmpleo."""

class CVParseError(BuscadorError):
    """Error durante el parseo del CV (extracción de texto o llamada LLM)."""

class NormalizationError(BuscadorError):
    """Error durante la normalización de una oferta."""

class ScoringError(BuscadorError):
    """Error durante el scoring de una oferta."""

class StorageError(BuscadorError):
    """Error durante operaciones de persistencia (SQLite)."""
```

**Design constraint:** Keep classes minimal — `class CVParseError(BuscadorError): pass` with only a docstring. No extra fields needed for this phase. `str(exc)` is sufficient for the exception handler message.

---

### `app/api/main.py` (modify — add configure_logging + exception handlers)

**Analog:** itself (lines 1-57) — add to existing lifespan and app instance.

**Existing lifespan pattern to extend** (lines 27-45):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415
    db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    logger.info("lifespan: usando SQLiteStorage en %s", db_path)
    app.state.storage = storage
    yield
    logger.info("lifespan: servicio detenido")
```

**Add `configure_logging()` as first call in lifespan** (deferred import pattern from lines 36-37):
```python
from app.obs.logging_config import configure_logging  # noqa: PLC0415
configure_logging()
```

**Exception handler registration pattern** (add after `app = FastAPI(...)`, before `app.include_router()`):
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from app.errors import CVParseError, NormalizationError, ScoringError, StorageError

@app.exception_handler(CVParseError)
async def cv_parse_error_handler(request: Request, exc: CVParseError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"type": "CVParseError", "message": str(exc)}})

@app.exception_handler(NormalizationError)
async def normalization_error_handler(request: Request, exc: NormalizationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"type": "NormalizationError", "message": str(exc)}})

@app.exception_handler(ScoringError)
async def scoring_error_handler(request: Request, exc: ScoringError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"type": "ScoringError", "message": str(exc)}})

@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": {"type": "StorageError", "message": str(exc)}})

@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": {"type": type(exc).__name__, "message": "Internal server error"}})
```

**CRITICAL ordering:** Specific handlers must be registered before the generic `Exception` handler. Register them between `app = FastAPI(...)` and `app.include_router(...)`.

---

### `app/scoring/llm.py` (modify — wrap assess_job with trace_llm)

**Analog:** `app/cv/llm_client.py` lines 30-61 (identical `client.messages.create` shape)

**Existing assess_job call point** (lines 178-199 — the exact location to wrap):
```python
def assess_job(job, cv_profile, user_profile, client):
    model = os.getenv("ANTHROPIC_MODEL_SCORING", "claude-sonnet-4-6")
    # system prompt FIJO — sin interpolación de contenido externo (T-03-08)
    return client.messages.create(
        model=model,
        max_tokens=2048,
        system=(...),
        messages=[{"role": "user", "content": _build_prompt(...)}],
        response_model=LLMJobAssessment,
        max_retries=2,
    )
```

**Wrap pattern** (add import at top of file, wrap the return):
```python
from app.obs.tracing import trace_llm  # new import

def assess_job(job, cv_profile, user_profile, client):
    model = os.getenv("ANTHROPIC_MODEL_SCORING", "claude-sonnet-4-6")
    with trace_llm("assess_job", job_id=job.id, model=model):
        return client.messages.create(
            model=model,
            max_tokens=2048,
            system=(...),
            messages=[{"role": "user", "content": _build_prompt(...)}],
            response_model=LLMJobAssessment,
            max_retries=2,
        )
```

**Note:** The function signature does not change. The existing tests mock `client.messages.create` directly and will continue to work because `trace_llm` is a no-op when env vars are absent (which they are in tests).

---

### `app/cv/llm_client.py` (modify — wrap extract_cv_profile with trace_llm)

**Analog:** `app/scoring/llm.py` lines 151-199 (same `client.messages.create` surface)

**Existing extract_cv_profile call point** (lines 30-61 — the exact location to wrap):
```python
def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
    return client.messages.create(
        model=model,
        max_tokens=4096,
        system=(...),
        messages=[{"role": "user", "content": f"Extrae el CVProfile..."}],
        response_model=CVProfile,
        max_retries=2,
    )
```

**Wrap pattern** (identical to assess_job wrap):
```python
from app.obs.tracing import trace_llm  # new import

def extract_cv_profile(raw_text: str, client: instructor.Instructor) -> CVProfile:
    model = os.getenv("ANTHROPIC_MODEL_CV", "claude-haiku-4-5-20251001")
    with trace_llm("extract_cv_profile", model=model):
        return client.messages.create(...)
```

---

### `app/api/routes/jobs.py` (modify — add llm_calls counter)

**Analog:** itself — the existing scoring loop at lines 220-243.

**Existing loop without counter** (lines 221-243):
```python
scored: list[ScoredJobConVisto] = []
for job in unique_jobs:
    ya_visto = storage.was_seen(job.id)
    try:
        score = score_job(job, cv_profile, user_profile, client=scoring_client)
        scored.append(ScoredJobConVisto(job=job, score=score, ya_visto=ya_visto))
    except Exception as exc:  # noqa: BLE001
        all_errors.append({"job_id": job.id, "error": str(exc)})
        logger.warning("process_jobs: error puntuando job=%s: %s", job.id, exc)

# 5. Ordenar por score_total DESC
scored.sort(key=lambda s: s.score.score_total, reverse=True)

logger.info(
    "process_jobs: entradas=%d unicos=%d puntuados=%d errores=%d",
    sum(len(b.offers) for b in body.sources),
    len(unique_jobs),
    len(scored),
    len(all_errors),
)
```

**Add llm_calls counter** — minimal diff:
```python
scored: list[ScoredJobConVisto] = []
llm_calls = 0  # ADD THIS
for job in unique_jobs:
    ya_visto = storage.was_seen(job.id)
    try:
        score = score_job(job, cv_profile, user_profile, client=scoring_client)
        llm_calls += 1  # ADD THIS — exactly 1 LLM call per successful score_job
        scored.append(ScoredJobConVisto(job=job, score=score, ya_visto=ya_visto))
    except Exception as exc:  # noqa: BLE001
        all_errors.append({"job_id": job.id, "error": str(exc)})
        logger.warning("process_jobs: error puntuando job=%s: %s", job.id, exc)

scored.sort(key=lambda s: s.score.score_total, reverse=True)

logger.info(
    "process_jobs: entradas=%d unicos=%d puntuados=%d llm_calls=%d errores=%d",  # ADD llm_calls=%d
    sum(len(b.offers) for b in body.sources),
    len(unique_jobs),
    len(scored),
    llm_calls,   # ADD THIS
    len(all_errors),
)
```

---

### `tests/obs/test_logging.py` (test — OBS-01)

**Analog:** existing test files pattern from `tests/api/conftest.py` + `tests/conftest.py`

**Key patterns to copy:**
- `from __future__ import annotations` header (used in all app + test files)
- `import pytest` with `caplog` fixture for log capture
- No `TestClient` needed — unit test, import `configure_logging` directly

**caplog pattern** (standard pytest pattern seen in project's test style):
```python
import pytest
from app.obs.logging_config import configure_logging

def test_configure_logging_idempotent(caplog):
    """configure_logging() llamado dos veces NO duplica handlers."""
    import logging
    root = logging.getLogger()
    initial_handler_count = len(root.handlers)
    configure_logging()
    configure_logging()  # segunda llamada — no debe añadir handler
    assert len(root.handlers) == initial_handler_count or len(root.handlers) == initial_handler_count + 1
```

---

### `tests/obs/test_tracing.py` (test — OBS-02)

**Analog:** `tests/conftest.py` lines 129-138 (mock_llm_client — `MagicMock` pattern) + `monkeypatch.setenv` usage seen throughout test suite

**Key patterns:**
- `monkeypatch.setenv` to set/unset `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
- `importlib.reload` to re-evaluate `_LANGFUSE_CONFIGURED` after patching env vars
- `unittest.mock.patch` to mock `langfuse.Langfuse` import for the "installed+configured" path

**No-op test pattern:**
```python
import importlib
import app.obs.tracing as tracing_module
from app.obs.tracing import trace_llm

def test_trace_llm_noop_without_env_vars(monkeypatch):
    """trace_llm es no-op cuando las env vars de Langfuse no están configuradas."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    importlib.reload(tracing_module)  # re-evalúa _LANGFUSE_CONFIGURED
    from app.obs.tracing import trace_llm as fresh_trace_llm
    executed = []
    with fresh_trace_llm("test_op"):
        executed.append(True)
    assert executed == [True]  # el bloque se ejecutó sin excepción
```

---

### `tests/api/test_exception_handlers.py` (test — OBS-03)

**Analog:** `tests/api/conftest.py` lines 72-108 (`api_client` fixture — `TestClient` + `dependency_overrides`)

**Imports pattern** (from `tests/api/conftest.py` lines 1-31):
```python
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from app.api.main import app
from tests.conftest import EXPECTED_ASSESSMENT, EXPECTED_PROFILE, EXPECTED_USER_PROFILE
```

**TestClient pattern for exception handler tests:**
```python
# Uses api_client fixture from tests/api/conftest.py
def test_cv_parse_error_returns_422(api_client):
    """CVParseError propagada hasta el router → JSONResponse 422 con envelope."""
    # Need a route that raises CVParseError — either mock a dep or add a test route
    ...
```

**Note:** The exception handlers intercept exceptions that propagate to router level. To test them cleanly, override a `Depends` to raise the typed exception, or add a minimal test endpoint. See `api_client` fixture pattern (lines 99-108) for `dependency_overrides` approach.

---

### `tests/api/test_examples.py` (test — DOC-03)

**Analog:** `tests/api/conftest.py` lines 111-128 (`api_client_with_cv` fixture)

**Test pattern using api_client_with_cv:**
```python
# tests/api/test_examples.py
import json
from pathlib import Path

def test_examples_arbeitnow_valid_json():
    """examples/arbeitnow_offers.json es JSON válido y parseable."""
    path = Path("examples/arbeitnow_offers.json")
    assert path.exists()
    data = json.loads(path.read_text())
    assert isinstance(data, list)

def test_examples_process_request_accepted(api_client_with_cv):
    """POST /jobs/process acepta el payload de examples/process_request.json."""
    payload = json.loads(Path("examples/process_request.json").read_text())
    resp = api_client_with_cv.post("/jobs/process", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert "errors" in body
```

---

### `examples/arbeitnow_offers.json` (documentation, DX)

**Canonical reference:** `tests/conftest.py` lines 194-215 (`sample_arbeitnow_payload` fixture)

**Field shape to use:**
```json
[
  {
    "slug": "ai-engineer-techcorp-12345",
    "company_name": "TechCorp GmbH",
    "title": "AI Engineer",
    "description": "<h2>About</h2><p>We build AI systems with Python and LLMs.</p>",
    "remote": false,
    "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
    "tags": ["Engineering"],
    "job_types": ["berufserfahren"],
    "location": "Berlin",
    "created_at": 1716350400
  }
]
```

---

### `examples/generic_offers.json` (documentation, DX)

**Canonical reference:** `tests/conftest.py` lines 218-235 (`sample_generic_payload` fixture)

**Field shape to use:**
```json
[
  {
    "employer": "OpenAI Inc.",
    "job_title": "ML Engineer",
    "city": "Remote",
    "body": "We are looking for a motivated ML Engineer to join our team.",
    "apply_url": "https://openai.com/careers/ml-engineer",
    "is_remote": true
  }
]
```

---

### `examples/process_request.json` (documentation, DX)

**Canonical reference:** `05-RESEARCH.md` lines 400-434 (exact `/jobs/process` contract)

The payload wraps both source formats into the `ProcessRequest` shape:
```json
{
  "sources": [
    {
      "source": "arbeitnow",
      "offers": [/* contents of arbeitnow_offers.json */]
    },
    {
      "source": "generic",
      "offers": [/* contents of generic_offers.json */]
    }
  ]
}
```

---

## Shared Patterns

### Deferred / Optional Import Pattern
**Source:** `app/dedup/embedder.py` lines 76-79 + `app/dedup/__init__.py` lines 105-109
**Apply to:** `app/obs/tracing.py` (langfuse import), `app/api/main.py` lifespan (`configure_logging` import), `tests/api/conftest.py` (`FakeEmbedder` import)

```python
from langfuse import Langfuse  # noqa: PLC0415 — import perezoso/opcional
```

The `# noqa: PLC0415` suppression comment is the established project convention for all non-top-level imports. Copy it verbatim.

### Structured Logging (key=value in logger args)
**Source:** `app/api/routes/jobs.py` lines 122-128, `app/dedup/__init__.py` lines 53-59, `app/api/main.py` lines 41-42
**Apply to:** All new log statements in `app/obs/`, new log in `process_jobs`

```python
logger.info(
    "normalize_jobs: source=%s in=%d ok=%d errors=%d",
    source, len(raw_offers), len(jobs), len(errors),
)
```

Pattern: `"scope: key1=%s key2=%d key3=%d"` positional args — grep-able without a parser.

### from __future__ import annotations
**Source:** `app/api/main.py` line 13, `app/api/routes/jobs.py` line 9, `tests/api/conftest.py` line 1
**Apply to:** All new Python files in this phase

```python
from __future__ import annotations
```

Every new module in the project starts with this line.

### TestClient + dependency_overrides + teardown
**Source:** `tests/api/conftest.py` lines 72-108
**Apply to:** `tests/api/test_exception_handlers.py`, `tests/api/test_examples.py`

```python
# Use api_client or api_client_with_cv fixtures from tests/api/conftest.py
# Never create a new TestClient — reuse the fixture
# If you need to raise a specific exception from a Depends, add it to dependency_overrides:
app.dependency_overrides[get_cached_cv_profile] = lambda: EXPECTED_PROFILE
# ALWAYS reset after yield:
app.dependency_overrides = {}  # CRITICO: reset tras yield — previene contaminación
```

### MagicMock pattern for LLM clients
**Source:** `tests/conftest.py` lines 128-138 + `tests/api/conftest.py` lines 87-89
**Apply to:** `tests/obs/test_tracing.py` (mock Langfuse client if testing the active path)

```python
mock_client = MagicMock()
mock_client.messages.create.return_value = EXPECTED_PROFILE  # or EXPECTED_ASSESSMENT
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `app/errors.py` | utility (exceptions) | — | No typed exception hierarchy exists in the codebase yet. All layers use bare `except Exception`. Pattern from `05-RESEARCH.md` Code Examples section is authoritative. |

---

## Metadata

**Analog search scope:** `app/`, `tests/`, `.planning/phases/05-observabilidad-robustez-docs/`
**Files scanned:** 11 (main.py, jobs.py, llm.py, llm_client.py, dedup/__init__.py, embedder.py, schemas.py, tests/conftest.py, tests/api/conftest.py, 05-CONTEXT.md, 05-RESEARCH.md)
**Pattern extraction date:** 2026-05-23
