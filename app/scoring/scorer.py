"""
Orquestador de scoring de ofertas.

Implementa la interfaz pública `score_job(job, cv_profile, user_profile, client) -> JobScore` que:
  1. Evalúa ubicación de forma determinista (location.py).
  2. Llama al LLM para evaluar skills/seniority/puesto/deal-breaker textual (llm.py).
  3. Calcula encaje_puesto desde decay lineal (ranking.py).
  4. Calcula score_total ponderado con pesos de UserProfile.pesos (determinista).
  5. Asigna recommendation por bandas deterministas.
  6. Aplica deal-breaker override (filtro duro — ÚLTIMO PASO, score_total se preserva honesto).

Este módulo es el único punto de entrada de scoring para consumidores externos
(n8n, endpoints FastAPI de Fase 4). Fase 5 envolverá assess_job() con Langfuse.

CRÍTICO: NO importar app.dedup (Pitfall 7 de RESEARCH.md — arrastraría BGE-M3/torch a tests).
"""
from __future__ import annotations

import logging

import instructor

from app.models.schemas import (
    CVProfile,
    Desglose,
    Job,
    JobScore,
    Recommendation,
    UserProfile,
)
from app.scoring.location import evaluar_ubicacion
from app.scoring.llm import assess_job, build_instructor_client
from app.scoring.ranking import encaje_puesto_desde_rango

logger = logging.getLogger(__name__)


def score_job(
    job: Job,
    cv_profile: CVProfile,
    user_profile: UserProfile,
    client: instructor.Instructor | None = None,
) -> JobScore:
    """Puntúa una oferta contra el perfil del usuario en 7 pasos.

    Paso 1: Cliente lazy — construye el cliente instructor si no se inyecta.
    Paso 2: Evaluación determinista de ubicación → encaje_ubicacion + deal_breaker_loc.
    Paso 3: Evaluación LLM → LLMJobAssessment (skills, seniority, puesto, deal-breaker texto).
    Paso 4: Decay del ranking → encaje_puesto (determinista sobre rango del LLM).
    Paso 5: score_total ponderado (determinista, fórmula exacta con pesos de profile).
    Paso 6: Recommendation por bandas (determinista sobre score_total).
    Paso 7: Deal-breaker override — ÚLTIMO, para que score_total sea honesto.

    Args:
        job:          Oferta normalizada (Job de Fase 2, ya deduplicada).
        cv_profile:   CV estructurado del candidato (CVProfile de Fase 1).
        user_profile: Perfil del usuario (UserProfile del config loader — incluye pesos).
        client:       Cliente instructor inyectado. Si None, se construye uno real.
                      Inyectable para tests (cero red).

    Returns:
        JobScore completo con score_total, recommendation, desglose y evidencia del LLM.
    """
    # Paso 1: cliente lazy si no se inyecta
    if client is None:
        client = build_instructor_client()

    # Paso 2: ubicación determinista
    encaje_ubicacion, deal_breaker_loc = evaluar_ubicacion(job, user_profile)

    # Paso 3: evaluación LLM (skills, seniority, puesto, deal-breaker textual)
    assessment = assess_job(job, cv_profile, user_profile, client)

    # Paso 4: decay del ranking (determinista sobre el rango que devolvió el LLM)
    encaje_puesto = encaje_puesto_desde_rango(assessment.rango_puesto)

    # Paso 5: score_total ponderado (determinista)
    # Fórmula: round(clamp(encaje_puesto*p.puesto + skills*p.skills + ubicacion*p.ubicacion + seniority*p.seniority))
    pesos = user_profile.pesos
    raw = (
        encaje_puesto * pesos.puesto
        + assessment.encaje_skills * pesos.skills
        + encaje_ubicacion * pesos.ubicacion
        + assessment.encaje_seniority * pesos.seniority
    )
    score_total = max(0, min(100, round(raw)))

    # Paso 6: recommendation por bandas (determinista)
    recommendation = _banda(score_total)

    # Paso 7 (ÚLTIMO): deal-breaker override — score_total conserva su valor honesto.
    # Un deal-breaker de ubicación OR un deal-breaker textual del LLM → skip.
    # Razón: score_total refleja la calidad real ("esta oferta habría sido un 85
    # si no fuera por la ubicación") — permite análisis futuros y es más honesto.
    deal_breaker_hit = bool(deal_breaker_loc or assessment.deal_breaker_hit_texto)
    # CR-02: combinar ambas razones cuando los dos deal-breakers disparan simultáneamente.
    # Antes se usaba `deal_breaker_loc or assessment.deal_breaker_cual_texto`, lo que
    # silenciosamente descartaba la razón del LLM cuando deal_breaker_loc era truthy.
    _db_parts = [p for p in (deal_breaker_loc, assessment.deal_breaker_cual_texto) if p]
    deal_breaker_cual: str | None = "; ".join(_db_parts) if _db_parts else None
    if deal_breaker_hit:
        recommendation = Recommendation.skip

    logger.info(
        "score_job: job=%s score=%d recommendation=%s deal_breaker=%s",
        job.id,
        score_total,
        recommendation.value,
        deal_breaker_cual,
    )

    return JobScore(
        score_total=score_total,
        recommendation=recommendation,
        desglose=Desglose(
            encaje_puesto=encaje_puesto,
            encaje_skills=assessment.encaje_skills,
            encaje_ubicacion=encaje_ubicacion,
            encaje_seniority=assessment.encaje_seniority,
        ),
        puesto_detectado=assessment.puesto_detectado,
        rango_puesto=assessment.rango_puesto,
        reasons_for=assessment.reasons_for,
        reasons_against=assessment.reasons_against,
        matched_skills=assessment.matched_skills,
        missing_requirements=assessment.missing_requirements,
        deal_breaker_hit=deal_breaker_hit,
        deal_breaker_cual=deal_breaker_cual,
    )


def _banda(score: int) -> Recommendation:
    """Asigna recommendation por bandas deterministas de score_total.

    Defaults (calibrables):
      >= 80 → strong_fit
      >= 60 → good_fit
      >= 40 → maybe
       < 40 → skip

    NOTA: estas bandas son el paso 6. El override de deal-breaker (paso 7)
    puede cambiar recommendation a skip DESPUÉS de esta función.
    """
    if score >= 80:
        return Recommendation.strong_fit
    if score >= 60:
        return Recommendation.good_fit
    if score >= 40:
        return Recommendation.maybe
    return Recommendation.skip
