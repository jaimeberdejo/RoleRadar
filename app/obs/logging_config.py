"""Configuración de logging estructurado de BuscadorDeEmpleo (OBS-01).

Expone:
- configure_logging(level=INFO): configura el root logger con formato key=value.

Decisión de diseño:
  Se usa stdlib ``logging`` únicamente — sin dependencias de logging de terceros.
  El formato key=value es grep-able sin parser extra y compatible con cualquier
  log aggregator.

  Guard de idempotencia (WR-01): el nivel se aplica SIEMPRE (incluso si ya
  existen handlers), mientras que el StreamHandler de stdout se añade solo si
  no hay uno ya presente. Esto evita que INFO logs sean descartados silenciosamente
  cuando uvicorn instala sus propios handlers antes del lifespan.
"""
from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """Configura el logging de la aplicación con formato key=value consistente.

    Llamado en el lifespan de la app (app/api/main.py). Idempotente: si ya
    existe un StreamHandler de stdout en el root logger, no añade otro
    (evita handlers duplicados en tests o reloads).

    WR-01: el nivel se aplica SIEMPRE aunque ya existan handlers. Así, si
    uvicorn instala sus handlers antes que lifespan, el nivel INFO solicitado
    se aplica igualmente y los logs de aplicación no quedan silenciados.

    Args:
        level: Nivel de logging para el root logger. Por defecto ``logging.INFO``.
    """
    root = logging.getLogger()
    # Siempre aplicar el nivel solicitado, independientemente de si ya hay handlers
    # (WR-01: sin esto, uvicorn puede dejar el nivel en WARNING y silenciar INFO logs)
    root.setLevel(level)

    # Añadir StreamHandler de stdout solo si no hay uno ya presente (evita duplicados)
    if any(
        isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
        for h in root.handlers
    ):
        return  # StreamHandler a stdout ya presente — no duplicar (Pitfall 3)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root.addHandler(handler)
