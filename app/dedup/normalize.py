"""
Funciones de normalización de texto para el pipeline de deduplicación.

Responsabilidades:
  - normalize_field: normalización NFD (strip de acentos) + casefold + colapso de espacios.
  - stable_job_id:   hash sha256 de 64 caracteres hexadecimales estable entre runs.

Estas funciones son puras (stdlib only) y no tienen dependencias externas.
Patrón análogo a app/cv/cache.py: mismo estilo sha256 + logger de módulo.

NOTA sobre location=None:
  El caller debe pasar "" cuando location es None para evitar TypeError en
  normalize_field. Los mappers hacen ``location or ""`` antes de llamar.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


def normalize_field(s: str) -> str:
    """Normaliza un campo de texto para comparación estable.

    Pasos:
    1. Descomposición NFD (unicode.normalize "NFD") — separa base + combining marks.
    2. Filtrado de categoría "Mn" (Nonspacing_Mark = diacríticos/acentos).
    3. casefold() — minúsculas Unicode-aware (más agresivo que lower()).
    4. strip() + colapso de espacios múltiples con re.sub.

    IMPORTANTE: usa NFD, no NFC. NFC recompone los caracteres acentuados (é, ñ)
    y NO permite quitarlos. NFD los descompone en base + combining mark, lo que
    permite filtrar la mark (Pitfall 2 de RESEARCH.md).

    Args:
        s: Cadena a normalizar.

    Returns:
        Cadena normalizada sin acentos, en minúsculas y sin espacios extra.

    Examples:
        >>> normalize_field("Ácmé Corp") == normalize_field("Acme Corp")
        True
        >>> normalize_field("  AI   Engineer  ")
        'ai engineer'
    """
    # Paso 1: NFD — descompone caracteres acentuados
    s = unicodedata.normalize("NFD", s)
    # Paso 2: quitar combining marks (acentos, tildes, cedillas, etc.)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    # Paso 3+4: casefold, strip y colapso de espacios
    return re.sub(r"\s+", " ", s.casefold().strip())


def stable_job_id(company: str, title: str, location: str) -> str:
    """Genera un identificador estable para una oferta a partir de sus campos clave.

    Construye la clave ``normalize(company)|normalize(title)|normalize(location)``
    y devuelve el sha256 hexadecimal de 64 caracteres (completo, sin truncar).
    Mismo patrón que app/cv/cache.pdf_hash — consistente con ``_HEX_RE``.

    Args:
        company:  Nombre de la empresa (puede estar sin normalizar).
        title:    Título del puesto (puede estar sin normalizar).
        location: Ubicación de la oferta. Pasar "" si el valor es None.

    Returns:
        Cadena hexadecimal de 64 caracteres (sha256 digest completo).

    Examples:
        >>> len(stable_job_id("Acme Corp", "AI Engineer", "Berlin"))
        64
        >>> stable_job_id("Acme", "Dev", "BCN") == stable_job_id("acme", "dev", "bcn")
        True
    """
    key = (
        normalize_field(company)
        + "|"
        + normalize_field(title)
        + "|"
        + normalize_field(location)
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
