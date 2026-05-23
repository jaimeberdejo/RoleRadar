"""Proveedores de dependencias inyectables para FastAPI (Depends).

Centraliza todos los Depends factories: LLM clients, embedder, storage y
CVProfile cacheado. Es el seam principal para dependency_overrides en tests.

Todos los imports de librerías pesadas (torch, sentence-transformers, OpenAI)
son DEFERIDOS dentro del cuerpo de cada función — el módulo es importable en
<1 segundo sin disparar descargas ni imports pesados (anti-torch, T-04-03).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import HTTPException, Request

from app.models.schemas import CVProfile

logger = logging.getLogger(__name__)


def get_storage(request: Request):
    """Lee el singleton Storage desde app.state (inicializado en lifespan)."""
    return request.app.state.storage


def get_cv_llm_client():
    """Cliente LLM para parseo de CV. Reemplazable en tests via dependency_overrides."""
    from app.cv.llm_client import build_instructor_client  # noqa: PLC0415
    return build_instructor_client()


def get_scoring_llm_client():
    """Cliente LLM para scoring. Reemplazable en tests via dependency_overrides."""
    from app.scoring.llm import build_instructor_client  # noqa: PLC0415
    return build_instructor_client()


def get_embedder():
    """BGE-M3 embedder. Import DEFERIDO — nunca dispara torch al importar el módulo.

    En tests: siempre se sobreescribe con FakeEmbedder via dependency_overrides
    (T-04-03). El import real de BgeM3Embedder (que arrastra torch) nunca se
    ejecuta durante la colección ni la ejecución de tests.
    """
    from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
    return BgeM3Embedder()


def get_user_profile_dep():
    """Carga el UserProfile desde data/profile.yaml.

    Envuelve FileNotFoundError→404 y ValueError→500 en HTTPException.
    Reemplazable en tests via dependency_overrides.
    """
    from app.config.loader import load_user_profile  # noqa: PLC0415
    try:
        return load_user_profile()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_cached_cv_profile() -> CVProfile:
    """Devuelve el CVProfile cacheado más reciente o lanza HTTPException 404.

    Lee data/.cache/_current para encontrar el hash activo (escrito por /cv/parse).
    Si _current no existe o el fichero JSON no existe → 404 con instrucción
    clara para llamar a POST /cv/parse primero.

    Raises:
        HTTPException 404: si no hay CVProfile cacheado. El detalle menciona
            "/cv/parse" para orientar al usuario/n8n.
    """
    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    current_file = cache_dir / "_current"
    if not current_file.exists():
        raise HTTPException(
            status_code=404,
            detail="No hay CVProfile cacheado. Llama a POST /cv/parse primero.",
        )
    content_hash = current_file.read_text(encoding="utf-8").strip()
    profile_file = cache_dir / f"{content_hash}.json"
    if not profile_file.exists():
        raise HTTPException(
            status_code=404,
            detail="CVProfile cacheado no encontrado. Llama a POST /cv/parse primero.",
        )
    return CVProfile.model_validate_json(profile_file.read_text(encoding="utf-8"))
