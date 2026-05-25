"""
Módulo LLM para enriquecimiento en prosa de evaluaciones de ofertas — v2.0.

Expone:
- LLMEnrichment: modelo Pydantic con razones/listas (SIN scores numéricos).
- enrich_job(job, cv_profile, user_profile, client): llama al LLM para obtener SOLO
  el enriquecimiento en prosa (reasons_for/against, matched_skills, missing_requirements).
- build_instructor_client(): fábrica del cliente instructor (seam de inyección para tests).

CAMBIO v2.0 (refactor Phase 7):
  - assess_job() ELIMINADO. Los 4 sub-scores numéricos los calcula scorer.py de forma
    determinista (location.py, puesto_match.py, skills_match.py, seniority.py).
  - enrich_job() devuelve SOLO prosa + listas — NUNCA los cuatro números.
  - response_model: LLMEnrichment (local, NO en schemas.py).
  - LLMJobAssessment sigue en schemas.py (para compatibilidad durante transición — 07-06).

Mitigaciones de seguridad (T-03-08, T-03-09, T-07-10):
- El texto de la oferta va SOLO en el mensaje de usuario en sección XML <oferta>;
  el system prompt es una cadena fija sin interpolación de contenido externo
  (anti prompt-injection — la oferta es DATO, no instrucción).
- _escape_for_prompt escapa <, >, & del contenido de la oferta antes de inyectarlo
  en la sección <oferta> (CR-03).
- La clave de API la lee el SDK de OpenAI del entorno (OPENAI_API_KEY); nunca se
  referencia aquí directamente.
- El modelo se configura via OPENAI_MODEL_SCORING con default gpt-4o.
- max_tokens=1024 (reducido desde 2048 de assess_job — prosa solo necesita menos;
  T-07-12 DoS mitigation).
"""
from __future__ import annotations

import html
import os

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field

from app.models.schemas import CVProfile, Job, PuestoRanking, UserProfile
from app.obs.tracing import trace_llm


# ---------------------------------------------------------------------------
# LLMEnrichment — modelo local (NO en schemas.py)
# Devuelve SOLO prosa + listas. Los scores numéricos son responsabilidad de scorer.py.
# ---------------------------------------------------------------------------

class LLMEnrichment(BaseModel):
    """Prose-only enrichment from the LLM. Numbers come from deterministic rules.

    This model is intentionally LOCAL to llm.py (not in schemas.py) because
    it represents an implementation detail of the LLM enrichment step, not
    part of the public API of the scoring system.

    The four numeric sub-scores (encaje_puesto, encaje_skills, encaje_ubicacion,
    encaje_seniority) are computed deterministically by scorer.py before any
    LLM call. The LLM's sole responsibility here is to provide honest prose
    context for the already-computed numeric verdict.
    """

    razonamiento: str = Field(
        description=(
            "Razonamiento honesto del LLM sobre el encaje. "
            "Sé específico y directo. Máx 2-3 frases."
        )
    )
    reasons_for: list[str] = Field(
        default_factory=list,
        description=(
            "Razones concretas de encaje entre la oferta y el CVProfile. "
            "Máx 3-4 items. HONESTO — no infles si el encaje es débil."
        ),
    )
    reasons_against: list[str] = Field(
        default_factory=list,
        description=(
            "Razones concretas de NO encaje entre la oferta y el CVProfile. "
            "HONESTO, sin inflar. Máx 3-4 items. El valor está en filtrar bien."
        ),
    )
    matched_skills: list[str] = Field(
        default_factory=list,
        description="Skills del CVProfile que la oferta pide explícitamente.",
    )
    missing_requirements: list[str] = Field(
        default_factory=list,
        description="Requisitos de la oferta que el candidato podría no cumplir.",
    )


# ---------------------------------------------------------------------------
# Función pública: enrich_job
# ---------------------------------------------------------------------------

def enrich_job(
    job: Job,
    cv_profile: CVProfile,
    user_profile: UserProfile,
    client: instructor.Instructor,
) -> LLMEnrichment:
    """Llama al LLM para obtener SOLO el enriquecimiento en prosa.

    Los 4 sub-scores ya han sido calculados de forma determinista en scorer.py.
    El LLM solo enriquece con: reasons_for/against, matched_skills, missing_requirements.

    La oferta va en sección XML <oferta> (anti prompt-injection, CR-03).
    El system prompt es FIJO sin interpolación externa (T-03-08).

    Args:
        job:          Oferta normalizada a evaluar.
        cv_profile:   CV estructurado del candidato.
        user_profile: Perfil del usuario (ranking, preferencias, deal-breakers).
        client:       Cliente instructor inyectado (real o mock).

    Returns:
        LLMEnrichment con prose-only enrichment (razonamiento + reasons + skills).
    """
    model = os.getenv("OPENAI_MODEL_SCORING", "gpt-4o")

    with trace_llm("enrich_job", job_id=job.id, model=model):
        return client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un evaluador HONESTO de ofertas de empleo. "
                        "Los scores numéricos ya han sido calculados. Tu tarea es SOLO "
                        "proporcionar razones concretas de encaje y desencaje, las skills "
                        "que coinciden y los requisitos que faltan. "
                        "NO infles reasons_for. Sé específico en reasons_against y "
                        "missing_requirements — el valor está en filtrar bien."
                    ),
                },
                {
                    "role": "user",
                    "content": _build_prompt(job, cv_profile, user_profile),
                },
            ],
            response_model=LLMEnrichment,
            max_retries=2,
        )


# ---------------------------------------------------------------------------
# build_instructor_client — seam de inyección para tests
# ---------------------------------------------------------------------------

