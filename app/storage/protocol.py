"""Protocolo de persistencia para el servicio BuscadorDeEmpleo.

Define la interfaz que debe satisfacer SQLiteStorage (y cualquier backend
futuro), usando typing.Protocol (PEP 544) para subtipado estructural — sin herencia.

Contratos:
    init_db: crea tablas si no existen; idempotente.
    upsert_scored_jobs: persiste lista de ofertas puntuadas; idempotente por job.id.
    was_seen: True si el job_id fue persistido en un run anterior.
    get_history: devuelve ofertas guardadas, paginable con limit/offset.
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
    """

    def init_db(self) -> None: ...

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None: ...

    def was_seen(self, job_id: str) -> bool: ...

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]: ...

    def get_settings(self) -> dict[str, str]: ...

    def set_setting(self, key: str, value: str) -> None: ...
