"""
Paquete de deduplicación y normalización de ofertas de empleo.

Fachada pública:
  - normalize_jobs: normaliza una lista de payloads crudos + source → (jobs, errors)
  - deduplicate: deduplicación semántica en dos niveles (exacta + coseno BGE-M3)

La función deduplicate se añade en Plan 04 (Wave 3).
"""
from __future__ import annotations

import logging

from app.dedup.mappers import MAPPER_REGISTRY
from app.models.schemas import Job

logger = logging.getLogger(__name__)

__all__ = ["normalize_jobs"]


def normalize_jobs(
    raw_offers: list[dict],
    source: str,
) -> tuple[list[Job], list[dict]]:
    """Normaliza una lista de payloads crudos de una fuente en objetos Job.

    Batch-resiliente: una oferta mal formada va a ``errors`` y nunca tumba el batch.
    Usa el mapper registrado para ``source``; si no existe, usa el mapper genérico.

    Args:
        raw_offers: Lista de dicts con el payload crudo de cada oferta.
        source: Identificador de la fuente (ej. "arbeitnow", "jsearch").

    Returns:
        Tupla ``(jobs, errors)`` donde ``errors`` es una lista de dicts con
        ``{"index": int, "source": str, "error": str}`` por cada oferta fallida.
    """
    mapper = MAPPER_REGISTRY.get(source) or MAPPER_REGISTRY["generic"]
    jobs: list[Job] = []
    errors: list[dict] = []
    for idx, raw in enumerate(raw_offers):
        try:
            jobs.append(mapper(raw, source))
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "source": source, "error": str(exc)})
    logger.info(
        "normalize_jobs: source=%s in=%d ok=%d errors=%d",
        source,
        len(raw_offers),
        len(jobs),
        len(errors),
    )
    return jobs, errors
