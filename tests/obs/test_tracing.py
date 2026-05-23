"""Tests del módulo app/obs/tracing.py (OBS-02).

Cubre:
- No-op sin env vars: trace_llm() es no-op cuando LANGFUSE_PUBLIC_KEY y
  LANGFUSE_SECRET_KEY están ausentes (el caso por defecto en CI/dev).
- No-op aunque las env vars estén puestas pero langfuse no esté instalado
  (langfuse está ausente de pyproject.toml — el caso real del proyecto).
- Import-safety: importar app.obs.tracing no importa langfuse (verifica que
  "langfuse" no aparece en sys.modules tras el import).
- El cuerpo del with se ejecuta exactamente una vez (trace_llm no salta el bloque).
- IN-01: langfuse instalado pero Langfuse() lanza RuntimeError → no-op, body ejecutado.

Estrategia de reload:
  _LANGFUSE_CONFIGURED se evalúa UNA VEZ al importar el módulo. Para probar
  el comportamiento con env vars distintas a las del entorno actual, se usa
  monkeypatch.setenv / monkeypatch.delenv + importlib.reload(app.obs.tracing)
  para forzar una re-evaluación del flag. Tras el test se hace reload de nuevo
  para restaurar el estado original.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest


def _reload_tracing():
    """Recarga app.obs.tracing para re-evaluar _LANGFUSE_CONFIGURED."""
    import app.obs.tracing  # noqa: PLC0415
    importlib.reload(app.obs.tracing)
    return app.obs.tracing


def test_noop_sin_env_vars(monkeypatch):
    """Con env vars ausentes, trace_llm() ejecuta el bloque interno sin lanzar."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    tracing = _reload_tracing()
    assert not tracing._LANGFUSE_CONFIGURED, "Flag debe ser False sin env vars"

    executed = []
    with tracing.trace_llm("test_op", meta="value"):
        executed.append(1)

    assert executed == [1], "El cuerpo del with debe ejecutarse exactamente una vez"


def test_noop_con_env_vars_pero_langfuse_ausente(monkeypatch):
    """Con env vars puestas pero langfuse no instalado, trace_llm() es no-op y no lanza.

    En el entorno del proyecto, langfuse NO está instalado (ausente de pyproject.toml).
    El segundo guard (except ImportError) hace el yield silencioso.
    """
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test-abc123")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test-def456")

    tracing = _reload_tracing()
    assert tracing._LANGFUSE_CONFIGURED, "Flag debe ser True con ambas env vars presentes"

    executed = []
    # langfuse no está instalado → ImportError → yield silencioso
    with tracing.trace_llm("test_op_configured", model="claude"):
        executed.append(1)

    assert executed == [1], "El cuerpo del with debe ejecutarse exactamente una vez aunque langfuse no esté instalado"


def test_import_safety():
    """Importar app.obs.tracing no debe importar langfuse (langfuse-free)."""
    # Asegurarse de que langfuse no está en sys.modules antes del test
    langfuse_keys = [k for k in sys.modules if "langfuse" in k]
    for k in langfuse_keys:
        del sys.modules[k]

    # Importar el módulo de tracing
    import app.obs.tracing  # noqa: PLC0415
    importlib.reload(app.obs.tracing)  # forzar re-import limpio

    langfuse_in_modules = [k for k in sys.modules if "langfuse" in k]
    assert not langfuse_in_modules, (
        f"Importar app.obs.tracing no debe arrastrar langfuse, "
        f"pero se encontró en sys.modules: {langfuse_in_modules}"
    )


def test_cuerpo_se_ejecuta_exactamente_una_vez(monkeypatch):
    """El bloque del with se ejecuta exactamente una vez, no cero ni dos veces."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    tracing = _reload_tracing()

    counter = 0
    with tracing.trace_llm("count_op"):
        counter += 1

    assert counter == 1, f"El bloque debe ejecutarse exactamente una vez, obtuvo {counter}"


def test_no_lanza_aunque_cuerpo_lanza(monkeypatch):
    """trace_llm() no suprime excepciones lanzadas dentro del bloque (comportamiento correcto).

    Un context manager no-op correcto propaga las excepciones del cuerpo normalmente.
    """
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    tracing = _reload_tracing()

    with pytest.raises(ValueError, match="test error"):
        with tracing.trace_llm("error_op"):
            raise ValueError("test error")


def test_noop_cuando_langfuse_init_falla(monkeypatch):
    """Langfuse instalado pero Langfuse() lanza RuntimeError → no-op, body ejecutado.

    IN-01: cubre el escenario de CR-01 donde langfuse está instalado y configurado
    pero la construcción de Langfuse() falla (auth error, config error, etc.).
    El body de la llamada LLM SIEMPRE debe ejecutarse; la excepción de Langfuse
    NO debe propagarse al llamador.
    """
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    # Inyectar un módulo langfuse falso en sys.modules para que el 'from langfuse import Langfuse'
    # dentro de trace_llm no lance ImportError, pero sí RuntimeError al instanciar Langfuse().
    class BrokenLangfuse:
        def __init__(self) -> None:
            raise RuntimeError("config error simulado")

    fake_langfuse_module = types.ModuleType("langfuse")
    fake_langfuse_module.Langfuse = BrokenLangfuse  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "langfuse", fake_langfuse_module)

    tracing = _reload_tracing()
    assert tracing._LANGFUSE_CONFIGURED, "Flag debe ser True con ambas env vars presentes"

    executed = []
    with tracing.trace_llm("failing_op"):
        executed.append(1)

    assert executed == [1], "Body debe ejecutarse aunque Langfuse() falle (CR-01)"
