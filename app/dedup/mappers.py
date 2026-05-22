"""
Registry de mappers de fuentes de empleo.

Cada mapper traduce el payload crudo de una fuente específica → objeto Job normalizado.
Los mappers usan stable_job_id() de normalize.py para generar el id estable.

══════════════════════════════════════════════════════════════════════════════════
AJUSTABLE: Los campos de cada fuente se afina aquí con respuestas reales.
NO asumir estos campos como definitivos — verificar contra responses reales de la
API antes de poner en producción. Ver RESEARCH.md para el shape confirmado de cada
fuente.
══════════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Callable

from app.dedup.normalize import stable_job_id
from app.models.schemas import Job, RemoteJob

logger = logging.getLogger(__name__)

# Tipo alias para las funciones de mapeo
MapperFn = Callable[[dict, str], Job]


# ──────────────────────────────────────────────────────────────────────────────
# AJUSTABLE: arbeitnow_mapper
# Fuente: https://www.arbeitnow.com/api/job-board-api
# Campos confirmados (2026-05-22): slug, company_name, title, description (HTML),
# remote (bool), url, tags (list[str]), job_types (list[str]), location (str),
# created_at (Unix timestamp int). Sin salary en la tier gratuita.
# AJUSTABLE: actualizar si la API añade campos o cambia formatos.
# ──────────────────────────────────────────────────────────────────────────────
def arbeitnow_mapper(raw: dict, source: str) -> Job:
    """Mapea un payload crudo de Arbeitnow a un objeto Job normalizado.

    Arbeitnow Job Board API (https://www.arbeitnow.com/api/job-board-api).

    Campos usados:
      - company_name → Job.company
      - title → Job.title
      - description (HTML) → Job.description (sin tags HTML)
      - remote (bool) → Job.remote (True→remote, False→unknown)
      - url → Job.url
      - location → Job.location
      - created_at (Unix int) → Job.posted_at (ISO 8601)

    AJUSTABLE: ajustar si la API añade campos de salary, nivel de seniority, etc.

    Args:
        raw:    Payload dict de Arbeitnow (un elemento del array "data").
        source: Identificador de la fuente (ej. "arbeitnow").

    Returns:
        Job normalizado con id estable.
    """
    company = raw.get("company_name", "")
    title = raw.get("title", "")
    location = raw.get("location", "")

    # Strip HTML tags de la descripción (Pitfall 6: Arbeitnow usa HTML)
    # El HTML original queda preservado en Job.raw para trazabilidad.
    # `or ""` trata tanto clave ausente como valor None/falsy explícito (WR-01).
    raw_desc = raw.get("description") or ""
    clean_desc = re.sub(r"<[^>]+>", " ", raw_desc).strip()

    # remote bool → enum: True → remote; False → unknown (no inferimos onsite sin evidencia)
    remote_bool = raw.get("remote", False)
    remote_val = RemoteJob.remote if remote_bool else RemoteJob.unknown

    # Convertir Unix timestamp → ISO 8601 con timezone UTC
    created_ts = raw.get("created_at")
    posted_at: str | None = None
    if created_ts is not None:
        try:
            posted_at = datetime.fromtimestamp(
                int(created_ts), tz=timezone.utc
            ).isoformat()
        except (ValueError, OSError, OverflowError) as exc:
            logger.warning(
                "arbeitnow_mapper: no se pudo convertir created_at=%r a ISO 8601: %s",
                created_ts,
                exc,
            )

    return Job(
        id=stable_job_id(company, title, location or ""),
        title=title,
        company=company,
        location=location or None,
        remote=remote_val,
        description=clean_desc,
        salary=None,  # Arbeitnow free API no incluye salary
        url=raw.get("url"),
        source=source,
        posted_at=posted_at,
        raw=raw,
    )


# ──────────────────────────────────────────────────────────────────────────────
# AJUSTABLE: generic_mapper
# Fallback para fuentes sin mapper específico. Prueba los nombres de campo más
# comunes de distintas convenciones de APIs de empleo.
# AJUSTABLE: añadir nombres de campo de nuevas fuentes según se incorporen.
# ──────────────────────────────────────────────────────────────────────────────
def generic_mapper(raw: dict, source: str) -> Job:
    """Mapper genérico de fallback: best-effort sobre nombres de campo comunes.

    Prueba varias convenciones de nombres de campo típicas de APIs de empleo.
    No asume el formato de ninguna API en concreto.

    Convenciones soportadas:
      - company: company_name / company / employer
      - title:   title / job_title / position
      - location: location / city / place
      - description: description / body / summary
      - url: url / apply_url / link
      - remote: remote / is_remote (bool) / work_type (str)

    AJUSTABLE: añadir más variantes de nombre de campo según se identifiquen
    nuevas fuentes.

    Args:
        raw:    Payload dict de la fuente desconocida o genérica.
        source: Identificador de la fuente.

    Returns:
        Job normalizado con id estable. Campos vacíos si no hay coincidencia.
    """
    company = (
        raw.get("company_name")
        or raw.get("company")
        or raw.get("employer")
        or ""
    )
    title = (
        raw.get("title")
        or raw.get("job_title")
        or raw.get("position")
        or ""
    )
    location = (
        raw.get("location")
        or raw.get("city")
        or raw.get("place")
        or ""
    )
    description = (
        raw.get("description")
        or raw.get("body")
        or raw.get("summary")
        or ""
    )
    url = raw.get("url") or raw.get("apply_url") or raw.get("link")

    # Inferencia de remote desde bool o string
    remote_raw = (
        raw.get("remote")
        if "remote" in raw
        else raw.get("is_remote")
        if "is_remote" in raw
        else raw.get("work_type", "")
    )
    if isinstance(remote_raw, bool):
        remote_val = RemoteJob.remote if remote_raw else RemoteJob.unknown
    elif isinstance(remote_raw, str):
        rl = remote_raw.lower()
        if "remote" in rl:
            remote_val = RemoteJob.remote
        elif "hybrid" in rl:
            remote_val = RemoteJob.hybrid
        elif "onsite" in rl or "on-site" in rl or "presencial" in rl:
            remote_val = RemoteJob.onsite
        else:
            remote_val = RemoteJob.unknown
    else:
        remote_val = RemoteJob.unknown

    # Convertir posted_at / created_at a ISO 8601 si es timestamp numérico (WR-03).
    # Espeja la lógica de arbeitnow_mapper: Job.posted_at es Optional[str].
    _ts_raw = raw.get("posted_at") or raw.get("created_at")
    posted_at: str | None = None
    if isinstance(_ts_raw, str):
        posted_at = _ts_raw
    elif isinstance(_ts_raw, (int, float)):
        try:
            posted_at = datetime.fromtimestamp(int(_ts_raw), tz=timezone.utc).isoformat()
        except (ValueError, OSError, OverflowError):
            pass  # timestamp inválido → posted_at queda None

    return Job(
        id=stable_job_id(company, title, location or ""),
        title=title,
        company=company,
        location=location or None,
        remote=remote_val,
        description=description,
        salary=None,
        url=url,
        source=source,
        posted_at=posted_at,
        raw=raw,
    )


# ──────────────────────────────────────────────────────────────────────────────
# MAPPER_REGISTRY: registry de mappers por source
# Añadir nuevas fuentes aquí cuando se incorporen.
# ──────────────────────────────────────────────────────────────────────────────
MAPPER_REGISTRY: dict[str, MapperFn] = {
    "arbeitnow": arbeitnow_mapper,
    # AJUSTABLE: descomentar y ajustar contra respuesta real cuando se incorpore la fuente
    # "jsearch": jsearch_mapper,       # stub — JSearch (RapidAPI) job board
    # "flybyapis": flybyapis_mapper,   # stub — FlyByAPIs job board
    "generic": generic_mapper,
}
