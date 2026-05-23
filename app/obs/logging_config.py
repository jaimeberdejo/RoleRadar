"""Configuración de logging estructurado de BuscadorDeEmpleo (OBS-01).

Expone:
- configure_logging(level=INFO): configura el root logger con formato key=value.

Decisión de diseño:
  Se usa stdlib ``logging`` únicamente — sin dependencias de logging de terceros.
  El formato key=value es grep-able sin parser extra y compatible con cualquier
  log aggregator.

  Guard de idempotencia: si el root logger ya tiene handlers, retorna inmediato
  sin añadir otro. Evita duplicar handlers en tests o reloads (Pitfall 3).
"""
from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logging de la aplicación con formato key=value consistente.

    Llamado en el lifespan de la app (app/api/main.py). Idempotente: si ya
    existe un StreamHandler de stdout en el root logger, no añade otro
    (evita handlers duplicados en tests o reloads).

    Args:
        level: Nivel de logging para el root logger. Por defecto ``logging.INFO``.
    """
    root = logging.getLogger()
    if root.handlers:
        return  # ya configurado — no duplicar handlers (Pitfall 3)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level)
