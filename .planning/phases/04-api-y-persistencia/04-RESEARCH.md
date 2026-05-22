# Phase 4: API y Persistencia - Research

**Researched:** 2026-05-22
**Domain:** FastAPI (app layer) + stdlib sqlite3 (persistence) + Python Protocol (storage abstraction)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**App FastAPI (app/api/)**
- New deps: `fastapi`, `uvicorn[standard]`, `python-multipart`. Added with `uv add`.
- Structure: `app/api/main.py` creates `FastAPI()` and includes routers; routers by concern in `app/api/routes/`: `cv.py`, `profile.py`, `jobs.py`.
- Runnable with `uvicorn app.api.main:app`.

**Endpoints (n8n contract — clean JSON, clear HTTP codes)**
- POST /cv/parse: multipart UploadFile → `parse_cv` → CVProfile cached. (API-01)
- GET /profile: `load_user_profile` → UserProfile. (API-02)
- POST /jobs/normalize: `{source: str, offers: [dict]}` → `{jobs: [Job], errors: [dict]}`. (API-03)
- POST /jobs/score: `{jobs: [Job]}` → `[ScoredJob]` using cached CVProfile + UserProfile. (API-05)
- POST /jobs/process: `{sources: [{source, offers}]}` → normalize + dedup + score → `[ScoredJob]` ordered by score_total desc, ya_visto marked, persisted. Main n8n endpoint. (API-04)
- GET /jobs/history: saved jobs with score and date (simple paginable). (API-06)
- Contract (API-07): Pydantic request/response models; HTTP 400/422/404/500; one malformed offer does NOT kill the batch.

**CVProfile dependency for scoring**
- /jobs/score and /jobs/process need a cached CVProfile.
- If no CVProfile in cache → 4xx with clear message to call /cv/parse first.

**Persistence (app/storage/) — SQLite-first**
- `Storage` Protocol/ABC abstraction.
- `SQLiteStorage` complete implementation with stdlib `sqlite3` (NO SQLAlchemy).
- Table: `jobs` (id PK, title, company, location, remote, url, source, score_total, recommendation, score_json, first_seen, last_seen, notified/seen flag).
- `SupabaseStorage` skeleton implementing the same Protocol; selected when SUPABASE_URL/SUPABASE_KEY in env; otherwise SQLiteStorage.
- SQLite path configurable via env (`SQLITE_DB_PATH`, default `data/jobs.db`).

**Dependency injection (testability)**
- LLM client (scoring + cv parse), Embedder (dedup), and Storage injected via FastAPI `Depends`.
- Tests use `TestClient` with `app.dependency_overrides` → zero network, zero BGE-M3 download.

**Tests**
- `tests/api/` with FastAPI TestClient. Each endpoint: happy path + error. /jobs/process end-to-end with mocked LLM+embedder and temp SQLite: order by score_total, ya_visto on second run, history.
- `tests/storage/` for SQLiteStorage (upsert, was_seen, history) with temp DB.

### Claude's Discretion
- Exact router split and request/response model names.
- Exact SQLite table schema and score_json format.
- Degree of SupabaseStorage skeleton implementation (minimum: Protocol + selection + NotImplemented/partial).
- Whether /jobs/score|process also accept CV in body in addition to using cache.

### Deferred Ideas (OUT OF SCOPE)
- Full real Supabase implementation + pgvector (skeleton now; real when connecting).
- Langfuse observability around scoring (Phase 5).
- README + n8n integration section (Phase 5).
- API authentication (out of scope v1 — personal tool).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | POST /cv/parse — upload PDF (multipart), return and cache CVProfile | UploadFile + await file.read() pattern; reuse parse_cv() from Phase 1 |
| API-02 | GET /profile — return loaded UserProfile | load_user_profile() already works; simple Depends wrapper |
| API-03 | POST /jobs/normalize — receive raw offers + source, return Jobs | normalize_jobs() already works; define NormalizeRequest/NormalizeResponse Pydantic models |
| API-04 | POST /jobs/process — normalize+dedup+score, order by score_total, mark ya_visto, persist | Orchestration endpoint; needs Storage Depends; uses all Phase 1-3 functions |
| API-05 | POST /jobs/score — granular: score a list of already-normalized Jobs | score_job() already works; needs cached CVProfile dependency |
| API-06 | GET /jobs/history — stored jobs with score and date | SQLiteStorage.get_history(); paginable via skip/limit query params |
| API-07 | n8n contract — clean JSON, clear HTTP codes, batch resilient | HTTPException patterns; existing resilience from normalize_jobs() |
| STORE-01 | SQLite-first persistence, upgrade to Supabase; credentials from env | Protocol + SQLiteStorage (stdlib sqlite3) + SupabaseStorage skeleton |
| STORE-02 | Store jobs with date (history for evolution) | first_seen / last_seen columns in SQLite; upsert pattern |
| STORE-03 | ya_visto control between runs so n8n doesn't repeat jobs | notified/seen flag in DB; was_seen() / mark_seen() protocol methods |
</phase_requirements>

---

## Summary

