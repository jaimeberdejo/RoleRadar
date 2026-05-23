"""Capa de persistencia del servicio (FASE 4).

Interfaz pública:
    Storage  — Protocol runtime_checkable de persistencia.
    get_storage_backend() — crea e inicializa el backend SQLite local.
"""
from __future__ import annotations

import os

from app.storage.protocol import Storage

__all__ = ["Storage", "get_storage_backend"]


def get_storage_backend() -> Storage:
    """Crea e inicializa el backend de persistencia (SQLite local).

    Ruta del fichero configurable vía la variable de entorno SQLITE_DB_PATH
    (default "data/jobs.db"). 100% local, sin dependencias de red.

    El import es DEFERIDO dentro del cuerpo (anti-circular / mantiene el
    paquete importable sin abrir disco hasta que se llama).

    Returns:
        Instancia de Storage lista para usar (init_db ya llamado).
    """
    from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415

    db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
    storage = SQLiteStorage(db_path)
    storage.init_db()
    return storage
