"""Jerarquía de excepciones de dominio para BuscadorDeEmpleo (OBS-03).

Proporciona excepciones tipadas por capa para que los exception handlers de
FastAPI puedan mapear cada error a un código HTTP y envelope JSON apropiados,
sin filtrar detalles internos al cliente.

Uso típico:
    raise CVParseError("No se pudo extraer texto del PDF")
    raise StorageError("Fallo al conectar con la base de datos")
"""
from __future__ import annotations


class BuscadorError(Exception):
    """Base exception para todos los errores de dominio de BuscadorDeEmpleo."""


class CVParseError(BuscadorError):
    """Error durante el parseo del CV (extracción de texto o llamada LLM)."""


class NormalizationError(BuscadorError):
    """Error durante la normalización de una oferta desde su formato crudo."""


class ScoringError(BuscadorError):
    """Error durante el scoring de una oferta (llamada al LLM de evaluación)."""


class StorageError(BuscadorError):
    """Error durante operaciones de persistencia (SQLite o Supabase)."""
