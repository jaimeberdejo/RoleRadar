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
    scheduler = BlockingScheduler(
        timezone=ZoneInfo("Europe/Madrid"),
        job_defaults={
            "coalesce": True,
            "misfire_grace_time": 3600,
            "max_instances": 1,
        },
    )
    scheduler.add_job(run_pipeline, "interval", hours=6, id="pipeline")
    scheduler.start()
