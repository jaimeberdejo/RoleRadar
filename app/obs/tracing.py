"""Stub de tracing de Langfuse para BuscadorDeEmpleo (OBS-02).

INVARIANTE CRÍTICA:
  Importar este módulo NO debe importar langfuse. langfuse es una dependencia
  OPCIONAL — jamás se añade a pyproject.toml; el import es perezoso dentro del
  context manager.

  Análogo a app/dedup/embedder.py: el import de la dependencia pesada/opcional
  ocurre dentro del método que la necesita, marcado con ``# noqa: PLC0415``.

  INVARIANTE DE DEGRADACIÓN ELEGANTE (CR-01):
  Cualquier excepción de Langfuse (init, __enter__, __exit__) NO debe propagarse
  al llamador LLM. Si Langfuse falla en cualquier punto, trace_llm actúa como
  no-op y el body (la llamada LLM) siempre se ejecuta.

Expone:
- trace_llm(name, **meta): context manager que traza una llamada LLM con
  Langfuse cuando está instalado y configurado; no-op silencioso en caso contrario.

Uso típico:
    with trace_llm("assess_job", job_id=job.id, model=model):
        result = client.messages.create(...)
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

# Evaluado UNA VEZ al importar el módulo (anti-pattern: no re-evaluar en cada llamada).
# El flag permanece estable durante el ciclo de vida del proceso; las variables de
# entorno no cambian en runtime en producción. En tests: usar importlib.reload() +
# monkeypatch.setenv() para re-evaluar.
_LANGFUSE_CONFIGURED = bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
    os.environ.get("LANGFUSE_SECRET_KEY")
)


@contextmanager
def trace_llm(name: str, **meta: Any) -> Generator[None, None, None]:
    """Context manager que traza una llamada LLM con Langfuse (si está disponible).

    No-op silencioso cuando:
    - LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY no están en el entorno (primer guard).
    - langfuse no está instalado (ImportError — segundo guard).
    - Langfuse falla en init, __enter__ o __exit__ (tercer guard — CR-01).

    Cuando Langfuse está configurado e instalado, usa la API de Langfuse 4.x
    (OTel-based): ``Langfuse().start_as_current_observation(name=..., as_type="generation")``.

    INVARIANTE: el body (llamada LLM) SIEMPRE se ejecuta, nunca se omite por
    un fallo de Langfuse. Un error de tracing produce un warning en el log pero
    jamás propaga al llamador.

    Args:
        name: Nombre de la observación (ej. "assess_job", "extract_cv_profile").
        **meta: Metadatos adicionales pasados como ``metadata`` a Langfuse.
    """
    if not _LANGFUSE_CONFIGURED:
        # Primer guard: env vars ausentes → no-op inmediato, sin tocar langfuse
        yield
        return

    try:
        from langfuse import Langfuse  # noqa: PLC0415 — import perezoso/opcional
    except ImportError:
        # Segundo guard: langfuse no instalado → no-op silencioso
        yield
        return

    # Tercer guard (CR-01): cualquier fallo de Langfuse (init, __enter__, __exit__)
    # degrada silenciosamente a no-op — el body LLM siempre se ejecuta.
    try:
        lf = Langfuse()
        cm = lf.start_as_current_observation(name=name, as_type="generation", metadata=meta)
        try:
            cm.__enter__()
        except Exception:  # noqa: BLE001
            logger.warning(
                "trace_llm: span enter falló, degradando a no-op (name=%s)", name, exc_info=True
            )
            yield
            return
        try:
            yield
        finally:
            try:
                cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "trace_llm: span exit falló, ignorado (name=%s)", name, exc_info=True
                )
    except Exception:  # noqa: BLE001
        # Langfuse init falló — degradar a no-op silencioso, body LLM siempre ejecuta
        logger.warning(
            "trace_llm: Langfuse init falló, degradando a no-op (name=%s)", name, exc_info=True
        )
        yield
