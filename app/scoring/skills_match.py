"""
skills_match.py — Scorer de encaje_skills por similitud coseno (BGE-M3).

Purpose
-------
Compara el texto del CV del candidato (habilidades + tecnologías de experiencia)
contra la descripción de la oferta usando similitud coseno con embeddings BGE-M3.
Devuelve un entero 0-100 que representa el encaje semántico de skills.

Este módulo es independiente: no importa app.scoring.ranking ni app.models.
El llamador (scorer.py) construye el ``cv_text`` a partir del ``CVProfile``
antes de invocar esta función.

Why TYPE_CHECKING guard?
------------------------
Pitfall 7: importar ``app.dedup.embedder`` a nivel de módulo arrastra
``sentence-transformers`` y ``torch`` al proceso, causando lentitud en tests
y fallos en CI sin GPU.  El parámetro ``embedder`` es duck-typed en runtime.

Cosine-to-score linear mapping
-------------------------------
BGE-M3 produce vectores L2-normalizados; el producto punto equivale a coseno.

  cosine ∈ [-1.0, 1.0]  (en la práctica, textos positivos: [0.0, 1.0])
  score = int(round(max(0.0, min(1.0, cosine)) * 100))

Tabla de referencia:
  ┌─────────────────┬───────┐
  │ Coseno          │ Score │
  ├─────────────────┼───────┤
  │  1.00           │  100  │
  │  0.80           │   80  │
  │  0.72           │   72  │
  │  0.50           │   50  │
  │  0.00           │    0  │
  │ -0.10 (raro)    │    0  │  ← clamp a 0; cosenos negativos son anómalos
  └─────────────────┴───────┘

CV_SKILLS_TEXT_MAX_TOKENS
--------------------------
Cap de 500 caracteres sobre el texto de CV antes de enviarlo al embedder.
BGE-M3 soporta hasta 8192 tokens, y el texto de skills+experience típico
es < 200 tokens; el cap protege contra entradas patológicas sin perder
información relevante en condiciones normales.  El truncado es a nivel de
caracteres (aproximación conservadora; 500 chars ≈ 100-125 tokens en inglés/español).
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.dedup.embedder import Embedder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración exportada
# ---------------------------------------------------------------------------

CV_SKILLS_TEXT_MAX_TOKENS: int = 500
"""Cap de caracteres para el texto de CV antes de embeber.

BGE-M3 acepta hasta 8192 tokens, pero el texto de skills+experience del CV
raramente supera los 200 tokens.  500 caracteres es un límite conservador que
cubre el texto real sin riesgo de costes o timeouts inesperados.
"""


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def encaje_skills_por_coseno(
    cv_text: str,
    job_description: str,
    embedder: "Embedder",  # duck-typed en runtime; TYPE_CHECKING solo
) -> int:
    """Calcula el encaje de skills entre el candidato y una oferta por similitud coseno.

    Usa embeddings BGE-M3 L2-normalizados, por lo que el producto punto equivale
    a la similitud coseno.  El resultado se mapea linealmente al rango 0-100.

    Args:
        cv_text:         Texto del CV del candidato (skills + tecnologías de experiencia).
                         Debe ser no-vacío.  Se trunca a ``CV_SKILLS_TEXT_MAX_TOKENS``
                         caracteres antes de embeber.
        job_description: Descripción de la oferta.  Si está vacía o es solo espacios,
                         se devuelve 0 (neutral) con un WARNING en el log.
        embedder:        Objeto con ``.embed(texts: list[str]) -> np.ndarray``
                         L2-normalizado.  No puede ser None.

    Returns:
        Entero en [0, 100].  Mapeo: ``int(round(max(0.0, cosine) * 100))``.
        - Coseno 1.0  → 100  (textos semánticamente idénticos)
        - Coseno 0.5  →  50  (encaje parcial)
        - Coseno 0.0  →   0  (sin relación semántica)
        - Coseno < 0  →   0  (anti-correlación; clampado a 0)

    Raises:
        ValueError: Si ``embedder`` es ``None``.
        ValueError: Si ``cv_text`` está vacío o contiene solo espacios en blanco.

    Examples:
        >>> from app.dedup.embedder import FakeEmbedder
        >>> import numpy as np
        >>> vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        >>> score = encaje_skills_por_coseno("Python FastAPI", "We need Python", FakeEmbedder(default_vector=vec))
        >>> score
        100
    """
    # Guard 1: embedder obligatorio
    if embedder is None:
        raise ValueError(
            "embedder es requerido para encaje_skills_por_coseno. "
            "Pasa un Embedder (BgeM3Embedder en producción, FakeEmbedder en tests)."
        )

    # Guard 2: cv_text no puede estar vacío
    if not cv_text or not cv_text.strip():
        raise ValueError(
            "cv_text no puede estar vacío. "
            "Construye el texto del CV antes de llamar a encaje_skills_por_coseno "
            "(ej. skills_tecnicas + tecnologías de experiencia)."
        )

    # Guard 3: descripción vacía → 0 neutral (advertencia, no error)
    if not job_description or not job_description.strip():
        logger.warning(
            "encaje_skills_por_coseno: job_description vacía → devolviendo 0 (neutral). "
            "La oferta podría no tener descripción disponible."
        )
        return 0

    # Truncar cv_text a CV_SKILLS_TEXT_MAX_TOKENS caracteres (aprox. protección)
    cv_text_truncated = cv_text[:CV_SKILLS_TEXT_MAX_TOKENS]

    # Embed en UNA sola llamada (batch efficiency):
    #   posición 0 = vector del texto de CV
    #   posición 1 = vector de la descripción de la oferta
    embeddings = embedder.embed([cv_text_truncated, job_description])
    cv_vec: np.ndarray = embeddings[0]   # shape (dim,)
    job_vec: np.ndarray = embeddings[1]  # shape (dim,)

    # Coseno = producto punto (vectores L2-normalizados: dot == cosine)
    cosine: float = float(np.dot(cv_vec, job_vec))

    # WR-02: NaN guard — a zero-norm embedding produces NaN via 0/0 in L2
    # normalisation; int(round(NaN)) raises ValueError and crashes the batch.
    # Treat NaN as 0 (neutral — no meaningful signal).
    if math.isnan(cosine):
        logger.warning(
            "encaje_skills_por_coseno: cosine es NaN (vector de norma cero) → "
            "devolviendo 0 (neutral)"
        )
        return 0

    # Mapeo lineal al rango 0-100; clamp para cosenos negativos (anómalos pero posibles)
    score: int = int(round(max(0.0, min(1.0, cosine)) * 100))

    logger.debug(
        "encaje_skills_por_coseno: cosine=%.4f → score=%d",
        cosine,
        score,
    )

    return score
