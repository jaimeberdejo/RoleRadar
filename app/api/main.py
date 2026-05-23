"""Aplicación FastAPI principal del servicio BuscadorDeEmpleo.

Inicializa la app con lifespan (storage SQLite local), registra los routers
por concern y expone la instancia `app` que uvicorn arranca con
`uvicorn app.api.main:app`.

Decisión de diseño:
    El import de SQLiteStorage es DEFERIDO dentro del cuerpo de lifespan
    (mismo patrón que app/dedup/__init__.py L105-109). Esto mantiene el
    módulo importable sin disco, sin red y sin torch, lo que hace la
    colección de pytest instantánea (T-04-03).

    Los exception handlers se registran entre `app = FastAPI(...)` y los
    `include_router(...)`. ORDEN CRÍTICO: los handlers específicos (CVParseError,
    NormalizationError, ScoringError, StorageError) van ANTES del handler genérico
    (Exception) porque FastAPI usa el PRIMERO que coincide (OBS-03).

    El handler genérico (Exception) NUNCA filtra el stack trace ni rutas internas
    al cliente — solo loguea con logger.exception y devuelve "Internal server error"
    como mensaje genérico (T-05-03 anti information disclosure).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import cv, jobs, profile
from app.errors import CVParseError, NormalizationError, ScoringError, StorageError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos compartidos al arrancar y los libera al parar.

    Storage (lazy, en tiempo de ejecución): SQLiteStorage local en
    SQLITE_DB_PATH (default data/jobs.db), con init_db() llamado.

    El import es deferido para que `from app.api.main import app` sea
    torch-free y no requiera sqlite en tiempo de import.

    configure_logging() se llama PRIMERO — antes de cualquier otra operación —
    para que todos los logs del arranque estén formateados (OBS-01).
    """
    from app.obs.logging_config import configure_logging  # noqa: PLC0415

    configure_logging()

    from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415

    db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    logger.info("lifespan: usando SQLiteStorage en %s", db_path)
    app.state.storage = storage
    yield
    # Cleanup: SQLite no requiere cierre explícito (conexiones por llamada).
    logger.info("lifespan: servicio detenido")


app = FastAPI(
    title="BuscadorDeEmpleo",
    description="Agregador inteligente de ofertas de empleo para Jaime.",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── Exception handlers (OBS-03) ─────────────────────────────────────────────
# ORDEN CRÍTICO: específicos ANTES del genérico (FastAPI usa el primero que coincide).
# El handler genérico (Exception) va AL FINAL como fallback.

@app.exception_handler(CVParseError)
async def cv_parse_error_handler(request: Request, exc: CVParseError) -> JSONResponse:
    """CVParseError → 422 con envelope {"error": {"type": ..., "message": ...}}."""
    return JSONResponse(
        status_code=422,
        content={"error": {"type": "CVParseError", "message": str(exc)}},
    )


@app.exception_handler(NormalizationError)
async def normalization_error_handler(request: Request, exc: NormalizationError) -> JSONResponse:
    """NormalizationError → 422 con envelope {"error": {"type": ..., "message": ...}}."""
    return JSONResponse(
        status_code=422,
        content={"error": {"type": "NormalizationError", "message": str(exc)}},
    )


@app.exception_handler(ScoringError)
async def scoring_error_handler(request: Request, exc: ScoringError) -> JSONResponse:
    """ScoringError → 422 con envelope {"error": {"type": ..., "message": ...}}."""
    return JSONResponse(
        status_code=422,
        content={"error": {"type": "ScoringError", "message": str(exc)}},
    )


@app.exception_handler(StorageError)
async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    """StorageError → 503 con envelope {"error": {"type": ..., "message": ...}}."""
    return JSONResponse(
        status_code=503,
        content={"error": {"type": "StorageError", "message": str(exc)}},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback para cualquier excepción no controlada → 500.

    INVARIANTE DE SEGURIDAD (T-05-03): el stack trace va SOLO al log (logger.exception),
    NUNCA al body de la respuesta. El mensaje al cliente es siempre el genérico
    "Internal server error" — sin filtrar str(exc) ni rutas de ficheros internos.
    """
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"type": type(exc).__name__, "message": "Internal server error"}},
    )


# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(profile.router)
app.include_router(cv.router)
app.include_router(jobs.router)
