"""
Tests exhaustivos (QA-04) para app/scoring/scorer.py.

Verifica la heurística completa de scoring con el LLM SIEMPRE mockeado (cero red):
  SCORE-01: score_job devuelve JobScore completo con todos los campos poblados.
  SCORE-02: fuera de ranking (rango_puesto=None) → encaje_puesto = suelo (no skip solo).
  SCORE-04: seniority bajo + missing_requirements reflejados en JobScore SIN forzar skip.
  SCORE-05: deal-breaker (ubicación O texto) → recommendation=skip, deal_breaker_hit=True,
            PERO score_total se preserva honesto.
  SCORE-06: score_total ponderado exacto = round(encaje_puesto*0.35 + skills*0.30 +
            ubicacion*0.20 + seniority*0.15).
  SCORE-07: reasons_against y missing_requirements del LLM propagados sin modificar.
  QA-04:   bandas correctas (strong_fit/good_fit/maybe/skip) por score_total.

Todos los tests inyectan el client directamente (make_scoring_client del conftest);
NO se parchan funciones internas.
"""
from __future__ import annotations

from app.models.schemas import (
    Job,
    JobScore,
    LLMJobAssessment,
    Recommendation,
    RemoteJob,
)
from app.scoring.scorer import score_job
from tests.conftest import make_scoring_client


# ---------------------------------------------------------------------------
# Helper: LLMJobAssessment base reutilizable en tests
# ---------------------------------------------------------------------------

def _base_assessment(**overrides) -> LLMJobAssessment:
    """Crea un LLMJobAssessment base modificable para cada test."""
    defaults = dict(
        razonamiento="Razonamiento de prueba.",
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        encaje_skills=85,
        encaje_seniority=70,
        matched_skills=["Python", "LLMs"],
        missing_requirements=[],
        reasons_for=["Match en skills principales"],
        reasons_against=["Requiere Kubernetes (no en CV)"],
        deal_breaker_hit_texto=False,
        deal_breaker_cual_texto=None,
    )
    defaults.update(overrides)
    return LLMJobAssessment(**defaults)


# ---------------------------------------------------------------------------
# SCORE-01: score_job devuelve JobScore completo
# ---------------------------------------------------------------------------