Phase 4 wires together three phases of already-built logic (CV parsing, normalization+dedup, scoring) into a FastAPI HTTP service and adds a SQLite-backed persistence layer. The research confirms that all required FastAPI patterns (lifespan, APIRouter, UploadFile, Depends, dependency_overrides) are well-documented and straightforward. The main technical decisions — SQLite-first with a `Protocol` abstraction, lazy embedder import to avoid torch-on-startup, and injecting LLM/embedder/storage via `Depends` — are all validated and consistent with how Phases 1-3 were built.

The biggest implementation nuances are: (1) the CVProfile "cache dependency" pattern — a `Depends` that reads from disk cache and raises HTTP 404 if empty; (2) sqlite3 thread safety with FastAPI's thread pool (sync endpoints run in a thread pool, requiring `check_same_thread=False` on the connection); (3) `await file.read()` for UploadFile (async, mandatory); (4) `httpx` must be added as a dev dependency for `TestClient` to work; and (5) keeping the BGE-M3 embedder import lazy so the app is importable without triggering torch.

**Primary recommendation:** Use sync endpoints (not `async def`) for any endpoint that calls sqlite3 or the scoring/dedup logic (which is CPU-bound/blocking). FastAPI runs sync endpoints in a threadpool automatically, avoiding event-loop blocking. Use `check_same_thread=False` with a per-request or thread-local SQLite connection.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTTP routing + request validation | API (FastAPI) | — | FastAPI handles via Pydantic v2 models + automatic 422 |
| CV upload + parse | API (FastAPI) | CV layer (app/cv/) | API receives bytes, delegates to parse_cv() |
| Profile loading | API (FastAPI) | Config layer (app/config/) | API exposes GET, delegates to load_user_profile() |
| Job normalization | API (FastAPI) | Dedup layer (app/dedup/) | API wraps normalize_jobs() |
| Deduplication | API (FastAPI) | Dedup layer (app/dedup/) | API calls deduplicate() injecting FakeEmbedder in tests |
| Scoring | API (FastAPI) | Scoring layer (app/scoring/) | API calls score_job() injecting mock LLM client in tests |
| Persistence / history | Storage (app/storage/) | API (FastAPI) | SQLiteStorage is owned by storage layer; API injects it via Depends |
| ya_visto tracking | Storage (app/storage/) | API (FastAPI) | was_seen()/mark_seen() live in storage; API reads the flag for response |
| Dependency injection seams | API (FastAPI) | — | FastAPI Depends + app.dependency_overrides |
| Test isolation | Test layer | — | dependency_overrides replaces LLM/embedder/storage; no network |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | 0.136.1 | HTTP framework, routing, validation, DI | Project spec; current stable release [VERIFIED: PyPI 2026-05-22] |
| uvicorn[standard] | 0.47.0 | ASGI server (includes websockets, httptools) | Project spec; standard extra includes performance deps [VERIFIED: PyPI 2026-05-22] |
| python-multipart | 0.0.29 | Multipart form data parsing for UploadFile | Required by FastAPI for file upload endpoints [VERIFIED: PyPI 2026-05-22] |
| httpx | 0.28.1 | HTTP client; TestClient transport layer | Required by starlette TestClient (not bundled with fastapi by default) [VERIFIED: PyPI 2026-05-22] |
| stdlib sqlite3 | (bundled, Python 3.13) | Persistence — jobs table, history, ya_visto | Project spec; zero deps, avoids SQLAlchemy weight |
| typing.Protocol | (stdlib, Python 3.8+) | Storage abstraction without inheritance | Structural subtyping for Storage/SQLiteStorage/SupabaseStorage |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| starlette | (pinned by fastapi) | TestClient source; ASGI primitives | Import TestClient from `fastapi.testclient` (re-exports starlette's) |
| python-dotenv | already in pyproject.toml | Read env vars (.env) for SQLITE_DB_PATH, SUPABASE_URL, etc. | Already installed; use at app startup |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib sqlite3 | aiosqlite | aiosqlite is truly async but adds a dep; sync sqlite3 in sync endpoints via threadpool is simpler and sufficient for single-user tool |
| stdlib sqlite3 | SQLAlchemy | Project spec explicitly forbids SQLAlchemy; sqlite3 is enough for this scale |
| Protocol | ABC (abstract base class) | ABC requires explicit inheritance; Protocol uses structural subtyping (duck-typing friendly), which means SupabaseStorage/FakeStorage don't need to import the Protocol |

**Installation (new deps for Phase 4):**
```bash
uv add fastapi "uvicorn[standard]" python-multipart httpx
```

**Version verification (run before writing):**
```bash
# Verified 2026-05-22:
# fastapi: 0.136.1  | uvicorn: 0.47.0  | python-multipart: 0.0.29  | httpx: 0.28.1
```
[VERIFIED: PyPI registry via curl 2026-05-22]

---

## Architecture Patterns

### System Architecture Diagram

```
n8n (external)
    │
    │  POST /jobs/process  {sources: [{source, offers}]}
    ▼
┌──────────────────────────────────────────────────┐
│  FastAPI app  (app/api/main.py)                  │
│  ┌────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │ cv.py      │  │ profile.py  │  │ jobs.py   │ │
│  │ POST /cv/  │  │ GET /profile│  │ POST      │ │
│  │ parse      │  │             │  │ /normalize │ │
│  └────┬───────┘  └──────┬──────┘  │ /score    │ │
│       │                 │         │ /process  │ │
│  Depends: LLM client    │         │ /history  │ │
│  Depends: Storage       │         └────┬──────┘ │
└────────────────────────────────────────┼────────┘
         │                  │            │
         ▼                  ▼            ▼
   app/cv/          app/config/    app/dedup/
   parse_cv()       load_user_     normalize_jobs()
   (cache-first)    profile()      deduplicate()
                                   (Embedder injected)
                                        │
                                        ▼
                                   app/scoring/
                                   score_job()
                                   (LLM client injected)
                                        │
                                        ▼
                                   app/storage/
                                   Storage Protocol
                                   ├── SQLiteStorage  (default)
                                   └── SupabaseStorage (if SUPABASE_URL set)
                                        │
                                        ▼
                                   data/jobs.db  (SQLite)
```

### Recommended Project Structure

```
app/
├── api/
│   ├── __init__.py
│   ├── main.py          # FastAPI(), lifespan, include_router()
│   ├── deps.py          # Depends factories: get_llm_client, get_embedder, get_storage, get_cv_profile
│   └── routes/
│       ├── __init__.py
│       ├── cv.py        # POST /cv/parse
│       ├── profile.py   # GET /profile
│       └── jobs.py      # POST /normalize, /score, /process; GET /history, /health
├── storage/
│   ├── __init__.py
│   ├── protocol.py      # class Storage(Protocol)
│   ├── sqlite.py        # SQLiteStorage (stdlib sqlite3, complete)
│   └── supabase.py      # SupabaseStorage skeleton
└── ... (cv/, dedup/, scoring/, config/, models/ already exist)

tests/
├── api/
│   ├── __init__.py
│   ├── conftest.py      # client fixture: TestClient + dependency_overrides
│   ├── test_cv.py
│   ├── test_profile.py
│   └── test_jobs.py
└── storage/
    ├── __init__.py
    └── test_sqlite.py
```

### Pattern 1: FastAPI App with Lifespan + APIRouter

**What:** The `lifespan` context manager initializes shared resources (Storage instance) on startup and cleans up on shutdown. Routers are included in `main.py`.

**When to use:** Any resource that is expensive to create per-request (DB connection manager, singleton config) and needs cleanup.

```python
# app/api/main.py
# Source: https://fastapi.tiangolo.com/advanced/events/  [CITED]
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.routes import cv, profile, jobs
from app.storage.sqlite import SQLiteStorage
from app.storage.supabase import SupabaseStorage
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: select and init storage
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        storage = SupabaseStorage()
    else:
        db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
        storage = SQLiteStorage(db_path)
        storage.init_db()
    app.state.storage = storage
    yield
    # Shutdown: cleanup if needed

app = FastAPI(lifespan=lifespan)
app.include_router(cv.router)
app.include_router(profile.router)
app.include_router(jobs.router)
```

### Pattern 2: Dependency Factories (app/api/deps.py)

**What:** Central file of `Depends`-compatible functions that read from `request.app.state` or build lazy instances. This is the seam for `dependency_overrides` in tests.

**When to use:** Any cross-cutting resource: LLM client, Embedder, Storage, cached CVProfile.

```python
# app/api/deps.py
# Source: FastAPI docs + established project pattern (Phases 1-3) [CITED]
from fastapi import Request, HTTPException
from app.cv.cache import load_cached_profile, pdf_hash
from app.cv.llm_client import build_instructor_client as _build_cv_client
from app.scoring.llm import build_instructor_client as _build_scoring_client
from app.models.schemas import CVProfile
import os

def get_storage(request: Request):
    """Reads storage singleton from app.state (set in lifespan)."""
    return request.app.state.storage

def get_cv_llm_client():
    """LLM client for CV parsing. Override in tests."""
    return _build_cv_client()

def get_scoring_llm_client():
    """LLM client for scoring. Override in tests."""
    return _build_scoring_client()

def get_embedder():
    """BGE-M3 embedder. Import deferred — never triggers torch at import time."""
    from app.dedup.embedder import BgeM3Embedder  # deferred import (anti-torch pitfall)
    return BgeM3Embedder()

def get_cached_cv_profile() -> CVProfile:
    """Returns the latest cached CVProfile or raises 404.
    
    The cache key is the most recent PDF hash stored in CV_CACHE_DIR.
    If the cache directory is empty, instructs the caller to POST /cv/parse first.
    """
    # Load the first .json found in CV_CACHE_DIR (single-user tool — one active CV)
    import os
    from pathlib import Path
    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    files = sorted(cache_dir.glob("*.json")) if cache_dir.exists() else []
    if not files:
        raise HTTPException(
            status_code=404,
            detail="No CVProfile cached. Call POST /cv/parse first."
        )
    return CVProfile.model_validate_json(files[-1].read_text(encoding="utf-8"))
```

**IMPORTANT NOTE on get_cached_cv_profile:** The CV cache (from Phase 1) stores one file per PDF hash. For a single-user tool, reading the most recently-modified file is the simplest approach. An alternative is to store the last hash in a metadata file or app.state after /cv/parse. The planner should choose one and be explicit.

### Pattern 3: UploadFile (POST /cv/parse)

**What:** Receive a PDF via multipart/form-data. `await file.read()` returns bytes.

**When to use:** Any file upload endpoint.

```python
# app/api/routes/cv.py
# Source: https://fastapi.tiangolo.com/tutorial/request-files/  [CITED]
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.cv.parser import parse_cv
from app.models.schemas import CVProfile
from app.api.deps import get_cv_llm_client
import instructor

router = APIRouter(prefix="/cv", tags=["cv"])

@router.post("/parse", response_model=CVProfile)
async def parse_cv_endpoint(
    file: UploadFile = File(..., description="CV en PDF"),
    client: instructor.Instructor = Depends(get_cv_llm_client),
):
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Solo se aceptan ficheros PDF.")
    pdf_bytes = await file.read()  # await is mandatory — UploadFile.read() is a coroutine
    try:
        return parse_cv(pdf_bytes)  # uses injected client if we patch parse_cv's dependency
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

**CRITICAL:** `await file.read()` — forgetting `await` raises a coroutine-not-awaited error. This is the most common UploadFile pitfall. [VERIFIED: FastAPI docs]

### Pattern 4: Storage Protocol + SQLiteStorage

**What:** `typing.Protocol` defines the storage interface. `SQLiteStorage` implements it with raw `sqlite3`. No inheritance required.

**When to use:** Any abstraction where multiple implementations are needed (SQLite for dev, Supabase for prod, FakeStorage for tests).

```python
# app/storage/protocol.py
# Source: PEP 544 / Python typing docs  [CITED]
from typing import Protocol, runtime_checkable
from app.models.schemas import ScoredJob

@runtime_checkable
class Storage(Protocol):
    def init_db(self) -> None: ...
    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None: ...
    def was_seen(self, job_id: str) -> bool: ...
    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]: ...
