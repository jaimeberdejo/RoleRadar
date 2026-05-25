"""
Orquestador de scoring de ofertas — v2.0 local-first.

Implementa `score_job(job, user_profile, cv_profile, embedder, *, client=None) -> JobScore`:

PASO 1: Ubicación determinista (location.py) → encaje_ubicacion + deal_breaker_loc
PASO 2: Puesto detectado vía BGE-M3 coseno (puesto_match.py) → puesto_detectado + rango_puesto
PASO 3: Encaje skills vía BGE-M3 coseno (skills_match.py) → encaje_skills
PASO 4: Seniority determinista (seniority.py) → encaje_seniority + seniority_nota
PASO 5: Deal-breaker textual determinista (deal_breaker.py) → db_hit + db_cual
PASO 6: score_total ponderado + recommendation por bandas (determinista)
PASO 7 (ÚLTIMO): Deal-breaker override → recommendation=skip si cualquier hit
PASO 8 (OPCIONAL): Si OPENAI_API_KEY presente → enrich_job() llena reasons/skills

CRÍTICO: NO importar app.dedup (Pitfall 7). El embedder se inyecta como dependencia.
OpenAI NO se importa a nivel de módulo — deferred import en la rama del key check.

NOTA: El orden de argumentos cambió respecto a v1.0:
  v1.0: score_job(job, cv_profile, user_profile, client=None)
  v2.0: score_job(job, user_profile, cv_profile, embedder, *, client=None)
Los callers deben actualizarse (tests en 07-06).
"""
from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from app.models.schemas import (
    CVProfile,
    Desglose,
    Job,
    JobScore,
    Recommendation,
    UserProfile,
)
from app.scoring.deal_breaker import detectar_deal_breaker
from app.scoring.location import evaluar_ubicacion
from app.scoring.puesto_match import match_puesto_por_coseno
from app.scoring.ranking import encaje_puesto_desde_rango
from app.scoring.seniority import evaluar_seniority
from app.scoring.skills_match import encaje_skills_por_coseno

if TYPE_CHECKING:
    from app.dedup.embedder import Embedder

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------

_CV_TEXT_MAX_CHARS: int = 500
"""Cap local (evita importar la constante de skills_match para no crear dependencia
circular si skills_match evoluciona). Mismo valor que CV_SKILLS_TEXT_MAX_TOKENS."""


def _build_cv_text(cv_profile: CVProfile) -> str:
    """Construye texto compacto del CV para embeddings de skills.

    Concatena skills_tecnicas + tecnologías de experiencia + dominios en un
    string separado por espacios, truncado a _CV_TEXT_MAX_CHARS caracteres.

    El truncado es conservador: el texto real de skills raramente supera
    200 tokens; el cap protege contra entradas patológicas (CVs muy largos).

    Returns:
        String no-vacío listo para pasar a encaje_skills_por_coseno.
        Fallback: "sin_skills" si el CVProfile no tiene ninguna skill
        ni tecnología — evita que la función downstream reciba un string vacío.
    """
    parts: list[str] = []

    if cv_profile.skills_tecnicas:
        parts.extend(cv_profile.skills_tecnicas)

    for exp in cv_profile.experiencia:
        if exp.tecnologias:
            parts.extend(exp.tecnologias)

    if cv_profile.dominios:
        parts.extend(cv_profile.dominios)

    text = " ".join(parts) if parts else "sin_skills"
    return text[:_CV_TEXT_MAX_CHARS]