def test_score_job_devuelve_jobscore_completo(
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-01: score_job devuelve un JobScore completo con todos los campos poblados."""
    assessment = _base_assessment()
    client = make_scoring_client(assessment)

    score = score_job(sample_job_remote, sample_cv_profile, sample_user_profile, client=client)

    assert isinstance(score, JobScore), f"Se esperaba JobScore, se obtuvo {type(score)}"

    # Desglose con los 4 encajes poblados
    assert score.desglose.encaje_puesto >= 0
    assert score.desglose.encaje_skills >= 0
    assert score.desglose.encaje_ubicacion >= 0
    assert score.desglose.encaje_seniority >= 0

    # Datos del assessment propagados
    assert score.puesto_detectado == assessment.puesto_detectado
    assert score.rango_puesto == assessment.rango_puesto
    assert score.matched_skills == assessment.matched_skills
    assert score.reasons_for == assessment.reasons_for
    assert score.reasons_against == assessment.reasons_against


# ---------------------------------------------------------------------------
# SCORE-06: score_total ponderado exacto
# ---------------------------------------------------------------------------

def test_score_total_ponderado_exacto(
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-06: score_total ponderado determinista exacto.

    Cálculo esperado (pesos default: puesto=0.35, skills=0.30, ubicacion=0.20, seniority=0.15):
      - encaje_puesto = 100 (rango=1, decay: 100 - (1-1)*15 = 100)
      - encaje_skills = 80 (del assessment mock)
      - encaje_ubicacion = 100 (remote job + modalidad_ideal=remote)
      - encaje_seniority = 70 (del assessment mock)
      score_total = round(100*0.35 + 80*0.30 + 100*0.20 + 70*0.15)
                 = round(35.0 + 24.0 + 20.0 + 10.5)
                 = round(89.5) = 90
    """
    assessment = _base_assessment(
        rango_puesto=1,       # → encaje_puesto = 100
        encaje_skills=80,
        encaje_seniority=70,
        deal_breaker_hit_texto=False,
    )
    client = make_scoring_client(assessment)

    score = score_job(sample_job_remote, sample_cv_profile, sample_user_profile, client=client)

    # Verificar sub-encajes
    assert score.desglose.encaje_puesto == 100, (
        f"encaje_puesto con rango=1 debe ser 100, se obtuvo {score.desglose.encaje_puesto}"
    )
    assert score.desglose.encaje_ubicacion == 100, (
        f"encaje_ubicacion remote+remote debe ser 100, se obtuvo {score.desglose.encaje_ubicacion}"
    )
    assert score.desglose.encaje_skills == 80
    assert score.desglose.encaje_seniority == 70

    # round(100*0.35 + 80*0.30 + 100*0.20 + 70*0.15) = round(89.5) = 90
    assert score.score_total == 90, (
        f"score_total esperado 90, se obtuvo {score.score_total}. "
        "Cálculo: round(100*.35 + 80*.30 + 100*.20 + 70*.15) = round(89.5) = 90"
    )


# ---------------------------------------------------------------------------
# QA-04: bandas de recommendation
# ---------------------------------------------------------------------------

def test_recommendation_bandas(
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """QA-04: las bandas de recommendation son correctas según score_total.

    Bandas: >=80 strong_fit, >=60 good_fit, >=40 maybe, <40 skip
    """
    # --- strong_fit: score ≥ 80 ---
    # encaje_puesto=100 (rango=1), skills=90, ubicacion=100 (remote), seniority=80
    # = round(100*.35 + 90*.30 + 100*.20 + 80*.15) = round(35+27+20+12) = round(94) = 94
    assessment_strong = _base_assessment(
        rango_puesto=1, encaje_skills=90, encaje_seniority=80, deal_breaker_hit_texto=False
    )
    score_strong = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile,
        client=make_scoring_client(assessment_strong),
    )
    assert score_strong.recommendation == Recommendation.strong_fit, (
        f"Score {score_strong.score_total} debe ser strong_fit (>=80)"
    )
    assert score_strong.score_total >= 80

    # --- good_fit: score en [60, 79] ---
    # Usar rango=3 (encaje_puesto=70), skills=60, ubicacion=100 (remote), seniority=60
    # = round(70*.35 + 60*.30 + 100*.20 + 60*.15) = round(24.5+18+20+9) = round(71.5) = 72
    assessment_good = _base_assessment(
        rango_puesto=3, encaje_skills=60, encaje_seniority=60, deal_breaker_hit_texto=False
    )
    score_good = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile,
        client=make_scoring_client(assessment_good),
    )
    assert score_good.recommendation == Recommendation.good_fit, (
        f"Score {score_good.score_total} debe ser good_fit (60-79)"
    )
    assert 60 <= score_good.score_total < 80

    # --- maybe: score en [40, 59] ---
    # Usar rango=4 (encaje_puesto=55), skills=40, ubicacion=100 (remote), seniority=40
    # = round(55*.35 + 40*.30 + 100*.20 + 40*.15) = round(19.25+12+20+6) = round(57.25) = 57
    assessment_maybe = _base_assessment(
        rango_puesto=4, encaje_skills=40, encaje_seniority=40, deal_breaker_hit_texto=False
    )
    score_maybe = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile,
        client=make_scoring_client(assessment_maybe),
    )
    assert score_maybe.recommendation == Recommendation.maybe, (
        f"Score {score_maybe.score_total} debe ser maybe (40-59)"
    )
    assert 40 <= score_maybe.score_total < 60

    # --- skip (por banda baja, sin deal-breaker): score < 40 ---
    # Usar rango=None (encaje_puesto=20 suelo), skills=10, ubicacion=100 (remote), seniority=10
    # = round(20*.35 + 10*.30 + 100*.20 + 10*.15) = round(7+3+20+1.5) = round(31.5) = 32
    assessment_skip_banda = _base_assessment(
        rango_puesto=None, encaje_skills=10, encaje_seniority=10, deal_breaker_hit_texto=False,
        puesto_detectado="fuera de ranking",
    )
    score_skip_banda = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile,
        client=make_scoring_client(assessment_skip_banda),
    )
    assert score_skip_banda.recommendation == Recommendation.skip, (
        f"Score {score_skip_banda.score_total} debe ser skip (<40)"
    )
    assert score_skip_banda.score_total < 40


# ---------------------------------------------------------------------------
# SCORE-05: deal-breaker de ubicación fuerza skip (score_total se preserva)
# ---------------------------------------------------------------------------