```

```python
# app/storage/sqlite.py  (key patterns)
# Source: Python stdlib docs + established project conventions  [CITED: docs.python.org/3/library/sqlite3.html]
import sqlite3
import json
from app.models.schemas import ScoredJob

class SQLiteStorage:
    def __init__(self, db_path: str = "data/jobs.db"):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        # check_same_thread=False: FastAPI runs sync endpoints in a threadpool.
        # Each call to _connect() creates a new connection (connection-per-call pattern)
        # which is the simplest thread-safe approach for a single-user tool.
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
                    score_json TEXT,   -- JobScore serialized as JSON string
                    first_seen TEXT,   -- ISO 8601
                    last_seen TEXT,    -- ISO 8601
                    seen INTEGER DEFAULT 0  -- 0=new, 1=already notified/seen
                )
            """)
            conn.commit()

    def upsert_scored_job(self, scored: ScoredJob) -> None:
        job, score = scored.job, scored.score
        score_json = score.model_dump_json()  # Pydantic v2: serialize to JSON string
        now = _now_iso()
        with self._connect() as conn:
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
                score.recommendation.value, score_json, now, now,
            ))
            conn.commit()
```

**Key SQLite patterns:**
- `ON CONFLICT(id) DO UPDATE SET ...` — proper upsert (requires SQLite >= 3.24, released 2018; Python 3.13 ships with SQLite 3.45+). [VERIFIED: Python docs, SQLite docs]
- `conn.row_factory = sqlite3.Row` — lets you access columns by name (`row["title"]`) in get_history().
- `score.model_dump_json()` — Pydantic v2 method; serializes to JSON string for TEXT column. `JobScore.model_validate_json(row["score_json"])` to deserialize.
- `check_same_thread=False` — required because FastAPI runs sync endpoints in its threadpool. Connection-per-call (new connection on each `_connect()`) is thread-safe and sufficient at this scale.

### Pattern 5: TestClient + dependency_overrides

**What:** FastAPI's `app.dependency_overrides` dict maps original `Depends` factory → replacement callable. TestClient wraps httpx for sync testing of ASGI apps.

**When to use:** Every API test. Override LLM client, embedder, and storage to get zero-network, zero-BGE-M3 tests.

```python
# tests/api/conftest.py
# Source: https://fastapi.tiangolo.com/advanced/testing-dependencies/  [CITED]
import pytest
from fastapi.testclient import TestClient  # re-exports starlette.testclient.TestClient
from app.api.main import app
from app.api.deps import get_scoring_llm_client, get_cv_llm_client, get_embedder, get_storage
from tests.conftest import make_scoring_client, EXPECTED_ASSESSMENT

class FakeStorage:
    """In-memory storage for tests — no disk, no SQLite."""
    def __init__(self):
        self._seen: set[str] = set()
        self._jobs: list[dict] = []
    def init_db(self): pass
    def upsert_scored_jobs(self, scored): ...
    def was_seen(self, job_id): return job_id in self._seen
    def get_history(self, limit=50, offset=0): return self._jobs

@pytest.fixture
def api_client():
    fake_store = FakeStorage()
    mock_scoring = make_scoring_client(EXPECTED_ASSESSMENT)
    
    # Import FakeEmbedder inside fixture (deferred — avoids torch import at collection time)
    import numpy as np
    from app.dedup.embedder import FakeEmbedder
    fake_embedder = FakeEmbedder(default_vector=np.array([1.,0.,0.,0.], dtype=np.float32))

    app.dependency_overrides[get_storage] = lambda: fake_store
    app.dependency_overrides[get_scoring_llm_client] = lambda: mock_scoring
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    # get_cv_llm_client overridden per test that needs /cv/parse

    with TestClient(app) as client:
        yield client

    app.dependency_overrides = {}  # reset after each test — prevents cross-contamination
```

**CRITICAL:** `app.dependency_overrides = {}` at teardown. Failing to reset causes test pollution. [VERIFIED: FastAPI docs, TestDriven.io]

### Anti-Patterns to Avoid

- **`async def` endpoints calling sqlite3 directly:** Sqlite3 is blocking I/O. In an `async def` endpoint it blocks the event loop for all other requests. Use `def` (sync) endpoints — FastAPI automatically runs them in its thread pool. [VERIFIED: FastAPI async docs]
- **Forgetting `await file.read()`:** UploadFile.read() returns a coroutine. Without `await` you get a coroutine object instead of bytes — no error at assignment time, but downstream fails. [VERIFIED: FastAPI docs]
- **Importing embedder at module level in app/api/:** `from app.dedup.embedder import BgeM3Embedder` at module top level would trigger torch import when the app starts. Always use a deferred import inside the `get_embedder` Depends function. [VERIFIED: existing project codebase — see app/dedup/__init__.py L106-109]
- **`check_same_thread=True` (default) with FastAPI threadpool:** FastAPI's sync endpoint thread pool will call sqlite3 from threads different from the creating thread. Default check blocks this. Must use `check_same_thread=False`. [VERIFIED: SQLite docs + search results]
- **Missing httpx dev dep for TestClient:** `from fastapi.testclient import TestClient` requires `httpx` at runtime even though it re-exports from starlette. If httpx is not installed, you get `ModuleNotFoundError`. Must `uv add httpx` (or in dev group). [VERIFIED: GitHub issue fastapi/fastapi#5656]
- **Sharing a single sqlite3 connection across threads:** Even with `check_same_thread=False`, a *shared single connection* used concurrently from multiple threads is unsafe. Use connection-per-call (create a new `sqlite3.connect()` per operation inside `_connect()`) or use thread-local storage. [VERIFIED: SQLite threading docs]
- **Not resetting `app.dependency_overrides`:** Overrides set in one test leak into subsequent tests if not cleared. Pattern: `yield client` then `app.dependency_overrides = {}`. [CITED: FastAPI docs on testing dependencies]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request body validation + 422 errors | Custom validation middleware | FastAPI + Pydantic v2 automatic | FastAPI auto-validates request bodies against Pydantic models and returns 422 Unprocessable Entity with field-level errors — free |
| Multipart parsing for file upload | Custom multipart parser | FastAPI UploadFile + python-multipart | python-multipart handles RFC 2046 multipart parsing; streaming chunks, content-type detection, etc. |
| HTTP error responses | Custom error dict builder | `raise HTTPException(status_code=..., detail=...)` | FastAPI serializes to `{"detail": "..."}` JSON automatically |
| JSON serialization of Pydantic models | `json.dumps(model.dict())` | `model.model_dump_json()` (Pydantic v2) | `model_dump_json()` handles enums, Optional, nested models correctly; `.dict()` is Pydantic v1 deprecated |
| JSON deserialization back from DB | `json.loads()` + `Model(**data)` | `Model.model_validate_json(json_str)` | Single call, type-safe, handles all Pydantic v2 coercions |
| DB upsert with conflict handling | SELECT then INSERT or UPDATE | `INSERT ... ON CONFLICT(id) DO UPDATE SET ...` | Atomic, no TOCTOU race condition |

**Key insight:** FastAPI + Pydantic v2 eliminate entire categories of boilerplate (validation, serialization, error formatting). sqlite3 `ON CONFLICT` upsert eliminates the read-before-write pattern that causes race conditions.

---

## Common Pitfalls

### Pitfall 1: Torch imported at app startup (breaks fast import)
**What goes wrong:** If `app/api/main.py` or any router imports `app.dedup.embedder.BgeM3Embedder` at module level, importing the app triggers the torch/sentence-transformers import chain (~2-5 seconds, downloads if not cached). TestClient collection time explodes and `pytest` may fail to collect if the model is not available.

**Why it happens:** `BgeM3Embedder` is defined in `app/dedup/embedder.py` which imports sentence-transformers at module level.

**How to avoid:** The `get_embedder` Depends function must do a deferred import inside the function body:
```python
def get_embedder():
    from app.dedup.embedder import BgeM3Embedder  # deferred — not at module level
    return BgeM3Embedder()
```
Tests always override `get_embedder` → the deferred import never executes in tests.

**Warning signs:** Slow pytest collection (>3s), `ImportError` for sentence-transformers in CI.

### Pitfall 2: sqlite3 threading — `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`
**What goes wrong:** A sqlite3 connection created in one thread is used from another thread (e.g., lifespan creates it, a request uses it from a different thread in the threadpool).

**Why it happens:** sqlite3's default safety guard `check_same_thread=True` blocks cross-thread reuse.

**How to avoid:** Either (a) create a new connection per operation call (`_connect()` method that returns `sqlite3.connect(path, check_same_thread=False)`), or (b) use thread-local storage. Connection-per-call is simplest for a low-concurrency personal tool.

**Warning signs:** `ProgrammingError` in the first real endpoint call after the server has handled more than one concurrent request.

### Pitfall 3: UploadFile bytes vs coroutine
**What goes wrong:** `pdf_bytes = file.read()` — forgets `await` — assigns a coroutine object to `pdf_bytes`. No immediate error. `parse_cv(pdf_bytes)` receives a coroutine, fails with a confusing TypeError downstream.

**Why it happens:** UploadFile.read() is a coroutine. `async def` endpoints must `await` it.

**How to avoid:** Always `pdf_bytes = await file.read()`. Alternatively, use a sync endpoint with `file.file.read()` (access the underlying SpooledTemporaryFile directly).

**Warning signs:** `TypeError: a bytes-like object is required` or similar in parse_cv.

### Pitfall 4: httpx not installed → TestClient import fails
**What goes wrong:** `from fastapi.testclient import TestClient` raises `ModuleNotFoundError: No module named 'httpx'`.

**Why it happens:** FastAPI re-exports starlette's TestClient, which internally requires httpx. FastAPI does not list httpx as a mandatory dependency (only needed for testing).

**How to avoid:** `uv add httpx` — add to main deps (acceptable for personal tool) or as a dev dependency.

**Warning signs:** ModuleNotFoundError at test collection time, before any test runs.

### Pitfall 5: CVProfile cache dependency — which file to load
**What goes wrong:** `get_cached_cv_profile()` must load the right CVProfile from the cache directory. Sorting by modification time to get the "latest" file is fragile (filesystem timestamps can be unreliable). Alternatively, storing only one hash active at a time sidesteps the problem.

**Why it happens:** The Phase 1 cache design stores one file per PDF hash. A single-user tool will have at most a handful of files but no explicit "current" pointer.

**How to avoid (two valid approaches):**
- Store the current hash in a metadata file (`data/.cache/_current`) when `/cv/parse` is called. `get_cached_cv_profile` reads that metadata file.
- Store the last hash in `app.state.current_cv_hash` set during `/cv/parse`. Fast but lost on restart.

The planner should pick one. The metadata file approach is more robust.

**Warning signs:** `/jobs/process` loads an old CVProfile after the user uploads a new CV in the same session.

### Pitfall 6: Pydantic v2 JSON round-trip for JobScore stored in SQLite
**What goes wrong:** `JobScore` contains `Recommendation` (str Enum) and `Desglose` (nested model). Storing with `json.dumps(score.dict())` loses enum serialization context; loading with `JobScore(**json.loads(row["score_json"]))` fails because dict values aren't coerced.

**Why it happens:** Pydantic v2 `.dict()` is deprecated; `.model_dump()` returns Python objects (enums as enum instances), not JSON-safe primitives.

**How to avoid:** Always `score.model_dump_json()` to serialize → `JobScore.model_validate_json(row["score_json"])` to deserialize.

**Warning signs:** `ValidationError` when loading history, or Recommendation appearing as a string literal instead of enum.

### Pitfall 7: `app.dependency_overrides` not reset between tests
**What goes wrong:** Test A overrides `get_storage` with FakeStorage. Test B (which runs after A) does not declare the override. The override from A is still active — Test B uses FakeStorage instead of a fresh temp DB.

**Why it happens:** `app.dependency_overrides` is a dict on the shared `app` object. If not cleared after the test, it persists for subsequent tests.

**How to avoid:** Use `app.dependency_overrides = {}` in fixture teardown (after `yield`).

**Warning signs:** Tests pass in isolation but fail when run together; behavior changes depending on test order.

---

## Code Examples

Verified patterns from official sources and existing project conventions:

### Lifespan + storage selection by env
```python
# Source: https://fastapi.tiangolo.com/advanced/events/ [CITED]
from contextlib import asynccontextmanager
from fastapi import FastAPI
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    app.state.storage = storage
    yield
    # cleanup if needed (e.g., close connection pool)

app = FastAPI(lifespan=lifespan)
```

### Storage Depends reading from app.state
```python
# Source: FastAPI docs — Dependencies [CITED]
from fastapi import Request

def get_storage(request: Request):
    return request.app.state.storage
```

### ON CONFLICT upsert (SQLite >= 3.24, Python 3.13 ships 3.45+)
```python
# Source: https://sqlite.org/lang_upsert.html [CITED]
conn.execute("""
    INSERT INTO jobs (id, title, score_total, first_seen, last_seen, seen)
    VALUES (?, ?, ?, ?, ?, 0)
    ON CONFLICT(id) DO UPDATE SET
        last_seen = excluded.last_seen,
        score_total = excluded.score_total
