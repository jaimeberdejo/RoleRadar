"""
puesto_match.py — Resolver de ranking de puestos por similitud coseno (BGE-M3).

Purpose
-------
Dado el título de una oferta y la lista ordenada de ``PuestoRanking`` del perfil del
usuario, determina cuál entrada del ranking coincide mejor con el título.  Devuelve
``(puesto_detectado, rango_puesto)`` listos para que scorer.py los pase a
``encaje_puesto_desde_rango()`` de ranking.py.

Why TYPE_CHECKING guard?
------------------------
Pitfall 7 de la fase de investigación: importar ``app.dedup.embedder`` a nivel de
módulo arrastra ``sentence-transformers`` y ``torch`` al proceso, lo que causa
~2-4 segundos de inicialización y puede romper tests en CI sin GPU.  Por eso
``Embedder`` solo se importa bajo ``TYPE_CHECKING``; en tiempo de ejecución el
parámetro es duck-typed (cualquier objeto con ``.embed()``).

Threshold default and justification
------------------------------------
``UMBRAL_PUESTO_DEFAULT = 0.55``

BGE-M3 produce vectores L2-normalizados; el producto punto equivale a la similitud
coseno.  Valores empíricos de referencia:

  - "AI Engineer"  vs  "Ingeniero de IA / AI Engineer"  → coseno ≈ 0.75–0.85
  - "Data Engineer" vs "Data Engineer, Remote"           → coseno ≈ 0.90+
  - "AI Engineer"  vs  "Contable Senior"                 → coseno ≈ 0.25–0.35

El margen entre matches reales (~0.70+) y falsos positivos (<0.40) es amplio;
0.55 da holgura suficiente contra ruido sin excluir sinónimos razonables.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from app.models.schemas import PuestoRanking

if TYPE_CHECKING:
    from app.dedup.embedder import Embedder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración exportada
# ---------------------------------------------------------------------------

UMBRAL_PUESTO_DEFAULT: float = 0.55
"""Similitud coseno mínima para considerar que un título coincide con una entrada
del ranking.  0.55 se eligió para dejar margen entre matches reales (≥0.70 típico
con BGE-M3) y no-matches (≤0.40).  Es ajustable por llamador."""


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def match_puesto_por_coseno(
    title: str,
    ranking: list[PuestoRanking],
    embedder: "Embedder",  # duck-typed en runtime; TYPE_CHECKING solo
    *,
    umbral: float = UMBRAL_PUESTO_DEFAULT,
) -> tuple[str, int | None]:
    """Resuelve qué entrada del ranking de puestos corresponde a un título de oferta.

    Compara el título de la oferta contra cada entrada del ranking (título +
    sinónimos concatenados) usando similitud coseno con embeddings BGE-M3
    L2-normalizados.  El coseno se calcula como producto punto (dot == cosine para
    vectores normalizados).

    Args:
        title:    Título de la oferta a evaluar (texto libre).
        ranking:  Lista ordenada de ``PuestoRanking``; índice 0 = máxima prioridad.
        embedder: Objeto con ``.embed(texts: list[str]) -> np.ndarray`` L2-normalizado.
                  No debe ser None (se lanza ``ValueError`` si lo es).
        umbral:   Similitud coseno mínima para considerar un match.
                  Por defecto ``UMBRAL_PUESTO_DEFAULT`` (0.55).

    Returns:
        ``(puesto_detectado, rango_puesto)`` donde:
        - ``puesto_detectado`` es el ``titulo`` de la entrada del ranking que mejor
          coincide, o ``"fuera de ranking"`` si ninguna supera el umbral.
        - ``rango_puesto`` es la posición 1-based en el ranking, o ``None`` si
          ninguna entrada supera el umbral.

    Raises:
        ValueError: Si ``embedder`` es ``None``.

    Examples:
        >>> from app.dedup.embedder import FakeEmbedder
        >>> import numpy as np
        >>> ranking = [PuestoRanking(titulo="AI Engineer", sinonimos=["LLM Engineer"])]
        >>> v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        >>> puesto, rango = match_puesto_por_coseno("AI Engineer", ranking, FakeEmbedder(default_vector=v))
        >>> rango
        1
    """
    # Guard: embedder obligatorio
    if embedder is None:
        raise ValueError(
            "embedder es requerido para match_puesto_por_coseno. "
            "Pasa un Embedder (BgeM3Embedder en producción, FakeEmbedder en tests)."
        )

    # Guard: ranking vacío → fuera de ranking
    if not ranking:
        logger.debug("match_puesto_por_coseno: ranking vacío → fuera de ranking (title=%r)", title)
        return ("fuera de ranking", None)

    # Construir textos del corpus: título + sinónimos de cada entrada del ranking.
    # Concatenar título y sinónimos en un solo texto por entrada maximiza la
    # similitud semántica cuando la oferta usa variantes como "LLM Engineer" o
    # "GenAI Engineer" en lugar del título canónico "AI Engineer".
    # SC3: "cosine between the job title and the ranking entries (+synonyms)".
    corpus_texts: list[str] = [
        " ".join([entry.titulo, *entry.sinonimos]).strip() for entry in ranking
    ]

    # Embed en UNA sola llamada (batch efficiency):
    #   posición 0 = vector del título de la oferta
    #   posiciones 1..N = vectores de cada entrada del ranking
    all_texts = [title] + corpus_texts
    embeddings = embedder.embed(all_texts)  # shape (1 + len(ranking), dim)

    title_vec: np.ndarray = embeddings[0]        # shape (dim,)
    corpus_vecs: np.ndarray = embeddings[1:]     # shape (len(ranking), dim)

    # Cosines = corpus_vecs @ title_vec (dot == cosine porque L2-normalizados)
    cosines: np.ndarray = corpus_vecs @ title_vec  # shape (len(ranking),)

    best_idx: int = int(np.argmax(cosines))
    best_cosine: float = float(cosines[best_idx])

    if best_cosine < umbral:
        logger.debug(
            "match_puesto_por_coseno: %r → fuera de ranking "
            "(best_cosine=%.3f < umbral=%.3f)",
            title,
            best_cosine,
            umbral,
        )
        return ("fuera de ranking", None)

    # rango es 1-based (índice 0 del ranking = rango 1 = máxima prioridad)
    rango_puesto: int = best_idx + 1
    puesto_detectado: str = ranking[best_idx].titulo

    logger.debug(
        "match_puesto_por_coseno: %r → %r (rango=%d, cosine=%.3f)",
        title,
        puesto_detectado,
        rango_puesto,
        best_cosine,
    )

    return (puesto_detectado, rango_puesto)
