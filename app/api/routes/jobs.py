"""Router de ofertas de empleo.

Expone:
    POST /jobs/normalize — normaliza ofertas crudas por fuente → {jobs, errors}
    POST /jobs/score     — puntúa una lista de Jobs normalizados → [ScoredJob]

Nota: POST /jobs/process y GET /jobs/history se añaden en Plan 04.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import (
    get_cached_cv_profile,
    get_scoring_llm_client,
    get_user_profile_dep,
)
from app.dedup import normalize_jobs
from app.models.schemas import CVProfile, Job, JobScore, ScoredJob, UserProfile
from app.scoring import score_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


# ─── Modelos request/response ────────────────────────────────────────────────


class NormalizeRequest(BaseModel):
    """Cuerpo de POST /jobs/normalize."""

    source: str
    offers: list[dict]


class NormalizeResponse(BaseModel):
    """Respuesta de POST /jobs/normalize."""

    jobs: list[Job]
    errors: list[dict] = Field(default_factory=list)


class ScoreRequest(BaseModel):
    """Cuerpo de POST /jobs/score."""

    jobs: list[Job]


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/normalize", response_model=NormalizeResponse)
def normalize_endpoint(body: NormalizeRequest) -> NormalizeResponse:
    """Normaliza una lista de ofertas crudas de una fuente.

    Batch-resiliente: una oferta mal formada va a ``errors`` y nunca tumba el
    batch completo (NORM-04 / API-07).

    Args:
        body: Fuente e lista de payloads crudos (dicts heterogéneos).

    Returns:
        NormalizeResponse con los Jobs normalizados y los errores encontrados.
    """
    jobs, errors = normalize_jobs(body.offers, body.source)
    logger.info(
        "normalize_endpoint: source=%s in=%d ok=%d errors=%d",
        body.source,
        len(body.offers),
        len(jobs),
        len(errors),
    )
    return NormalizeResponse(jobs=jobs, errors=errors)


@router.post("/score", response_model=list[ScoredJob])
def score_endpoint(
    body: ScoreRequest,
    cv_profile: CVProfile = Depends(get_cached_cv_profile),
    user_profile: UserProfile = Depends(get_user_profile_dep),
    scoring_client=Depends(get_scoring_llm_client),
) -> list[ScoredJob]:
    """Puntúa una lista de Jobs ya normalizados usando el CVProfile cacheado.

    Requiere que el CVProfile esté en caché (llamar a POST /cv/parse primero).
    Si no hay CVProfile cacheado, ``get_cached_cv_profile`` lanza HTTPException 404.

    Batch-resiliente: un job que falla al puntuar se omite (con log de warning)
    y el resto del batch continúa (API-07).

    Args:
        body:           Lista de Jobs normalizados a puntuar.
        cv_profile:     CVProfile cacheado (inyectado por Depends).
        user_profile:   UserProfile del fichero profile.yaml (inyectado por Depends).
        scoring_client: Cliente instructor inyectable (sobreescrito en tests).

    Returns:
        Lista de ScoredJob ordenada en el orden de entrada (sin ordenar aquí —
        la ordenación por score_total es responsabilidad de /jobs/process en Plan 04).
    """
    results: list[ScoredJob] = []
    for job in body.jobs:
        try:
            job_score: JobScore = score_job(
                job, cv_profile, user_profile, client=scoring_client
            )
            results.append(ScoredJob(job=job, score=job_score))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "score_endpoint: error puntuando job=%s: %s",
                getattr(job, "id", "?"),
                exc,
            )
    logger.info(
        "score_endpoint: in=%d puntuados=%d",
        len(body.jobs),
        len(results),
    )
    return results
