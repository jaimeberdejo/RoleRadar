"""
Caché de CVProfile en disco, indexada por sha256 de los bytes del PDF.

Satisface CV-03: el CV no se vuelve a parsear con el LLM si el contenido
no ha cambiado. La caché es un directorio de ficheros JSON, uno por hash.

El directorio de caché es configurable via la variable de entorno CV_CACHE_DIR
(por defecto: data/.cache). Las funciones leen el env var en cada llamada
(enfoque lazy) para que monkeypatch.setenv funcione correctamente en tests.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

from app.models.schemas import CVProfile

logger = logging.getLogger(__name__)

# Patrón que identifica un sha256 hexadecimal válido: exactamente 64 dígitos hex.
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def _cache_dir() -> Path:
    """Devuelve el directorio de caché actual, leyendo CV_CACHE_DIR en tiempo de llamada."""
    return Path(os.getenv("CV_CACHE_DIR", "data/.cache"))


def _validate_hash(content_hash: str) -> None:
    """Valida que content_hash sea un sha256 hexadecimal seguro (64 dígitos hex en minúsculas).

    Raises:
        ValueError: Si el valor no es un sha256 hex válido (previene path traversal).
    """
    if not _HEX_RE.match(content_hash):
        raise ValueError(
            f"Clave de caché inválida: {content_hash!r}. "
            "Se esperaba un sha256 hexadecimal de 64 caracteres."
        )


def pdf_hash(pdf_bytes: bytes) -> str:
    """Calcula el sha256 hexadecimal de los bytes del PDF.

    Args:
        pdf_bytes: Contenido crudo del PDF.

    Returns:
        Cadena hexadecimal de 64 caracteres (sha256 digest).
    """
    return hashlib.sha256(pdf_bytes).hexdigest()


def load_cached_profile(content_hash: str) -> CVProfile | None:
    """Carga un CVProfile desde la caché si existe el fichero para ese hash.

    Args:
        content_hash: Hash sha256 del PDF original (obtenido con pdf_hash()).

    Returns:
        CVProfile deserializado, o None si no hay entrada en caché o el
        fichero está corrupto (en ese caso se elimina el fichero dañado).

    Raises:
        ValueError: Si content_hash no es un sha256 hexadecimal válido.
    """
    _validate_hash(content_hash)
    cache_file = _cache_dir() / f"{content_hash}.json"
    if not cache_file.exists():
        return None
    try:
        return CVProfile.model_validate_json(cache_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "Caché corrupta para hash %s, se ignorará y se eliminará: %s",
            content_hash,
            exc,
        )
        try:
            cache_file.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def save_cached_profile(content_hash: str, profile: CVProfile) -> None:
    """Persiste un CVProfile en disco bajo el hash dado.

    Crea el directorio de caché si no existe. El fichero se nombra
    ``{content_hash}.json`` y contiene JSON con sangría para legibilidad.

    Args:
        content_hash: Hash sha256 del PDF original (obtenido con pdf_hash()).
        profile: CVProfile a serializar y guardar.

    Raises:
        ValueError: Si content_hash no es un sha256 hexadecimal válido.
    """
    _validate_hash(content_hash)
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{content_hash}.json"
    cache_file.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
