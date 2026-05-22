"""Módulo de parseo de CV (FASE 1).

Interfaz pública:
    parse_cv(pdf_bytes: bytes) -> CVProfile
"""

from app.cv.parser import parse_cv

__all__ = ["parse_cv"]
