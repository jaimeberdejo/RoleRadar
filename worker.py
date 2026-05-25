"""Worker BuscadorDeEmpleo — proceso de fondo con APScheduler.

Punto de entrada del contenedor `worker` en docker-compose.yml.
El pipeline real se implementa en app/pipeline.py (compartido con la UI).
Este módulo solo gestiona el scheduler y delega la lógica al pipeline.

NO instanciar APScheduler dentro de Streamlit — este módulo corre en un
proceso separado.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app.pipeline import run_pipeline as _pipeline_run  # noqa: E402

logger = logging.getLogger(__name__)


def run_pipeline() -> None:
    """Wrapper del scheduler: llama al pipeline compartido y loguea el resultado."""
    result = _pipeline_run()
    logger.info(
        "Scheduler pipeline run complete: fetched=%d deduped=%d scored=%d new=%d errors=%d",
        result.fetched,
        result.deduped,
        result.scored,
        result.new_seen,
        len(result.errors),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Worker arrancando — pipeline real (Fase 8)")

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
    scheduler.add_job(
        run_pipeline,
        "interval",
        hours=interval_hours,
        id="pipeline",
        next_run_time=datetime.now(),  # fire immediately on startup, then every N hours
    )
    scheduler.start()
