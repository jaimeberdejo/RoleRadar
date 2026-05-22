"""
Paquete de deduplicación y normalización de ofertas de empleo.

Fachada pública:
  - normalize_jobs: normaliza una lista de payloads crudos + source → (jobs, errors)
  - deduplicate: deduplicación semántica en dos niveles (exacta + coseno BGE-M3)

La deduplicación opera en dos niveles:
  Nivel 1 (exacto): agrupa por hash NFD de empresa + título.
  Nivel 2 (semántico): clustering greedy por similitud coseno sobre embeddings
    BGE-M3 del texto "título + empresa + primeras N palabras de descripción".
Cuando embedder=None, se instancia BgeM3Embedder de forma perezosa (solo en uso
real). Los tests siempre inyectan FakeEmbedder vía el parámetro embedder= para
evitar descargar el modelo (~2.3 GB) en CI.
"""
from __future__ import annotations

import logging

from app.dedup.mappers import MAPPER_REGISTRY
from app.models.schemas import Job

logger = logging.getLogger(__name__)

__all__ = ["normalize_jobs", "deduplicate"]


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


def deduplicate(
    jobs: list[Job],
    embedder: "Embedder | None" = None,
    umbral: float = 0.85,
    desc_words: int = 50,
) -> list[Job]:
    """Desduplicación en dos niveles: hash exacto → clustering semántico → merge.

    Nivel 1 (exacto): agrupa ofertas por la clave normalizada empresa+título usando
    ``exact_group``. Dos ofertas con el mismo par (empresa, título) normalizados
    quedan en el mismo grupo, con independencia de capitalización o acentos.

    Nivel 2 (semántico): sobre los representantes de cada grupo exacto (ya fusionados
    por ``merge_group``), aplica ``semantic_cluster`` usando embeddings del texto
    "título + empresa + primeras ``desc_words`` palabras de descripción" para
    agrupar ofertas semánticamente similares (similitud coseno ≥ ``umbral``).

    Fusión: cada cluster semántico se pasa a ``merge_group``, que conserva la oferta
    con descripción más larga como canónica y acumula las URLs de las descartadas en
    ``urls_alternativas``.

    Los imports de los módulos hoja (exact, semantic, merger, embedder) se realizan
    DENTRO del cuerpo de la función para evitar arrastrar numpy/torch al importar el
    paquete (invariante anti-torch, T-02-11).

    Args:
        jobs: Lista de ofertas normalizadas (objetos Job).
        embedder: Embedder inyectado para la fase semántica. Si es None, se usa
            BgeM3Embedder() de forma perezosa (descarga el modelo en primera llamada
            real). Los tests siempre inyectan FakeEmbedder via este parámetro.
        umbral: Umbral de similitud coseno [0, 1] para el clustering semántico.
            Default 0.85 (configurable en UserProfile.dedup_umbral).
        desc_words: Número de palabras de descripción a incluir en el texto de
            embedding. Default 50.

    Returns:
        Lista de Jobs únicos, fusionados y ordenados. Cada Job canónico acumula
        las URLs de sus duplicados en ``urls_alternativas``.
    """
    # Imports deferidos: evitan arrastrar numpy/torch al importar app.dedup (T-02-11)
    from app.dedup.exact import exact_group  # noqa: PLC0415
    from app.dedup.semantic import semantic_cluster  # noqa: PLC0415
    from app.dedup.merger import merge_group  # noqa: PLC0415
    from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415

    if not jobs:
        return []

    # Nivel 1 — deduplicación exacta por empresa + título normalizados
    groups = exact_group(jobs)
    logger.info(
        "dedup level-1 (exact): %d jobs -> %d groups",
        len(jobs),
        len(groups),
    )

    # Fusionar cada grupo exacto a su oferta canónica (representante)
    representatives = [merge_group(g) for g in groups]

    # Instanciar BgeM3Embedder de forma perezosa si no se inyectó uno
    if embedder is None:
        embedder = BgeM3Embedder()

    # Nivel 2 — clustering semántico sobre los representantes
    clusters = semantic_cluster(representatives, embedder, umbral, desc_words)
    logger.info(
        "dedup level-2 (semantic): %d reps -> %d clusters",
        len(representatives),
        len(clusters),
    )

    # Fusionar cada cluster semántico a su oferta canónica final
    result = [merge_group([representatives[i] for i in cluster]) for cluster in clusters]
    return result