def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre OpenAI. Inyectable para tests."""
    return instructor.from_openai(OpenAI())


# ---------------------------------------------------------------------------
# Helpers privados de formato — texto legible, no model_dump_json crudo
# (RESEARCH Open Q 2: texto estructurado > JSON para juicio del LLM)
# ---------------------------------------------------------------------------

def _escape_for_prompt(text: str) -> str:
    """Escapa caracteres XML significativos en campos de la oferta para evitar cierre
    prematuro de los delimitadores XML del prompt (CR-03 anti prompt-injection).

    Escapa < > & para que un campo de oferta que contenga '</oferta>' no pueda
    romper la separación estructural del prompt. El LLM recibe &lt; &gt; &amp;
    en los campos de oferta (dato), no en las etiquetas de estructura (instrucción).
    """
    return html.escape(text, quote=False)


def _format_cv(cv: CVProfile) -> str:
    """Renderiza CVProfile como texto estructurado legible para el LLM.

    WR-03: All string fields from the CV are XML-escaped via _escape_for_prompt
    to prevent a corrupted/malicious CV entry (e.g. a company name containing
    '</cv>') from closing the <cv>…</cv> XML tag early and injecting content
    into the surrounding prompt structure.
    """
    lines: list[str] = []

    if cv.anios_experiencia_total is not None:
        lines.append(f"Años de experiencia total: {cv.anios_experiencia_total}")

    if cv.experiencia:
        lines.append("\nExperiencia:")
        for exp in cv.experiencia:
            linea = f"  - {_escape_for_prompt(exp.empresa)} | {_escape_for_prompt(exp.rol)}"
            if exp.duracion:
                linea += f" | {_escape_for_prompt(exp.duracion)}"
            if exp.tecnologias:
                linea += f" | Tecnologías: {', '.join(_escape_for_prompt(t) for t in exp.tecnologias)}"
            lines.append(linea)
            if exp.logros:
                for logro in exp.logros:
                    lines.append(f"    * {_escape_for_prompt(logro)}")

    if cv.skills_tecnicas:
        lines.append(f"\nSkills técnicas: {', '.join(_escape_for_prompt(s) for s in cv.skills_tecnicas)}")

    if cv.dominios:
        lines.append(f"Dominios: {', '.join(_escape_for_prompt(d) for d in cv.dominios)}")

    if cv.formacion:
        lines.append("\nFormación:")
        for form in cv.formacion:
            linea = f"  - {_escape_for_prompt(form.titulo)}"
            if form.institucion:
                linea += f" ({_escape_for_prompt(form.institucion)})"
            if form.anio:
                linea += f", {form.anio}"
            lines.append(linea)

    return "\n".join(lines)


def _format_ranking(ranking: list[PuestoRanking]) -> str:
    """Renderiza el ranking de puestos numerado (1-based) con sinónimos.

    El orden 1-based es crítico (Pitfall 1 de RESEARCH): el LLM debe usar
    el mismo rango para rango_puesto (1 = máxima prioridad).

    WR-03: titulo and sinonimos values are XML-escaped to prevent a manipulated
    profile.yaml entry from injecting content into the prompt structure.
    """
    lines: list[str] = []
    for i, puesto in enumerate(ranking, start=1):
        linea = f"{i}. {_escape_for_prompt(puesto.titulo)}"
        if puesto.sinonimos:
            linea += f" (sinónimos: {', '.join(_escape_for_prompt(s) for s in puesto.sinonimos)})"
        lines.append(linea)
    return "\n".join(lines)


def _format_job(job: Job) -> str:
    """Renderiza Job como texto estructurado legible para el LLM.

    Los campos de la oferta (title, company, location, description) son contenido
    externo no confiable y se escapan con _escape_for_prompt para evitar que un
    valor como '</oferta>' cierre prematuramente el delimitador XML del prompt
    (CR-03 anti prompt-injection).
    """
    lines: list[str] = [
        f"Título: {_escape_for_prompt(job.title)}",
        f"Empresa: {_escape_for_prompt(job.company)}",
        f"Ubicación: {_escape_for_prompt(job.location or 'No especificada')}",
        f"Modalidad: {job.remote.value}",
    ]
    if job.description:
        lines.append(f"Descripción:\n{_escape_for_prompt(job.description)}")
    return "\n".join(lines)


def _build_prompt(job: Job, cv_profile: CVProfile, user_profile: UserProfile) -> str:
    """Construye el mensaje de usuario con XML tags para separar contexto.

    La oferta va en sección <oferta> delimitada (anti prompt-injection:
    la descripción de la oferta no puede sobrescribir el system prompt).
    """
    ranking_text = _format_ranking(user_profile.ranking_puestos)
    cv_text = _format_cv(cv_profile)
    job_text = _format_job(job)
    deal_breakers_text = "\n".join(f"- {db}" for db in user_profile.deal_breakers)

    return (
        "<candidato>\n"
        f"<cv>{cv_text}</cv>\n"
        f"<ranking_puestos>{ranking_text}</ranking_puestos>\n"
        "<preferencias_ubicacion>"
        f"modalidad_ideal={user_profile.preferencia_remoto.modalidad_ideal.value}, "
        f"acepta_onsite_en={user_profile.preferencia_remoto.acepta_onsite_solo_en}"
        "</preferencias_ubicacion>\n"
        f"<deal_breakers>\n{deal_breakers_text}\n</deal_breakers>\n"
        "</candidato>\n"
        f"<oferta>\n{job_text}\n</oferta>\n"
        "Proporciona el enriquecimiento en prosa para esta oferta."
    )
