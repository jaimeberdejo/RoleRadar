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
import os
from pathlib import Path

from app.models.schemas import CVProfile

# Directorio por defecto — documentado aquí para referencia. Las funciones
# usan _cache_dir() en lugar de este símbolo para respetar cambios en el env.
CACHE_DIR: Path = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))


def _cache_dir() -> Path:
    """Devuelve el directorio de caché actual, leyendo CV_CACHE_DIR en tiempo de llamada."""
    return Path(os.getenv("CV_CACHE_DIR", "data/.cache"))


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
        CVProfile deserializado, o None si no hay entrada en caché.
    """
    cache_file = _cache_dir() / f"{content_hash}.json"
    if cache_file.exists():
        return CVProfile.model_validate_json(cache_file.read_text())
    return None


def save_cached_profile(content_hash: str, profile: CVProfile) -> None:
    """Persiste un CVProfile en disco bajo el hash dado.

    Crea el directorio de caché si no existe. El fichero se nombra
    ``{content_hash}.json`` y contiene JSON con sangría para legibilidad.

    Args:
        content_hash: Hash sha256 del PDF original (obtenido con pdf_hash()).
        profile: CVProfile a serializar y guardar.
    """
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{content_hash}.json"
    cache_file.write_text(profile.model_dump_json(indent=2))
