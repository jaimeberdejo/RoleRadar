"""Tests del módulo app/obs/logging_config.py (OBS-01).

Cubre:
- Idempotencia: configure_logging() llamada dos veces no añade handlers duplicados.
- Formato key=value: el formatter instalado incluye los tokens level= y logger=.
- Nivel: configure_logging(level=logging.DEBUG) deja el root logger en DEBUG.

Nota sobre el entorno pytest:
  pytest instala LogCaptureHandler en el root logger alrededor de cada test.
  Los tests guardan y restauran el estado del root logger AL FINAL para no
  contaminar otros tests. La limpieza para el test en sí ocurre dentro del
  cuerpo del test (justo antes de la llamada), ya que pytest re-inserta sus
  handlers después de que un fixture setup los limpie.
"""
from __future__ import annotations

import logging
import sys

import pytest

from app.obs.logging_config import configure_logging


@pytest.fixture()
def restore_root():
    """Restaura el root logger a su estado previo al finalizar el test.

    No limpia los handlers en setup — eso se hace dentro del cuerpo del test,
    justo antes de la llamada a configure_logging(), para evitar que los
    LogCaptureHandler de pytest se reinsertan entre setup y la llamada.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    yield root
    # Restaurar exactamente el estado previo
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_idempotencia(restore_root):
    """Llamar configure_logging() dos veces no añade un segundo StreamHandler."""
    root = restore_root

    # Limpiar handlers justo antes de configure_logging() para estado conocido.
    # Hacerlo aquí (no en fixture setup) garantiza que no haya handlers de pytest
    # entre la limpieza y la llamada a configure_logging().
    root.handlers[:] = []
    assert len(root.handlers) == 0, "Precondición: root sin handlers"

    configure_logging()
    after_first = len(root.handlers)
    assert after_first == 1, (
        f"Primera llamada debe añadir exactamente 1 handler, obtuvo {after_first}"
    )

    configure_logging()
    after_second = len(root.handlers)
    assert after_second == after_first, (
        f"Segunda llamada no debe añadir handlers "
        f"(esperado {after_first}, obtenido {after_second})"
    )


def test_formato_key_value(restore_root):
    """El formatter instalado incluye los tokens level= y logger= (formato key=value)."""
    root = restore_root

    root.handlers[:] = []
    configure_logging()

    assert root.handlers, "configure_logging() debe haber instalado al menos un handler"
    handler = root.handlers[0]
    fmt = handler.formatter._fmt if handler.formatter else ""

    assert "level=%(levelname)s" in fmt, (
        f"El formatter debe incluir 'level=%(levelname)s', pero fmt={fmt!r}"
    )
    assert "logger=%(name)s" in fmt, (
        f"El formatter debe incluir 'logger=%(name)s', pero fmt={fmt!r}"
    )


def test_nivel(restore_root):
    """configure_logging(level=DEBUG) deja el root logger con level DEBUG."""
    root = restore_root

    root.handlers[:] = []
    configure_logging(level=logging.DEBUG)

    assert root.level == logging.DEBUG, (
        f"El root logger debe estar en DEBUG tras configure_logging(level=DEBUG), "
        f"pero está en {logging.getLevelName(root.level)}"
    )
