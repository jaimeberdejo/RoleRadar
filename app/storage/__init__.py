"""Capa de persistencia del servicio (FASE 4).

Interfaz pública:
    Storage  — Protocol runtime_checkable de persistencia.
    get_storage_backend() — selecciona la implementación según env vars.
"""
from __future__ import annotations

import os

from app.storage.protocol import Storage

__all__ = ["Storage", "get_storage_backend"]


def get_storage_backend() -> Storage:
    """Selecciona e inicializa el backend de storage según variables de entorno.

    Si SUPABASE_URL y SUPABASE_KEY están presentes → SupabaseStorage.
    En caso contrario → SQLiteStorage(SQLITE_DB_PATH, default "data/jobs.db").

    Los imports son DEFERIDOS dentro del cuerpo (anti-torch / anti-circular):
    sqlite.py y supabase.py pueden no existir aún; el import diferido no se
    ejecuta hasta que se llame a esta función.

    Returns:
        Instancia de Storage lista para usar (init_db ya llamado si SQLite).
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if supabase_url and supabase_key:
        from app.storage.supabase import SupabaseStorage  # noqa: PLC0415
        return SupabaseStorage()
    else:
        from app.storage.sqlite import SQLiteStorage  # noqa: PLC0415
        db_path = os.getenv("SQLITE_DB_PATH", "data/jobs.db")
        storage = SQLiteStorage(db_path)
        storage.init_db()
        return storage
