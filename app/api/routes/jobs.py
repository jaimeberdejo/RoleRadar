"""Router de ofertas de empleo.

Expone:
    POST /jobs/normalize — normaliza ofertas crudas por fuente → {jobs, errors}
    POST /jobs/score     — puntúa una lista de Jobs normalizados → [ScoredJob]
    POST /jobs/process   — orquestación normalize+dedup+score+persist → ProcessResponse
    GET  /jobs/history   — historial de ofertas guardadas, paginable
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import (
    get_cached_cv_profile,
    get_embedder,
    get_scoring_llm_client,
    get_storage,
    get_user_profile_dep,
)
from app.dedup import deduplicate, normalize_jobs
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


class SourceBlock(BaseModel):
    """Una fuente con sus ofertas crudas para POST /jobs/process."""

    source: str
    offers: list[dict]


class ProcessRequest(BaseModel):
    """Cuerpo de POST /jobs/process: una o varias fuentes con sus ofertas."""

    sources: list[SourceBlock]


class ScoredJobConVisto(BaseModel):
    """Wrapper de respuesta de /jobs/process: ScoredJob + ya_visto.

    ya_visto=True si la oferta ya estaba en el storage antes de este run.
    NO muta el schema core ScoredJob — ya_visto vive solo en este modelo de respuesta.
    """

    job: Job
    score: JobScore
    ya_visto: bool = False


class ProcessResponse(BaseModel):
    """Respuesta de POST /jobs/process."""

    results: list[ScoredJobConVisto]
    errors: list[dict] = Field(default_factory=list)


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


@router.post("/process", response_model=ProcessResponse)
def process_jobs(
    body: ProcessRequest,
    cv_profile: CVProfile = Depends(get_cached_cv_profile),
    user_profile: UserProfile = Depends(get_user_profile_dep),
    scoring_client=Depends(get_scoring_llm_client),
    embedder=Depends(get_embedder),
    storage=Depends(get_storage),
) -> ProcessResponse:
    """Orquesta normalize → dedup → score → persist → ordena.

    Es el endpoint principal de n8n. Recibe ofertas crudas de una o varias fuentes,
    las normaliza, deduplica semánticamente, puntúa cada una contra el perfil real
    del usuario, computa ya_visto ANTES de persistir, persiste y devuelve los
    resultados ordenados por score_total DESC.

    Batch-resiliente: una oferta mal formada va a ``errors`` y nunca tumba el batch.
    Requiere CVProfile cacheado (POST /cv/parse primero); si no hay → 404.

    Args:
        body:           Sources con sus ofertas crudas.
        cv_profile:     CVProfile cacheado (inyectado).
        user_profile:   UserProfile del profile.yaml (inyectado).
        scoring_client: Cliente instructor para scoring (sobreescrito en tests).
        embedder:       Embedder para deduplicación semántica (sobreescrito en tests).
        storage:        Storage backend (sobreescrito en tests).

    Returns:
        ProcessResponse con resultados ordenados por score_total DESC y errores.
    """
    all_jobs: list[Job] = []
    all_errors: list[dict] = []

    # 1. Normalizar todas las fuentes (batch-resiliente ya integrado en normalize_jobs)
    for source_block in body.sources:
        jobs, errors = normalize_jobs(source_block.offers, source_block.source)
        all_jobs.extend(jobs)
        all_errors.extend(errors)

    # 2. Deduplicar semánticamente
    unique_jobs = deduplicate(all_jobs, embedder=embedder, umbral=user_profile.dedup_umbral)

    # 3. Score batch-resiliente: ya_visto ANTES del upsert — orden crítico
    scored: list[ScoredJobConVisto] = []
    for job in unique_jobs:
        ya_visto = storage.was_seen(job.id)  # ANTES del upsert — si no, siempre True
        try:
            score = score_job(job, cv_profile, user_profile, client=scoring_client)
            scored.append(ScoredJobConVisto(job=job, score=score, ya_visto=ya_visto))
        except Exception as exc:  # noqa: BLE001
            all_errors.append({"job_id": job.id, "error": str(exc)})
            logger.warning("process_jobs: error puntuando job=%s: %s", job.id, exc)

    # 4. Persistir (DESPUÉS de computar ya_visto — orden crítico)
    storage.upsert_scored_jobs([ScoredJob(job=s.job, score=s.score) for s in scored])

    # 5. Ordenar por score_total DESC
    scored.sort(key=lambda s: s.score.score_total, reverse=True)

    logger.info(
        "process_jobs: entradas=%d unicos=%d puntuados=%d errores=%d",
        sum(len(b.offers) for b in body.sources),
        len(unique_jobs),
        len(scored),
        len(all_errors),
    )
    return ProcessResponse(results=scored, errors=all_errors)
