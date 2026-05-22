"""
Fusión de grupos de ofertas duplicadas en una oferta canónica.

Responsabilidad:
  - merge_group: dado un grupo de Jobs duplicados, selecciona el canónico
    (el de descripción más larga = más completa) y acumula las URLs alternativas
    de los descartados en Job.urls_alternativas.

REGLA DE NO-MUTACIÓN (DEDUP-03 + Pydantic v2):
  merge_group usa model_copy(update=...) para crear un nuevo objeto Job
  con las urls_alternativas actualizadas. El Job canónico original NO se muta.

Patrón análogo a app/cv/parser.py: función de orquestación con inputs tipados y
output tipado. No importa dependencias externas (solo app.models.schemas).
"""
from __future__ import annotations

import logging

from app.models.schemas import Job

logger = logging.getLogger(__name__)


def merge_group(group: list[Job]) -> Job:
    """Fusiona un grupo de Jobs duplicados en una oferta canónica.

    Estrategia:
    - Canónica: el Job con la descripción más larga (más completa / más información).
    - URLs alternativas: las URLs de los Jobs descartados se acumulan en
      ``urls_alternativas`` de la canónica (via model_copy — sin mutar el original).
    - Jobs descartados sin URL (url=None) no añaden nada a urls_alternativas.

    Si el grupo tiene un solo Job, se devuelve tal cual (sin copiar).

    Args:
        group: Lista de Jobs del mismo grupo (duplicados exactos o semánticos).
               Debe tener al menos 1 elemento.

    Returns:
        Job canónico con urls_alternativas enriquecidas con las URLs descartadas.
        El Job canónico original NO se muta (Pydantic v2 model_copy).

    Raises:
        ValueError: Si group está vacío.

    Examples:
        >>> merge_group([job_corto, job_largo])
        # Devuelve un Job con description = job_largo.description y
        # urls_alternativas contiene la url de job_corto
    """
    if not group:
        raise ValueError("merge_group recibió un grupo vacío.")

    if len(group) == 1:
        # Caso trivial: sin duplicados, devolver el job tal cual
        return group[0]

    # Seleccionar la oferta con descripción más completa (más larga)
    canonical = max(group, key=lambda j: len(j.description))

    # Acumular URLs de los descartados (excluir None y la URL de la canónica)
    urls_alternativas_nuevas = [
        j.url
        for j in group
        if j is not canonical and j.url is not None
    ]

    # Combinar URLs alternativas existentes con las nuevas
    todas_las_alternativas = list(canonical.urls_alternativas) + urls_alternativas_nuevas

    logger.debug(
        "merge_group: %d jobs → canónica '%s @ %s' (desc=%d chars), %d URLs alternativas",
        len(group),
        canonical.title,
        canonical.company,
        len(canonical.description),
        len(todas_las_alternativas),
    )

    # model_copy(update=...) crea un nuevo objeto Job (Pydantic v2 — no mutación)
    return canonical.model_copy(update={"urls_alternativas": todas_las_alternativas})