def _fallback_reasons(
    puesto_detectado: str,
    encaje_puesto: int,
    encaje_skills: int,
    encaje_ubicacion: int,
    encaje_seniority: int,
    seniority_nota: str,
    cv_skills: list[str],
    job_description: str,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Genera razones/skills deterministas cuando no hay clave de OpenAI.

    Construye reasons_for, reasons_against, matched_skills y missing_requirements
    a partir de los sub-scores ya calculados. NUNCA devuelve listas vacías para
    reasons_for/reasons_against (garantía de la interfaz de JobScore).

    Args:
        puesto_detectado:  Puesto detectado por coseno (o "fuera de ranking").
        encaje_puesto:     Sub-score 0-100.
        encaje_skills:     Sub-score 0-100.
        encaje_ubicacion:  Sub-score 0-100.
        encaje_seniority:  Sub-score 0-100.
        seniority_nota:    Nota textual de evaluar_seniority (siempre no-vacía).
        cv_skills:         Lista de skills del CVProfile.
        job_description:   Descripción de la oferta (para matched_skills por intersección).

    Returns:
        (reasons_for, reasons_against, matched_skills, missing_requirements)
    """
    reasons_for: list[str] = []
    reasons_against: list[str] = []

    # Reasons for — positivos
    if encaje_puesto >= 70:
        reasons_for.append(
            f"Puesto coincide con el ranking (posición detectada: {puesto_detectado})"
        )
    if encaje_skills >= 70:
        reasons_for.append("Buen encaje de skills técnicas según el CV")
    if encaje_ubicacion >= 80:
        reasons_for.append("Ubicación/modalidad favorable")

    # Reasons against — negativos
    if encaje_puesto < 40:
        reasons_against.append("Puesto fuera del ranking o encaje bajo")
    if encaje_skills < 50:
        reasons_against.append("Encaje de skills técnicas bajo")
    if encaje_seniority < 50 and seniority_nota:
        reasons_against.append(seniority_nota)

    # Garantía: al menos un item en cada lista
    if not reasons_for:
        reasons_for.append("Evalúa manualmente esta oferta")
    if not reasons_against:
        reasons_against.append("Evalúa manualmente esta oferta")

    # matched_skills — intersección determinista CV skills ∩ job description
    job_desc_lower = job_description.lower()
    matched_skills: list[str] = [
        skill for skill in cv_skills
        if skill.lower() in job_desc_lower
    ]

    # missing_requirements — basado en seniority si es bajo
    missing_requirements: list[str] = []
    if encaje_seniority < 60 and seniority_nota:
        missing_requirements.append(seniority_nota)

    return reasons_for, reasons_against, matched_skills, missing_requirements


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------


def score_job(
    job: Job,
    user_profile: UserProfile,
    cv_profile: CVProfile,
    embedder,  # Embedder Protocol — REQUIRED (duck-typed, no runtime import de app.dedup)
    *,
    client=None,  # instructor.Instructor | None — para LLM enrichment (opcional)
) -> JobScore:
    """Puntúa una oferta contra el perfil del usuario en 8 pasos.

    PASO 1: Ubicación determinista (location.py) → encaje_ubicacion + deal_breaker_loc
    PASO 2: Puesto detectado por coseno (puesto_match.py) → puesto_detectado + rango_puesto
    PASO 3: Encaje skills por coseno (skills_match.py) → encaje_skills
    PASO 4: Seniority determinista (seniority.py) → encaje_seniority + seniority_nota
    PASO 5: Deal-breaker textual determinista (deal_breaker.py) → db_hit + db_cual
    PASO 6: score_total ponderado (determinista) + recommendation por bandas
    PASO 7: Deal-breaker override ÚLTIMO → recommendation=skip si hit (score_total honesto)
    PASO 8 (OPCIONAL): OPENAI_API_KEY presente → enrich_job() llena reasons/skills/prose

    Args:
        job:          Oferta normalizada (Job ya deduplicada).
        user_profile: Perfil del usuario (ranking, pesos, deal_breakers, ubicación).
        cv_profile:   CV estructurado del candidato (CVProfile).
        embedder:     Embedder inyectado — OBLIGATORIO. Usarlo con FakeEmbedder en tests.
                      Lanza ValueError claro si es None (no 0 silencioso — SC2).
        client:       instructor.Instructor inyectado para LLM enrichment.
                      Se usa SOLO si OPENAI_API_KEY está en el entorno.
                      Si None y hay clave, se construye uno real via build_instructor_client.

    Returns:
        JobScore completo con todos los campos poblados. Nunca reasons_for/against vacíos.

    Raises:
        ValueError: Si embedder es None (requerido para pasos 2 y 3).
    """
    # --------------------------------------------------------------------------
    # PASO 1: Ubicación determinista
    # --------------------------------------------------------------------------
    encaje_ubicacion, deal_breaker_loc = evaluar_ubicacion(job, user_profile)

    # --------------------------------------------------------------------------
    # PASO 2: Puesto detectado vía embedder coseno → rango + decay
    # --------------------------------------------------------------------------
    puesto_detectado, rango_puesto = match_puesto_por_coseno(
        job.title, user_profile.ranking_puestos, embedder
    )
    encaje_puesto = encaje_puesto_desde_rango(rango_puesto)

    # --------------------------------------------------------------------------
    # PASO 3: Encaje skills vía embedder coseno
    # --------------------------------------------------------------------------
    cv_text = _build_cv_text(cv_profile)
    if cv_text == "sin_skills":
        # WR-01: "sin_skills" sentinel → the CV has no skills/techs/domains.
        # Embedding it would yield a semantically unrelated vector (BGE-M3 has
        # no concept of "empty CV"), producing a wrongly low score that penalises
        # every job as if the candidate had no matching skills.  Return neutral 50
        # consistent with the seniority.py None→50 pattern.
        encaje_skills = 50
        logger.warning(
            "score_job: CVProfile sin skills/tecnologías/dominios → "
            "encaje_skills=50 (neutral). Re-parsea el CV para obtener un score real."
        )
    else:
        encaje_skills = encaje_skills_por_coseno(cv_text, job.description or "", embedder)

    # --------------------------------------------------------------------------
    # PASO 4: Seniority determinista
    # --------------------------------------------------------------------------
    seniority_result = evaluar_seniority(
        job.description or "", cv_profile.anios_experiencia_total
    )
    encaje_seniority = seniority_result.encaje_seniority

    # --------------------------------------------------------------------------
    # PASO 5: Deal-breaker textual determinista
    # --------------------------------------------------------------------------
    job_text = f"{job.title} {job.description or ''}"
    db_result = detectar_deal_breaker(job_text, user_profile.deal_breakers)

    # --------------------------------------------------------------------------
    # PASO 6: score_total ponderado + recommendation por bandas
    # --------------------------------------------------------------------------
    pesos = user_profile.pesos
    raw = (
        encaje_puesto * pesos.puesto
        + encaje_skills * pesos.skills
        + encaje_ubicacion * pesos.ubicacion
        + encaje_seniority * pesos.seniority
    )
    score_total = max(0, min(100, round(raw)))
    recommendation = _banda(score_total)

    # --------------------------------------------------------------------------
    # PASO 7: Deal-breaker override ÚLTIMO (score_total se preserva honesto)
    # CR-02: combinar deal_breaker_loc + db_result.cual cuando los dos disparan.
    # --------------------------------------------------------------------------
    deal_breaker_hit = bool(deal_breaker_loc or db_result.hit)
    _db_parts = [p for p in (deal_breaker_loc, db_result.cual) if p]
    deal_breaker_cual: str | None = "; ".join(_db_parts) if _db_parts else None
    if deal_breaker_hit:
        recommendation = Recommendation.skip

    # --------------------------------------------------------------------------
    # PASO 8 (OPCIONAL): LLM enrichment (prose + matched/missing)
    # Deferred import: solo cuando OPENAI_API_KEY está configurada.
    # --------------------------------------------------------------------------
    if os.getenv("OPENAI_API_KEY"):
        from app.scoring.llm import build_instructor_client, enrich_job  # noqa: PLC0415
        if client is None:
            client = build_instructor_client()
        enrichment = enrich_job(job, cv_profile, user_profile, client)
        reasons_for = enrichment.reasons_for
        reasons_against = enrichment.reasons_against
        matched_skills = enrichment.matched_skills
        missing_requirements = enrichment.missing_requirements
    else:
        reasons_for, reasons_against, matched_skills, missing_requirements = _fallback_reasons(
            puesto_detectado,
            encaje_puesto,
            encaje_skills,
            encaje_ubicacion,
            encaje_seniority,
            seniority_result.seniority_nota,
            cv_profile.skills_tecnicas,
            job.description or "",
        )

    logger.info(
        "score_job: job=%s score=%d recommendation=%s deal_breaker=%s openai=%s",
        job.id,
        score_total,
        recommendation.value,
        deal_breaker_cual,
        bool(os.getenv("OPENAI_API_KEY")),
    )

    return JobScore(
        score_total=score_total,
        recommendation=recommendation,
        desglose=Desglose(
            encaje_puesto=encaje_puesto,
            encaje_skills=encaje_skills,
            encaje_ubicacion=encaje_ubicacion,
            encaje_seniority=encaje_seniority,
        ),
        puesto_detectado=puesto_detectado,
        rango_puesto=rango_puesto,
        reasons_for=reasons_for,
        reasons_against=reasons_against,
        matched_skills=matched_skills,
        missing_requirements=missing_requirements,
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
