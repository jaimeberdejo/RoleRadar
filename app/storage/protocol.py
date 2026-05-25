"""Protocolo de persistencia para el servicio BuscadorDeEmpleo.

Define la interfaz que debe satisfacer SQLiteStorage (y cualquier backend
futuro), usando typing.Protocol (PEP 544) para subtipado estructural — sin herencia.

Contratos:
    init_db: crea tablas si no existen; idempotente.
    upsert_scored_jobs: persiste lista de ofertas puntuadas; idempotente por job.id.
    was_seen: True si el job_id fue persistido en un run anterior.
    get_history: devuelve ofertas guardadas, paginable con limit/offset.
    get_settings: devuelve todas las settings como {key: value_str}.
    set_setting: upsert de una setting; value es string (JSON si complejo).
    record_run: inserta fila en runs con métricas del pipeline run (STORE-05).
    get_recent_runs: devuelve los runs más recientes ordenados por id desc (STORE-05).
    mark_seen: establece seen=1 en la fila del job (STORE-07).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.models.schemas import ScoredJob


@runtime_checkable
class Storage(Protocol):
    """Interfaz de persistencia. SQLiteStorage (y futuros backends) debe satisfacerla.

    Contratos:
    - upsert_scored_jobs: idempotente por job.id; actualiza si ya existe.
    - was_seen: True si el job_id fue persistido en un run anterior.
    - get_history: paginable con limit/offset; devuelve dicts serializables a JSON.
    - get_settings: devuelve todas las settings como {key: value_str}.
    - set_setting: upsert de una setting; value es string (JSON si complejo).
    - record_run: inserta fila en runs con métricas del pipeline run.
    - get_recent_runs: devuelve los runs más recientes ordenados por id desc.
    - mark_seen: establece seen=1 en la fila del job (phase 9 entrega).
    """

    def init_db(self) -> None: ...

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None: ...

    def was_seen(self, job_id: str) -> bool: ...

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]: ...

    def get_settings(self) -> dict[str, str]: ...

    def set_setting(self, key: str, value: str) -> None: ...

    def record_run(
        self,
        *,
        started_at: str,
        finished_at: str,
        fetched: int,
        deduped: int,
        scored: int,
        new_seen: int,
        errors: list[str] | None = None,
    ) -> None: ...

    def get_recent_runs(self, limit: int = 10) -> list[dict]: ...

    def mark_seen(self, job_id: str) -> None: ...
