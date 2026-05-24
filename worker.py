"""Worker BuscadorDeEmpleo — proceso de fondo con APScheduler.

Punto de entrada del contenedor `worker` en docker-compose.yml.
En Fase 8 se implementará el pipeline completo; esta versión es un stub
que arranca el scheduler vacío para que el contenedor permanezca activo.

NO instanciar APScheduler dentro de Streamlit — este módulo corre en un
proceso separado.
"""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Pipeline principal — implementado en Fase 8."""
    logger.info("Pipeline stub: no implementado aún (Fase 8)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Worker arrancando (stub — Fase 8 implementa el pipeline)")

    # Leer el intervalo desde la settings table (fuente de verdad configurable).
    # Fallback a 6 si la DB no está disponible todavía o la clave no existe.
    _DEFAULT_INTERVAL_HOURS = 6
    try:
        from app.storage import get_storage_backend  # noqa: PLC0415

        _storage = get_storage_backend()
        _settings = _storage.get_settings()
        interval_hours: int = int(_settings.get("schedule_interval_hours", str(_DEFAULT_INTERVAL_HOURS)))
    except Exception as _exc:  # noqa: BLE001
        logger.warning(
            "No se pudo leer schedule_interval_hours de la DB (%s) — usando default %dh",
            _exc,
            _DEFAULT_INTERVAL_HOURS,
        )
        interval_hours = _DEFAULT_INTERVAL_HOURS

    logger.info("Intervalo del scheduler: %d horas", interval_hours)
    scheduler = BlockingScheduler(
        timezone=ZoneInfo("Europe/Madrid"),
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": 3600,
            "max_instances": 1,
        },
    )
    scheduler.add_job(run_pipeline, "interval", hours=interval_hours, id="pipeline")
    scheduler.start()
