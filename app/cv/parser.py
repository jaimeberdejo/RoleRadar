"""
Orquestador público de parseo de CV.

Implementa la interfaz pública `parse_cv(pdf_bytes) -> CVProfile` que:
  1. Comprueba la caché por sha256 del contenido del PDF (CV-03).
  2. Si hay hit: devuelve el CVProfile cacheado sin invocar el LLM.
  3. Si no hay hit: extrae texto con pymupdf → llama al LLM (instructor) →
     guarda en caché → devuelve el CVProfile.

Este módulo es el único punto de entrada para consumidores externos (n8n,
endpoints FastAPI). Importa exclusivamente vía los módulos hoja ya construidos
(extractor, cache, llm_client) para mantener responsabilidades separadas.
"""
from __future__ import annotations

from app.cv.cache import load_cached_profile, pdf_hash, save_cached_profile
from app.cv.extractor import extract_text_from_pdf
from app.cv.llm_client import build_instructor_client, extract_cv_profile
from app.models.schemas import CVProfile


def parse_cv(pdf_bytes: bytes) -> CVProfile:
    """Interfaz pública de la fase: PDF bytes → CVProfile tipado.

    Flujo cache-first (CV-03): el sha256 del PDF se comprueba ANTES de
    cualquier extracción o llamada al LLM para que el mismo PDF no se
    reprocese.

    Args:
        pdf_bytes: Contenido crudo del fichero PDF en memoria.

    Returns:
        CVProfile con la información extraída y validada por Pydantic.

    Raises:
        ValueError: Si el PDF no contiene texto extraíble (propagado desde
            extractor.py — PDFs escaneados sin capa de texto).
    """
    h = pdf_hash(pdf_bytes)
    cached = load_cached_profile(h)
    if cached is not None:
        return cached
    raw_text = extract_text_from_pdf(pdf_bytes)
    client = build_instructor_client()
    profile = extract_cv_profile(raw_text, client)
    save_cached_profile(h, profile)
    return profile
