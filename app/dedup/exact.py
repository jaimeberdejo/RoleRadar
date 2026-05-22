"""
Deduplicación de nivel 1: agrupación por hash exacto empresa+título normalizados.

Responsabilidad:
  - exact_group: agrupa una lista de Job por la clave
    ``normalize_field(company) + "|" + normalize_field(title)``.
    Dos Jobs con la misma empresa y título (en cualquier capitalización/acento)
    quedan en el mismo grupo.

Este módulo no importa numpy ni torch: es stdlib + project deps únicamente.
Patrón análogo a app/cv/cache.py: dict keyed lookup sobre campos normalizados.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from app.dedup.normalize import normalize_field
from app.models.schemas import Job

logger = logging.getLogger(__name__)


def exact_group(jobs: list[Job]) -> list[list[Job]]:
    """Agrupa ofertas con el mismo par empresa+título normalizados (nivel 1 de dedup).

    La clave de agrupación es ``normalize_field(company) + "|" + normalize_field(title)``.
    La normalización NFD + casefold + colapso de espacios garantiza que variantes como
    "Acme Corp", "acme corp" o "Àcmé Corp" se traten como el mismo grupo.

    Args:
        jobs: Lista de ofertas normalizadas (objetos Job).

    Returns:
        Lista de grupos (cada grupo es una lista de Job con la misma clave exacta).
        Grupos de tamaño 1: oferta única (sin duplicado exacto).
        Grupos de tamaño > 1: duplicados exactos a fusionar.

    Examples:
        >>> jobs = [Job(title="AI Engineer", company="Acme", ...), Job(title="ai engineer", company="acme", ...)]
        >>> grupos = exact_group(jobs)
        >>> len(grupos)  # ambos comparten la misma clave normalizada
        1
    """
    if not jobs:
        return []

    grupos: dict[str, list[Job]] = defaultdict(list)
    for job in jobs:
        clave = normalize_field(job.company) + "|" + normalize_field(job.title)
        grupos[clave].append(job)

    resultado = list(grupos.values())
    logger.debug(
        "exact_group: %d jobs → %d grupos (duplicados exactos: %d)",
        len(jobs),
        len(resultado),
        sum(1 for g in resultado if len(g) > 1),
    )
    return resultado
