"""Paquete de observabilidad: configuración de logging estructurado (OBS-01) y stub de tracing de Langfuse (OBS-02)."""
from __future__ import annotations

from app.obs.logging_config import configure_logging
from app.obs.tracing import trace_llm

__all__ = ["configure_logging", "trace_llm"]