""", (job_id, title, score_total, now, now))
conn.commit()
```

### Pydantic v2 JSON round-trip for SQLite TEXT column
```python
# Source: Pydantic v2 docs — Serialization [CITED: docs.pydantic.dev/latest/concepts/serialization/]
# Write:
score_json: str = score.model_dump_json()           # → JSON string, enum values as strings
# Read:
score: JobScore = JobScore.model_validate_json(row["score_json"])  # → typed JobScore
```

### TestClient + dependency_overrides (canonical pattern)
```python
# Source: https://fastapi.tiangolo.com/advanced/testing-dependencies/ [CITED]
from fastapi.testclient import TestClient

def test_get_profile(api_client):  # api_client fixture from conftest
    response = api_client.get("/profile")
    assert response.status_code == 200
    data = response.json()
    assert "datos_personales" in data

# Fixture teardown resets overrides:
# app.dependency_overrides = {}
```

### /cv/parse with UploadFile (multipart)
```python
# Source: https://fastapi.tiangolo.com/tutorial/request-files/ [CITED]
from fastapi import UploadFile, File

@router.post("/parse")
async def parse_cv_endpoint(file: UploadFile = File(...)):
    content = await file.read()   # await — returns bytes
    return parse_cv(content)

# In tests: use files= kwarg with TestClient
def test_parse_cv(api_client, sample_pdf_bytes):
    response = api_client.post(
        "/cv/parse",
        files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 200
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` / `@app.on_event("shutdown")` | `FastAPI(lifespan=lifespan)` async context manager | FastAPI 0.93 (deprecated in 0.93, removed in later) | Lifespan is the current standard; old decorators still work but show deprecation warnings |
| Pydantic v1 `.dict()` / `.json()` | Pydantic v2 `.model_dump()` / `.model_dump_json()` | Pydantic v2 (2023) | Project already uses Pydantic v2 — use v2 API only |
| `from starlette.testclient import TestClient` | `from fastapi.testclient import TestClient` | FastAPI 0.87+ (convenience re-export) | Both work; prefer `fastapi.testclient` for clarity |
| `INSERT OR REPLACE INTO ...` | `INSERT INTO ... ON CONFLICT(id) DO UPDATE SET ...` | SQLite 3.24 (2018) | ON CONFLICT allows partial update (not full row replacement); INSERT OR REPLACE deletes and re-inserts, losing `first_seen` and `seen` flag |

**Deprecated/outdated:**
- `@app.on_event("startup")`: deprecated in FastAPI 0.93; use `lifespan=` parameter.
- `pydantic.BaseModel.dict()`: Pydantic v1 API, removed in v2; use `.model_dump()`.
- `pydantic.BaseModel.json()`: same; use `.model_dump_json()`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Python 3.13 ships with SQLite >= 3.24 (required for ON CONFLICT upsert syntax) | SQLite patterns | If a user has an older SQLite bundled, upsert syntax fails — fallback to INSERT OR REPLACE (loses first_seen) | [ASSUMED — confirmed by Python 3.13 release notes that it ships with SQLite 3.45.3, but not verified via local command] |
| A2 | FakeEmbedder class exists in app/dedup/embedder.py (Phase 2 artifact) | Test patterns | If FakeEmbedder doesn't exist or has a different signature, tests/api/conftest.py fixture needs adjustment |

[VERIFIED: A2 is supported by tests/conftest.py line 114: `from app.dedup.embedder import FakeEmbedder` — the class exists]

---

## Open Questions

1. **CVProfile cache pointer for `get_cached_cv_profile`**
   - What we know: The Phase 1 cache stores one JSON file per PDF hash in `data/.cache/`.
   - What's unclear: What is the canonical "current" CV? Sorting by mtime is fragile. `app.state` pointer is lost on restart.
   - Recommendation: Create `data/.cache/_current` metadata file written by `/cv/parse`; `get_cached_cv_profile` reads it. Planner should make this explicit in the plan.

2. **`upsert_scored_jobs` bulk vs one-by-one**
   - What we know: `/jobs/process` returns a list of `ScoredJob`. The protocol method is `upsert_scored_jobs(scored: list[ScoredJob])`.
   - What's unclear: Should the bulk upsert use a single transaction (faster) or individual per-row `_connect()` calls?
   - Recommendation: Single transaction with one `conn` opened for the whole list — much faster and avoids opening N connections per batch.

3. **ya_visto flag: column name**
   - CONTEXT.md says "notified/seen flag". The `ScoredJob` response model should include a `ya_visto: bool` field. Confirm whether this field goes on the response only (computed from `was_seen()` before persisting) or also lives in the DB `seen` column.
   - Recommendation: `seen` column in DB (0/1); `ya_visto` in the API response is populated from `was_seen(job.id)` *before* the upsert, so a returning job is flagged correctly.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | All | ✓ | 3.13.5 | — |
| pytest 9.0.3 | Tests | ✓ | 9.0.3 | — |
| pydantic 2.13.4 | All models | ✓ | 2.13.4 | — |
| fastapi | App layer | ✗ | not installed yet | `uv add fastapi` |
| uvicorn[standard] | App startup | ✗ | not installed yet | `uv add "uvicorn[standard]"` |
| python-multipart | /cv/parse UploadFile | ✗ | not installed yet | `uv add python-multipart` |
| httpx | TestClient | ✗ | not installed yet | `uv add httpx` |
| sqlite3 | Storage | ✓ | bundled with Python 3.13 (3.45.3) | — |

**Missing dependencies with no fallback:**
- `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx` — must be installed before Phase 4 code runs. One `uv add` command covers all.

**Missing dependencies with fallback:**
- None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/api/ tests/storage/ -q` |
| Full suite command | `pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | POST /cv/parse returns CVProfile, caches it | integration | `pytest tests/api/test_cv.py -x` | ❌ Wave 0 |
| API-02 | GET /profile returns UserProfile | integration | `pytest tests/api/test_profile.py -x` | ❌ Wave 0 |
| API-03 | POST /jobs/normalize returns jobs + errors | integration | `pytest tests/api/test_jobs.py::test_normalize -x` | ❌ Wave 0 |
| API-04 | POST /jobs/process: order by score_total, ya_visto on 2nd run | integration | `pytest tests/api/test_jobs.py::test_process -x` | ❌ Wave 0 |
| API-05 | POST /jobs/score: 404 if no CVProfile cached | integration | `pytest tests/api/test_jobs.py::test_score_no_cv -x` | ❌ Wave 0 |
| API-06 | GET /jobs/history returns paginated history | integration | `pytest tests/api/test_jobs.py::test_history -x` | ❌ Wave 0 |
| API-07 | Malformed offer → errors[], not 500 | integration | `pytest tests/api/test_jobs.py::test_process_malformed -x` | ❌ Wave 0 |
| STORE-01 | SQLiteStorage selected when no SUPABASE_URL; SupabaseStorage protocol exists | unit | `pytest tests/storage/test_sqlite.py -x` | ❌ Wave 0 |
| STORE-02 | upsert sets first_seen/last_seen; history returns jobs with date | unit | `pytest tests/storage/test_sqlite.py::test_history -x` | ❌ Wave 0 |
| STORE-03 | was_seen() returns True on 2nd call; ya_visto in /jobs/process response | unit+integration | `pytest tests/storage/ tests/api/test_jobs.py::test_ya_visto -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/api/ tests/storage/ -q`
- **Per wave merge:** `pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/api/__init__.py` — package init
- [ ] `tests/api/conftest.py` — api_client fixture with dependency_overrides
- [ ] `tests/api/test_cv.py` — API-01 tests
- [ ] `tests/api/test_profile.py` — API-02 tests
- [ ] `tests/api/test_jobs.py` — API-03, API-04, API-05, API-06, API-07 tests
- [ ] `tests/storage/__init__.py` — package init
- [ ] `tests/storage/test_sqlite.py` — STORE-01, STORE-02, STORE-03 tests
- [ ] Install: `uv add fastapi "uvicorn[standard]" python-multipart httpx`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Out of scope v1 — personal tool, n8n on localhost/private net |
| V3 Session Management | no | Stateless HTTP; no sessions |
| V4 Access Control | no | Single-user tool |
| V5 Input Validation | yes | FastAPI + Pydantic v2 automatic 422 on invalid input; UploadFile content-type check for /cv/parse |
| V6 Cryptography | no | No user secrets stored; ANTHROPIC_API_KEY from env (not in code) |

### Known Threat Patterns for Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via job data | Tampering | sqlite3 parameterized queries (`?` placeholders) — NEVER string interpolation in SQL |
| Path traversal via uploaded PDF | Tampering | PDF bytes never written to disk with caller-controlled filename; hash-based cache key (validated by `_HEX_RE` in cache.py — Phase 1) |
| ANTHROPIC_API_KEY in code | Information Disclosure | Key read from environment via SDK; never referenced in source (established Phase 1-3 pattern) |
| Prompt injection via offer content | Tampering | scoring/llm.py uses fixed system prompt + offer in `<oferta>` XML section (Phase 3 pattern); same pattern must be preserved in /jobs/process |

---

## Sources

### Primary (HIGH confidence)
- PyPI registry (curl) — fastapi 0.136.1, uvicorn 0.47.0, python-multipart 0.0.29, httpx 0.28.1 [VERIFIED: 2026-05-22]
- `app/dedup/__init__.py` lines 106-109 — deferred import pattern for BGE-M3 [VERIFIED: codebase]
- `tests/conftest.py` — existing mock patterns, FakeEmbedder import pattern [VERIFIED: codebase]
- `app/cv/cache.py` — sha256 hash cache, `CV_CACHE_DIR` env var pattern [VERIFIED: codebase]
- `app/models/schemas.py` — ScoredJob, JobScore, CVProfile, UserProfile shapes [VERIFIED: codebase]
- `pyproject.toml` — existing deps, Python 3.13 requirement [VERIFIED: codebase]
- Python docs: sqlite3 stdlib [CITED: docs.python.org/3/library/sqlite3.html]

### Secondary (MEDIUM confidence)
- FastAPI testing docs [CITED: fastapi.tiangolo.com/tutorial/testing/] — TestClient, dependency_overrides pattern
- FastAPI lifespan docs [CITED: fastapi.tiangolo.com/advanced/events/] — async context manager pattern
- FastAPI UploadFile docs [CITED: fastapi.tiangolo.com/tutorial/request-files/] — `await file.read()`
- FastAPI dependencies docs [CITED: fastapi.tiangolo.com/tutorial/dependencies/] — Depends, app.state
- SQLite upsert docs [CITED: sqlite.org/lang_upsert.html] — ON CONFLICT DO UPDATE
- Pydantic v2 serialization docs [CITED: docs.pydantic.dev/latest/concepts/serialization/] — model_dump_json()
- GitHub issue fastapi/fastapi#5656 — httpx required for TestClient [VERIFIED: cross-referenced in search results]

### Tertiary (LOW confidence)
- None — all claims are either codebase-verified or cited from official docs.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all package versions verified via PyPI registry
- Architecture: HIGH — based on existing codebase patterns (Phases 1-3) and official FastAPI docs
- Pitfalls: HIGH — derived from official docs + confirmed in existing project code (deferred import anti-torch pattern already in place)
- SQLite patterns: HIGH — stdlib docs + SQLite official docs

**Research date:** 2026-05-22
**Valid until:** 2026-08-22 (stable libraries; FastAPI moves slowly on breaking changes)
