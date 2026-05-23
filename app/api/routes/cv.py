"""Router de parseo de CV.

Expone:
    POST /cv/parse — recibe un PDF (multipart UploadFile), lo pasa a parse_cv(),
                     escribe el puntero _current en el directorio de caché y
                     devuelve el CVProfile resultante.

Seguridad (T-04-08):
    - Valida content_type: solo PDF o application/octet-stream.
    - Sanity de tamaño: rechaza ficheros > MAX_PDF_BYTES (10 MB).
    - Los bytes nunca se escriben a disco con nombre controlado por el cliente;
      el cache usa sha256 del contenido (patrón heredado de app/cv/cache.py).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import instructor
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_cv_llm_client
from app.cv.cache import pdf_hash
from app.cv.parser import parse_cv
from app.errors import CVParseError
from app.models.schemas import CVProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cv", tags=["cv"])

# Límite de tamaño de fichero: 10 MB (T-04-08 — DoS mitigation)
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB

_ACCEPTED_CONTENT_TYPES = ("application/pdf", "application/octet-stream")


@router.post("/parse", response_model=CVProfile)
async def parse_cv_endpoint(
    file: UploadFile = File(..., description="CV en formato PDF"),
    client: instructor.Instructor = Depends(get_cv_llm_client),
) -> CVProfile:
    """Parsea el CV (PDF) y devuelve el CVProfile cacheado.

    Escribe el puntero _current en CV_CACHE_DIR para que los endpoints
    /jobs/score y /jobs/process puedan encontrar el CVProfile vía
    get_cached_cv_profile (Plan 01).

    Args:
        file:   Fichero PDF subido como multipart form-data.
        client: Cliente instructor inyectable (sobreescrito en tests).

    Returns:
        CVProfile extraído y cacheado.

    Raises:
        HTTPException 400: Si el tipo de fichero no es PDF, el fichero supera
            el tamaño máximo o el PDF no contiene texto extraíble.
    """
    # Validar content_type (T-04-08)
    if file.content_type not in _ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan ficheros PDF.",
        )

    # await ES OBLIGATORIO — UploadFile.read() es corrutina (Pitfall 3 de RESEARCH.md)
    pdf_bytes = await file.read()

    # Sanity de tamaño (T-04-08 — DoS mitigation)
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Fichero demasiado grande. Máximo permitido: {MAX_PDF_BYTES // 1024 // 1024} MB.",
        )

    # Delegar a parse_cv (cache-first: si ya existe en caché lo devuelve sin LLM)
    # Pasar el cliente inyectado para que dependency_overrides sea efectivo en tests
    # y para que la trazabilidad Langfuse funcione en Fase 5 (CR-01 Option B).
    try:
        profile = parse_cv(pdf_bytes, client=client)
    except ValueError as exc:
        # Mapear ValueError (PDF sin texto extraíble) a CVParseError para que el
        # handler tipado de main.py devuelva un envelope {"error": {"type": "CVParseError"}}
        # consistente con el resto de errores de dominio (WR-02).
        raise CVParseError(str(exc)) from exc

    # Escribir _current con el hash activo para que get_cached_cv_profile lo encuentre
    cache_dir = Path(os.getenv("CV_CACHE_DIR", "data/.cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "_current").write_text(pdf_hash(pdf_bytes), encoding="utf-8")

    logger.info(
        "parse_cv_endpoint: CV parseado y cacheado. skills=%d",
        len(profile.skills_tecnicas),
    )
    return profile
