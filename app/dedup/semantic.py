"""
Deduplicación de nivel 2: clustering semántico greedy por similitud coseno.

Responsabilidades:
  - build_embed_text: construye el texto a embeber para una oferta
    (título + empresa + primeras N palabras de descripción).
  - semantic_cluster: genera grupos de índices de jobs semánticamente similares
    usando embeddings y un umbral de similitud coseno configurable.

INVARIANTE (T-02-07): este módulo importa numpy (dep directa, segura) y el
Protocol Embedder (solo Protocol — no torch). Importar este módulo NO introduce
torch en sys.modules.

Patrón: función con dependency injection (embedder: Embedder), análogo a
extract_cv_profile(raw_text, client) en app/cv/llm_client.py.
"""
from __future__ import annotations

import logging

import numpy as np

from app.dedup.embedder import Embedder
from app.models.schemas import Job

logger = logging.getLogger(__name__)


def build_embed_text(job: Job, desc_words: int = 50) -> str:
    """Construye el texto de embedding para una oferta.

    Formato: ``"{title} {company} {primeras N palabras de description}"``.
    Si la descripción está vacía, el resultado es ``"{title} {company}"``.

    Args:
        job: Oferta normalizada.
        desc_words: Número de palabras de descripción a incluir (default: 50).

    Returns:
        Cadena de texto para embeber, sin espacios sobrantes al inicio/fin.

    Examples:
        >>> build_embed_text(Job(title="AI Engineer", company="Acme", description="", ...))
        'AI Engineer Acme'
    """
    palabras = job.description.split()[:desc_words]
    fragmento = " ".join(palabras)
    return f"{job.title} {job.company} {fragmento}".strip()


def semantic_cluster(
    jobs: list[Job],
    embedder: Embedder,
    umbral: float = 0.85,
    desc_words: int = 50,
) -> list[list[int]]:
    """Agrupa jobs semánticamente similares usando clustering greedy por coseno.

    Algoritmo (greedy threshold, Pattern 4 de RESEARCH.md):
    1. Genera textos de embedding para cada job con build_embed_text().
    2. Obtiene la matriz de embeddings E de shape (n, dim), L2-normalizada.
    3. Calcula la matriz de similitud coseno: sim = E @ E.T
    4. Aplica np.clip para corregir valores >1.0 por precisión float32 (T-02-09).
    5. Greedy: para cada job i sin asignar, abre un nuevo cluster y añade
       todos los jobs j > i con sim[i,j] >= umbral que tampoco estén asignados.

    NOTA: el clustering es greedy (dependiente del orden). Para mayor determinismo
    en producción, ordenar los jobs por longitud de descripción descendente antes
    de llamar (Pitfall 5 de RESEARCH.md). El facade deduplicate() aplica ese orden.

    Args:
        jobs: Lista de ofertas a agrupar (los índices del resultado corresponden
              a posiciones en esta lista).
        embedder: Embedder inyectado. En producción: BgeM3Embedder.
                  En tests: FakeEmbedder (sin torch, sin red).
        umbral: Umbral de similitud coseno [0, 1]. Default: 0.85.
                Configurable en UserProfile.dedup_umbral.
        desc_words: Palabras de descripción a incluir en el texto de embedding.

    Returns:
        Lista de clusters. Cada cluster es una lista de índices (int) en `jobs`.
        Todos los índices de [0, len(jobs)) aparecen exactamente una vez.
        Si jobs está vacío, devuelve [].

    Examples:
        >>> # Con FakeEmbedder de vectores idénticos, todos los jobs van al mismo cluster
        >>> clusters = semantic_cluster([j1, j2, j3], fake_embedder_identico, umbral=0.85)
        >>> len(clusters)  # 1 cluster con los 3 jobs
        1
    """
    if not jobs:
        return []

    # Paso 1-2: construir textos y obtener embeddings L2-normalizados
    textos = [build_embed_text(j, desc_words) for j in jobs]
    embeddings: np.ndarray = embedder.embed(textos)  # shape (n, dim), float32

    n = len(embeddings)

    # Paso 3: matriz de similitud coseno (dot product válido porque los vecs son L2-norm)
    sim_matrix: np.ndarray = embeddings @ embeddings.T  # shape (n, n)

    # Paso 4: clip de precisión float32 (T-02-09 — valores como 1.0000001 rompen umbral)
    np.clip(sim_matrix, -1.0, 1.0, out=sim_matrix)

    # Paso 5: clustering greedy
    asignado = [-1] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if asignado[i] >= 0:
            continue  # ya fue asignado a un cluster anterior

        # Abrir nuevo cluster con job i como semilla
        cluster_idx = len(clusters)
        cluster: list[int] = [i]
        asignado[i] = cluster_idx

        # Añadir jobs j > i no asignados con similitud suficiente
        for j in range(i + 1, n):
            if asignado[j] < 0 and sim_matrix[i, j] >= umbral:
                cluster.append(j)
                asignado[j] = cluster_idx

        clusters.append(cluster)

    logger.debug(
        "semantic_cluster: %d jobs → %d clusters (umbral=%.2f)",
        n, len(clusters), umbral,
    )
    return clusters
