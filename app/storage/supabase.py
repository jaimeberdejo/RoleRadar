"""Skeleton de SupabaseStorage para BuscadorDeEmpleo.

Implementa el mismo Protocol que SQLiteStorage. Seleccionado cuando
SUPABASE_URL y SUPABASE_KEY están en el entorno.

Implementación real diferida a Fase 5 (cuando se conecte Supabase/pgvector).
Actualmente: init_db no hace nada (tablas vía migraciones Supabase);
upsert/was_seen/get_history lanzan NotImplementedError.
"""
from __future__ import annotations

import logging

from app.models.schemas import ScoredJob

logger = logging.getLogger(__name__)


class SupabaseStorage:
    """Storage skeleton sobre Supabase/pgvector.

    Implementa el mismo Protocol que SQLiteStorage.
    Seleccionado cuando SUPABASE_URL y SUPABASE_KEY están en el entorno.
    Implementación real diferida a Fase 5.
    """

    def __init__(self) -> None:
        # from supabase import create_client  # cuando se implemente en Fase 5
        logger.warning("SupabaseStorage: skeleton — no persiste nada todavía.")

    def init_db(self) -> None:
        """No-op: tablas de Supabase se gestionan vía migraciones."""
        pass

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None:
        raise NotImplementedError("SupabaseStorage no implementado aún. Fase 5.")

    def was_seen(self, job_id: str) -> bool:
        raise NotImplementedError("SupabaseStorage no implementado aún. Fase 5.")

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        raise NotImplementedError("SupabaseStorage no implementado aún. Fase 5.")
