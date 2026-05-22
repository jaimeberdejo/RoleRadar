"""Aplicación FastAPI principal del servicio BuscadorDeEmpleo.

Inicializa la app con lifespan (selección de storage por env vars),
registra los routers por concern y expone la instancia `app` que uvicorn
arranca con `uvicorn app.api.main:app`.

Decisión de diseño:
    Los imports de SQLiteStorage/SupabaseStorage son DEFERIDOS dentro del
    cuerpo de lifespan (mismo patrón que app/dedup/__init__.py L105-109).
    Esto mantiene el módulo importable sin disco, sin red y sin torch,
    lo que hace la colección de pytest instantánea (T-04-03).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import profile

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa recursos compartidos al arrancar y los libera al parar.

    Selección de storage (lazy, en tiempo de ejecución):
    - Si SUPABASE_URL y SUPABASE_KEY presentes → SupabaseStorage.
    - En caso contrario → SQLiteStorage(SQLITE_DB_PATH, default data/jobs.db)
      con init_db() llamado.

    Los imports son deferidos para que `from app.api.main import app` sea
    torch-free y no requiera sqlite en tiempo de import.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if supabase_url and supabase_key:
        from app.storage.supabase import SupabaseStorage  # noqa: PLC0415
        storage = SupabaseStorage()
        logger.info("lifespan: usando SupabaseStorage")
    else:
        from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415
        db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
        storage = SQLiteStorage(db_path)
        storage.init_db()
        logger.info("lifespan: usando SQLiteStorage en %s", db_path)
    app.state.storage = storage
    yield
    # Cleanup: SQLite no requiere cierre explícito (conexiones por llamada).
    # SupabaseStorage podría cerrar el cliente HTTP aquí cuando se implemente.
    logger.info("lifespan: servicio detenido")


app = FastAPI(
    title="BuscadorDeEmpleo",
    description="Agregador inteligente de ofertas de empleo para Jaime.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(profile.router)
# app.include_router(cv.router)    # Plan 03
# app.include_router(jobs.router)  # Plan 03/04
