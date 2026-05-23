"""Tests del módulo app/obs/logging_config.py (OBS-01).

Cubre:
- Idempotencia: configure_logging() llamada dos veces no añade handlers duplicados.
- Formato key=value: el formatter instalado incluye los tokens level= y logger=.
- Nivel: configure_logging(level=logging.DEBUG) deja el root logger en DEBUG.
"""
from __future__ import annotations

import logging

import pytest

from app.obs.logging_config import configure_logging


@pytest.fixture()
def clean_root_logger():
    """Guarda y restaura el estado del root logger para no contaminar otros tests."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    # Limpiar handlers existentes antes del test para que el estado sea conocido
    root.handlers.clear()
    yield root
    # Restaurar
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_idempotencia(clean_root_logger):
    """Llamar configure_logging() dos veces no añade un segundo StreamHandler."""
    root = clean_root_logger
    assert len(root.handlers) == 0, "Precondición: root sin handlers"

    configure_logging()
    handlers_after_first = len(root.handlers)
    assert handlers_after_first == 1, "Primera llamada debe añadir exactamente 1 handler"

    configure_logging()
    handlers_after_second = len(root.handlers)
    assert handlers_after_second == handlers_after_first, (
        f"Segunda llamada no debe añadir handlers (esperado {handlers_after_first}, "
        f"obtenido {handlers_after_second})"
    )


def test_formato_key_value(clean_root_logger):
    """El formatter instalado incluye los tokens level= y logger= (formato key=value)."""
    configure_logging()
    root = clean_root_logger
    assert root.handlers, "configure_logging() debe haber instalado al menos un handler"
    handler = root.handlers[0]
    fmt = handler.formatter._fmt if handler.formatter else ""
    assert "level=%(levelname)s" in fmt, (
        f"El formatter debe incluir 'level=%(levelname)s', pero fmt={fmt!r}"
    )
    assert "logger=%(name)s" in fmt, (
        f"El formatter debe incluir 'logger=%(name)s', pero fmt={fmt!r}"
    )


def test_nivel(clean_root_logger):
    """configure_logging(level=DEBUG) deja el root logger con level DEBUG."""
    configure_logging(level=logging.DEBUG)
    root = clean_root_logger
    assert root.level == logging.DEBUG, (
        f"El root logger debe estar en DEBUG, pero está en {logging.getLevelName(root.level)}"
    )