def test_deal_breaker_ubicacion_fuerza_skip(
    sample_job_onsite_madrid,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-05: deal-breaker de ubicación → recommendation=skip, deal_breaker_hit=True.

    El score_total se preserva honesto (no se pone a 0).
    Madrid onsite + dispuesto_a_reubicarse=False → encaje_ubicacion=10 + deal_breaker_loc.
    Con skills=90 y seniority=80 (altos), el score_total sería alto si no fuera por el override.
    """
    assessment = _base_assessment(
        rango_puesto=1,
        encaje_skills=90,
        encaje_seniority=80,
        deal_breaker_hit_texto=False,
        deal_breaker_cual_texto=None,
    )
    client = make_scoring_client(assessment)

    score = score_job(
        sample_job_onsite_madrid, sample_cv_profile, sample_user_profile, client=client
    )

    # El deal-breaker de ubicación fuerza skip
    assert score.recommendation == Recommendation.skip, (
        f"Madrid onsite + no reubicarse debe forzar skip, se obtuvo {score.recommendation}"
    )
    assert score.deal_breaker_hit is True
    assert score.deal_breaker_cual is not None
    assert "Madrid" in score.deal_breaker_cual, (
        f"deal_breaker_cual debe mencionar Madrid, se obtuvo: {score.deal_breaker_cual}"
    )

    # score_total se preserva honesto (> 40 dada las altas skills)
    assert score.score_total > 40, (
        f"score_total debe preservarse honesto pese al skip, se obtuvo {score.score_total}"
    )


# ---------------------------------------------------------------------------
# SCORE-05: deal-breaker de texto del LLM fuerza skip
# ---------------------------------------------------------------------------

def test_deal_breaker_texto_fuerza_skip(
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-05: deal-breaker textual del LLM → recommendation=skip, deal_breaker_hit=True.

    El deal_breaker_cual debe coincidir con el texto del assessment.
    """
    assessment = _base_assessment(
        rango_puesto=1,
        encaje_skills=80,
        encaje_seniority=70,
        deal_breaker_hit_texto=True,
        deal_breaker_cual_texto="exige 5+ años de experiencia",
    )
    client = make_scoring_client(assessment)

    score = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile, client=client
    )

    assert score.recommendation == Recommendation.skip, (
        f"deal_breaker_hit_texto=True debe forzar skip, se obtuvo {score.recommendation}"
    )
    assert score.deal_breaker_hit is True
    assert score.deal_breaker_cual == "exige 5+ años de experiencia", (
        f"deal_breaker_cual debe ser el texto del LLM, se obtuvo: {score.deal_breaker_cual}"
    )


# ---------------------------------------------------------------------------
# SCORE-04: seniority bajo no descarta (se refleja en el JobScore)
# ---------------------------------------------------------------------------

