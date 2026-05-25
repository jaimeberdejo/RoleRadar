"""
Detector determinista de deal-breakers basado en texto.

Responsabilidad: comprobar si el texto de una oferta (título + descripción)
contiene alguno de los deal_breakers del perfil del usuario mediante
coincidencia exacta de subcadena normalizada (NFD + casefold).

Por qué subcadena y NO word-boundary:
    Los deal_breakers son frases en lenguaje natural como
    "exige 5+ años de experiencia" o "presencial fuera de Barcelona".
    Estas frases contienen signos de puntuación ("+"), números y
    palabras compuestas que harían el escapado con \\b complejo y
    frágil. La subcadena normalizada es más simple y suficiente para
    el caso de uso: las frases del perfil son específicas y no hay
    riesgo de falsos positivos con subcadenas cortas.

NFD normalization (replicada localmente, NO importada de location.py):
    La misma convención que scoring/location.py: NFD + filtrar
    categoría Mn (nonspacing marks = acentos/tildes). Replicar aquí
    en lugar de importar evita el acoplamiento cruzado entre submódulos
    de scoring (Pitfall 7: location.py importa app.models.schemas; si
    scoring/deal_breaker.py importase location.py arrastraría esa cadena).
    El helper `_normalizar` es trivial (stdlib only).

Política de múltiples hits:
    Todos los deal_breakers disparados se recogen y se unen con "; "
    en `cual` (mismo patrón que scorer.py CR-02 para campos multi-valor).

Integración con scorer.py:
    El texto de entrada (`job_text`) debe construirse como:
        f"{job.title} {job.description}"
    para que los deal_breakers también detecten palabras clave en el
    título (e.g., "presencial" en "Trabajo Presencial — Madrid").

    Cuando `hit=True`, el scorer DEBE establecer `recommendation=skip`
    independientemente del score_total numérico (filtro duro; CLAUDE.md
    regla de deal-breakers). El score_total se mantiene honesto pero la
    recomendación se sobreescribe.

Dependencias externas: NINGUNA. Solo stdlib (dataclasses, logging, unicodedata).
No importa app.dedup (torch/BGE-M3 avoidance, Pitfall 7 de RESEARCH.md).
"""
from __future__ import annotations

import dataclasses
import logging
import unicodedata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resultado público
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class DealBreakerResult:
    """Resultado de la detección de deal-breakers en el texto de una oferta.

    Attributes:
        hit:  True si al menos un deal_breaker del perfil se encontró en el texto.
        cual: None si hit=False. Si hit=True, el/los deal_breaker(s) disparados,
              unidos con "; " cuando hay varios.
    """

    hit: bool
    cual: str | None  # None si hit=False; string(s) disparados si hit=True


# ---------------------------------------------------------------------------
# Helper privado — NFD normalization (stdlib pura)
# ---------------------------------------------------------------------------


def _normalizar(text: str) -> str:
    """Normaliza texto a minúsculas ASCII para comparación estable.

    Pasos:
    1. Descomposición NFD: separa base + combining marks (acentos).
    2. Filtrado de categoría "Mn" (Nonspacing_Mark = acentos, tildes).
    3. casefold + strip.

    Convención del proyecto (idéntica a scoring/location.py `_normalize_city`).
    No se importa desde location.py para evitar acoplamiento transitivo.

    Ejemplos:
        _normalizar("Exigé 5+ años") → "exige 5+ anos"
        _normalizar("PRESENCIAL FUERA DE BARCELONA") → "presencial fuera de barcelona"
        _normalizar("  Málaga  ") → "malaga"
    """
    nfd = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------


def detectar_deal_breaker(
    job_text: str,
    deal_breakers: list[str],
) -> DealBreakerResult:
    """Detecta deal-breakers en el texto de una oferta mediante subcadena normalizada.

    Comprueba si la versión NFD+casefold de cada deal_breaker del perfil es
    subcadena de la versión NFD+casefold del texto de la oferta.

    Args:
        job_text:      Texto a revisar. Construir como ``f"{job.title} {job.description}"``
                       para que los deal_breakers también detecten palabras en el título.
        deal_breakers: Lista de frases de deal_breaker del ``UserProfile`` del usuario.
                       Puede ser vacía.

    Returns:
        ``DealBreakerResult(hit=False, cual=None)`` si no se detectó ninguno.
        ``DealBreakerResult(hit=True, cual="<frase(s)>")`` si se detectó al menos uno.
        Cuando hay varios hits, ``cual`` contiene todos unidos con ``"; "``.

    Note:
        Esta función es puramente determinista. No realiza ninguna llamada al LLM
        ni a embeddings. Funciona aunque ``OPENAI_API_KEY`` no esté configurada
        (SCORE-13).

        Cuando ``hit=True``, el scorer debe establecer ``recommendation=skip``
        independientemente del score_total (filtro duro — CLAUDE.md deal_breakers).
    """
    # Guard 1: sin texto o sin deal_breakers → imposible hacer match
    if not job_text or not job_text.strip():
        logger.debug("detectar_deal_breaker: job_text vacío → no hit")
        return DealBreakerResult(hit=False, cual=None)

    if not deal_breakers:
        logger.debug("detectar_deal_breaker: deal_breakers vacío → no hit")
        return DealBreakerResult(hit=False, cual=None)

    # Normalizar el texto de la oferta una sola vez (eficiencia)
    job_norm = _normalizar(job_text)

    hits: list[str] = []

    for db in deal_breakers:
        db_norm = _normalizar(db)
        logger.debug(
            "detectar_deal_breaker: comprobando '%s' → norm='%s' en job_norm",
            db,
            db_norm,
        )
        if db_norm in job_norm:
            hits.append(db)  # conservar el string ORIGINAL (legible para el usuario)

    if hits:
        cual = "; ".join(hits)
        logger.info("Deal-breaker detectado: %s", cual)
        return DealBreakerResult(hit=True, cual=cual)

    return DealBreakerResult(hit=False, cual=None)
