"""
Módulo LLM para evaluación de ofertas de empleo.

Expone:
- build_instructor_client(): fábrica del cliente instructor (seam de inyección para tests).
- assess_job(job, cv_profile, user_profile, client): llama al LLM con
  response_model=LLMJobAssessment y devuelve una evaluación tipada.

Mitigaciones de seguridad (T-03-08, T-03-09):
- El texto de la oferta va SOLO en el mensaje de usuario en sección XML <oferta>;
  el system prompt es una cadena fija sin interpolación de contenido externo
  (anti prompt-injection — la oferta es DATO, no instrucción).
- La clave de API la lee el SDK de OpenAI del entorno (OPENAI_API_KEY); nunca se referencia aquí.
- El modelo se configura via OPENAI_MODEL_SCORING con default gpt-4o.
"""
from __future__ import annotations

import html
import os

import instructor
from openai import OpenAI

from app.models.schemas import CVProfile, Job, LLMJobAssessment, PuestoRanking, UserProfile
from app.obs.tracing import trace_llm


def _escape_for_prompt(text: str) -> str:
    """Escapa caracteres XML significativos en campos de la oferta para evitar cierre
    prematuro de los delimitadores XML del prompt (CR-03 anti prompt-injection).

    Escapa < > & para que un campo de oferta que contenga '</oferta>' no pueda
    romper la separación estructural del prompt. El LLM recibe &lt; &gt; &amp;
    en los campos de oferta (dato), no en las etiquetas de estructura (instrucción).
    """
    return html.escape(text, quote=False)


def build_instructor_client() -> instructor.Instructor:
    """Construye el cliente instructor sobre OpenAI. Inyectable para tests."""
    return instructor.from_openai(OpenAI())


# ---------------------------------------------------------------------------
# Helpers privados de formato — texto legible, no model_dump_json crudo
# (RESEARCH Open Q 2: texto estructurado > JSON para juicio del LLM)
# ---------------------------------------------------------------------------

def _format_cv(cv: CVProfile) -> str:
    """Renderiza CVProfile como texto estructurado legible para el LLM."""
    lines: list[str] = []

    if cv.anios_experiencia_total is not None:
        lines.append(f"Años de experiencia total: {cv.anios_experiencia_total}")

    if cv.experiencia:
        lines.append("\nExperiencia:")
        for exp in cv.experiencia:
            linea = f"  - {exp.empresa} | {exp.rol}"
            if exp.duracion:
                linea += f" | {exp.duracion}"
            if exp.tecnologias:
                linea += f" | Tecnologías: {', '.join(exp.tecnologias)}"
            lines.append(linea)
            if exp.logros:
                for logro in exp.logros:
                    lines.append(f"    * {logro}")

    if cv.skills_tecnicas:
        lines.append(f"\nSkills técnicas: {', '.join(cv.skills_tecnicas)}")

    if cv.dominios:
        lines.append(f"Dominios: {', '.join(cv.dominios)}")

    if cv.formacion:
        lines.append("\nFormación:")
        for form in cv.formacion:
            linea = f"  - {form.titulo}"
            if form.institucion:
                linea += f" ({form.institucion})"
            if form.anio:
                linea += f", {form.anio}"
            lines.append(linea)

    return "\n".join(lines)


def _format_ranking(ranking: list[PuestoRanking]) -> str:
    """Renderiza el ranking de puestos numerado (1-based) con sinónimos.

    El orden 1-based es crítico (Pitfall 1 de RESEARCH): el LLM debe usar
    el mismo rango para rango_puesto (1 = máxima prioridad).
    """
    lines: list[str] = []
    for i, puesto in enumerate(ranking, start=1):
        linea = f"{i}. {puesto.titulo}"
        if puesto.sinonimos:
            linea += f" (sinónimos: {', '.join(puesto.sinonimos)})"
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
        "Evalúa el encaje de esta oferta con el candidato."
    )


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------

def assess_job(
    job: Job,
    cv_profile: CVProfile,
    user_profile: UserProfile,
    client: instructor.Instructor,
) -> LLMJobAssessment:
    """Llama al LLM para evaluar el encaje oferta↔candidato.

    Devuelve un LLMJobAssessment estructurado con:
    - puesto_detectado + rango_puesto: el LLM empareja la oferta con el ranking.
    - encaje_skills + encaje_seniority: evaluación 0-100 vs CVProfile real.
    - matched_skills + missing_requirements: evidencia textual del LLM.
    - reasons_for + reasons_against: honesto, sin inflar (SCORE-07).
    - deal_breaker_hit_texto + deal_breaker_cual_texto: deal-breakers textuales.

    NOTA: Esta función es el único punto de entrada LLM para scoring.
    Fase 5 la envolverá con Langfuse para observabilidad (OBS-02).

    Args:
        job:          Oferta normalizada a evaluar.
        cv_profile:   CV estructurado del candidato.
        user_profile: Perfil del usuario (ranking, preferencias, deal-breakers).
        client:       Cliente instructor inyectado (real o mock).

    Returns:
        LLMJobAssessment validado por Pydantic.
    """
    model = os.getenv("OPENAI_MODEL_SCORING", "gpt-4o")

    # system prompt FIJO — sin interpolación de contenido externo (T-03-08).
    # Va como primer mensaje (convención OpenAI), no como parámetro `system=` (Anthropic).
    with trace_llm("assess_job", job_id=job.id, model=model):
        return client.chat.completions.create(
            model=model,
            max_tokens=2048,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un evaluador HONESTO de ofertas de empleo. "
                        "Tu objetivo es dar una evaluación realista y calibrada de si la oferta encaja "
                        "con el candidato. NO infles los reasons_for ni ocultes los reasons_against. "
                        "Si hay requisitos que el candidato claramente no cumple, ponlos en missing_requirements. "
                        "El valor de este sistema está en filtrar bien, no en parecer optimista."
                    ),
                },
                {
                    "role": "user",
                    "content": _build_prompt(job, cv_profile, user_profile),
                },
            ],
            response_model=LLMJobAssessment,
            max_retries=2,
        )