def test_seniority_bajo_no_descarta(
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-04: encaje_seniority bajo + missing_requirements reflejados SIN forzar skip.

    Si score_total >= 40, recommendation no debe ser skip por seniority solo.
    """
    assessment = _base_assessment(
        rango_puesto=1,
        encaje_skills=80,
        encaje_seniority=30,
        missing_requirements=["5+ años de experiencia"],
        deal_breaker_hit_texto=False,
    )
    client = make_scoring_client(assessment)

    score = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile, client=client
    )

    # Seniority bajo NO debe descartar por sí solo
    assert score.recommendation != Recommendation.skip, (
        f"Seniority bajo sin deal-breaker no debe forzar skip, se obtuvo {score.recommendation}"
    )

    # El encaje_seniority bajo se refleja en el desglose
    assert score.desglose.encaje_seniority == 30, (
        f"desglose.encaje_seniority debe ser 30, se obtuvo {score.desglose.encaje_seniority}"
    )

    # Los missing_requirements del LLM se propagan sin modificar
    assert "5+ años de experiencia" in score.missing_requirements, (
        f"missing_requirements debe incluir '5+ años de experiencia', se obtuvo {score.missing_requirements}"
    )

    # score_total suficientemente alto (rango=1, skills=80, ubicacion=100, seniority=30)
    # = round(100*.35 + 80*.30 + 100*.20 + 30*.15) = round(35+24+20+4.5) = round(83.5) = 84
    assert score.score_total >= 40


# ---------------------------------------------------------------------------
# SCORE-07: honestidad propagada sin modificar
# ---------------------------------------------------------------------------

def test_honestidad_propagada(
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-07: reasons_against, missing_requirements y matched_skills del LLM
    aparecen IDÉNTICOS en el JobScore (sin modificar)."""
    assessment = _base_assessment(
        reasons_for=["Experiencia en Python", "Match con AI Engineer"],
        reasons_against=["No tiene Kubernetes", "Sin experiencia en cloud"],
        matched_skills=["Python", "LLMs", "FastAPI"],
        missing_requirements=["Kubernetes", "AWS"],
        deal_breaker_hit_texto=False,
    )
    client = make_scoring_client(assessment)

    score = score_job(
        sample_job_remote, sample_cv_profile, sample_user_profile, client=client
    )

    assert score.reasons_for == ["Experiencia en Python", "Match con AI Engineer"], (
        f"reasons_for propagadas incorrectamente: {score.reasons_for}"
    )
    assert score.reasons_against == ["No tiene Kubernetes", "Sin experiencia en cloud"], (
        f"reasons_against propagadas incorrectamente: {score.reasons_against}"
    )
    assert score.matched_skills == ["Python", "LLMs", "FastAPI"], (
        f"matched_skills propagadas incorrectamente: {score.matched_skills}"
    )
    assert score.missing_requirements == ["Kubernetes", "AWS"], (
        f"missing_requirements propagados incorrectamente: {score.missing_requirements}"
    )


# ---------------------------------------------------------------------------
# SCORE-02 integración: fuera de ranking → suelo sin descartar sola
# ---------------------------------------------------------------------------

def test_fuera_de_ranking_no_descarta(
    sample_job_fuera_ranking,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-02: rango_puesto=None (fuera de ranking) → encaje_puesto = suelo (20).

    Una oferta fuera del ranking no se descarta automáticamente solo por eso.
    """
    assessment = _base_assessment(
        rango_puesto=None,
        puesto_detectado="fuera de ranking",
        encaje_skills=70,
        encaje_seniority=70,
        deal_breaker_hit_texto=False,
    )
    client = make_scoring_client(assessment)

    score = score_job(
        sample_job_fuera_ranking, sample_cv_profile, sample_user_profile, client=client
    )

    # encaje_puesto debe ser el suelo (20), no 0
    assert score.desglose.encaje_puesto == 20, (
        f"fuera de ranking debe dar encaje_puesto=20 (suelo), se obtuvo {score.desglose.encaje_puesto}"
    )

    # No debe descartarse solo por estar fuera de ranking
    # score = round(20*.35 + 70*.30 + 100*.20 + 70*.15) = round(7+21+20+10.5) = round(58.5) = 59
    # → maybe, no skip
    assert score.recommendation != Recommendation.skip, (
        f"Fuera de ranking NO debe descartarse solo, se obtuvo {score.recommendation}"
    )


# ---------------------------------------------------------------------------
# CR-02 / IN-03: ambos deal-breakers (ubicación + texto LLM) reportados juntos
# ---------------------------------------------------------------------------

def test_ambos_deal_breakers_reportados(
    sample_job_onsite_madrid,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """CR-02 / IN-03: cuando disparan AMBOS deal-breakers (ubicación + texto LLM),
    deal_breaker_cual incluye las dos razones separadas por '; '.

    Antes del fix, el 'or' corto-circuitaba y la razón del LLM se silenciaba.
    """
    assessment = _base_assessment(
        rango_puesto=1,
        encaje_skills=85,
        encaje_seniority=70,
        deal_breaker_hit_texto=True,
        deal_breaker_cual_texto="exige 5+ años de experiencia",
    )
    client = make_scoring_client(assessment)

    score = score_job(
        sample_job_onsite_madrid, sample_cv_profile, sample_user_profile, client=client
    )

    # Ambos deal-breakers deben forzar skip
    assert score.recommendation == Recommendation.skip, (
        f"Con ambos deal-breakers activos debe ser skip, se obtuvo {score.recommendation}"
    )
    assert score.deal_breaker_hit is True

    # La razón de ubicación (Madrid) debe estar presente
    assert score.deal_breaker_cual is not None
    assert "Madrid" in score.deal_breaker_cual, (
        f"deal_breaker_cual debe mencionar Madrid (deal-breaker ubicación), "
        f"se obtuvo: {score.deal_breaker_cual}"
    )

    # La razón textual del LLM también debe estar presente
    assert "exige 5+ años" in score.deal_breaker_cual, (
        f"deal_breaker_cual debe incluir la razón del LLM ('exige 5+ años'), "
        f"se obtuvo: {score.deal_breaker_cual}"
    )

    # score_total se preserva honesto (no se pone a 0 por el override)
    assert score.score_total > 0, (
        f"score_total debe preservarse honesto, se obtuvo {score.score_total}"
    )
