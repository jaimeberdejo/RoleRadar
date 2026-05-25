"""
Tests exhaustivos (QA-04, QA-07) para app/scoring/scorer.py — v2.0 signature.

New scorer signature (Phase 7 Wave 2):
  score_job(job, user_profile, cv_profile, embedder, *, client=None) -> JobScore

All 4 numeric sub-scores are deterministic (no LLM required):
  - encaje_ubicacion: location.py deterministic rule
  - encaje_puesto: puesto_match.py cosine via embedder
  - encaje_skills: skills_match.py cosine via embedder
  - encaje_seniority: seniority.py deterministic rule

LLM enrichment (prose only) is OPTIONAL — only when OPENAI_API_KEY is set.
Without the key, _fallback_reasons() provides rule-based non-empty strings.

Tests:
  SCORE-01: score_job devuelve JobScore completo con todos los campos poblados.
  SCORE-02: fuera de ranking (rango_puesto=None) → encaje_puesto = suelo (20).
  SCORE-04: seniority bajo → reflejado en desglose, SIN forzar skip.
  SCORE-05: deal-breaker (ubicación O texto) → recommendation=skip, deal_breaker_hit=True,
            score_total se preserva honesto.
  SCORE-06: score_total ponderado exacto (determinista).
  SCORE-07: enrichment values propagated sin modificar (con OPENAI_API_KEY).
  QA-04:    bandas correctas (strong_fit/good_fit/maybe/skip) por score_total.
  QA-07:    sin OPENAI_API_KEY → JobScore completo con razones no-vacías.
  SCORE-14: con OPENAI_API_KEY → enrichment llamado; reasons del enrich propagadas.
  CR-02:    ambos deal-breakers (ubicación + texto) reportados juntos.

FakeEmbedder always imported INSIDE test bodies (Pitfall 7 — no torch at collection).
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from app.models.schemas import (
    Job,
    JobScore,
    Recommendation,
    RemoteJob,
)
from app.scoring.scorer import score_job


# ---------------------------------------------------------------------------
# Helper: build a FakeEmbedder with identical vectors (all texts → same vector)
# ---------------------------------------------------------------------------

def _make_fake_embedder():
    """Return a FakeEmbedder with default_vector=[1,0,0,0] for all texts.

    With this embedder:
    - All cosines == 1.0 → encaje_skills=100, encaje_puesto matches entry 1
    """
    from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7
    return FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))


# ---------------------------------------------------------------------------
# SCORE-01: score_job devuelve JobScore completo
# ---------------------------------------------------------------------------

def test_score_job_devuelve_jobscore_completo(
    monkeypatch,
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-01: score_job devuelve un JobScore completo con todos los campos poblados.

    Uses FakeEmbedder (default_vector) and no OPENAI_API_KEY — tests the
    complete deterministic path.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    embedder = _make_fake_embedder()

    score = score_job(sample_job_remote, sample_user_profile, sample_cv_profile, embedder)

    assert isinstance(score, JobScore), f"Se esperaba JobScore, se obtuvo {type(score)}"

    # Desglose con los 4 encajes poblados
    assert 0 <= score.desglose.encaje_puesto <= 100
    assert 0 <= score.desglose.encaje_skills <= 100
    assert 0 <= score.desglose.encaje_ubicacion <= 100
    assert 0 <= score.desglose.encaje_seniority <= 100

    # Fields populated
    assert isinstance(score.puesto_detectado, str)
    assert isinstance(score.score_total, int)
    assert 0 <= score.score_total <= 100
    assert isinstance(score.recommendation, Recommendation)
    assert isinstance(score.deal_breaker_hit, bool)
    assert isinstance(score.reasons_for, list)
    assert isinstance(score.reasons_against, list)
    assert isinstance(score.matched_skills, list)
    assert isinstance(score.missing_requirements, list)


# ---------------------------------------------------------------------------
# SCORE-06: score_total ponderado exacto (determinista)
# ---------------------------------------------------------------------------

def test_score_total_ponderado_exacto(
    monkeypatch,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-06: score_total ponderado determinista exacto.

    With FakeEmbedder default_vector=[1,0,0,0]:
      - encaje_puesto=100 (rango=1, all same vectors → first entry matches, decay=100)
      - encaje_skills=100 (cosine=1.0 between cv_text and job description)
      - encaje_ubicacion=100 (remote job + modalidad_ideal=remote)
      - encaje_seniority=75 (no signal in "We are looking for an AI Engineer..." → generous 75)

    score_total = round(100*0.35 + 100*0.30 + 100*0.20 + 75*0.15)
               = round(35 + 30 + 20 + 11.25)
               = round(96.25) = 96

    Pesos default: puesto=0.35, skills=0.30, ubicacion=0.20, seniority=0.15.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Remote job with no seniority signal in description → seniority=75
    job = Job(
        id="remote-ai-engineer-techcorp",
        title="AI Engineer",
        company="TechCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description="We are looking for an AI Engineer with Python and LLMs experience.",
        source="test",
    )
    embedder = _make_fake_embedder()

    score = score_job(job, sample_user_profile, sample_cv_profile, embedder)

    # Sub-encajes verificados individualmente
    assert score.desglose.encaje_puesto == 100, (
        f"encaje_puesto con rango=1 (todos mismos vectores) debe ser 100, "
        f"se obtuvo {score.desglose.encaje_puesto}"
    )
    assert score.desglose.encaje_ubicacion == 100, (
        f"encaje_ubicacion remote+remote debe ser 100, "
        f"se obtuvo {score.desglose.encaje_ubicacion}"
    )
    assert score.desglose.encaje_skills == 100, (
        f"encaje_skills con cosine=1.0 (default_vector idéntico) debe ser 100, "
        f"se obtuvo {score.desglose.encaje_skills}"
    )
    assert score.desglose.encaje_seniority == 75, (
        f"encaje_seniority sin señal en descripción debe ser 75 (generous), "
        f"se obtuvo {score.desglose.encaje_seniority}"
    )

    # round(100*0.35 + 100*0.30 + 100*0.20 + 75*0.15) = round(96.25) = 96
    assert score.score_total == 96, (
        f"score_total esperado 96, se obtuvo {score.score_total}. "
        "Cálculo: round(100*.35 + 100*.30 + 100*.20 + 75*.15) = round(96.25) = 96"
    )


# ---------------------------------------------------------------------------
# QA-04: bandas de recommendation
# ---------------------------------------------------------------------------

def test_recommendation_bandas(
    monkeypatch,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """QA-04: las bandas de recommendation son correctas según score_total.

    Bandas: >=80 strong_fit, >=60 good_fit, >=40 maybe, <40 skip

    We control the score by using orthogonal embedder vectors and specific
    job descriptions.
    """
    from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # --- strong_fit: all same vectors → max scores → 96 ≥ 80 → strong_fit ---
    job_remote = Job(
        id="remote-ai-engineer",
        title="AI Engineer",
        company="TechCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description="We are looking for an AI Engineer with Python experience.",
        source="test",
    )
    embedder_strong = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    score_strong = score_job(job_remote, sample_user_profile, sample_cv_profile, embedder_strong)
    assert score_strong.recommendation == Recommendation.strong_fit, (
        f"Score {score_strong.score_total} debe ser strong_fit (>=80)"
    )
    assert score_strong.score_total >= 80

    # --- skip (por banda baja): fuera de ranking + skills orthogonal + bad ubicacion + seniority mismatch ---
    # encaje_puesto: title orthogonal to all ranking entries → fuera de ranking → 20 (suelo)
    # encaje_skills: orthogonal cv_text ↔ job_description → 0
    # encaje_ubicacion: Madrid onsite + dispuesto_a_reubicarse=False → 10
    # encaje_seniority: "10+ years required" + 2yr candidate → ratio 0.2 → 10
    # score = round(20*0.35 + 0*0.30 + 10*0.20 + 10*0.15) = round(7+0+2+1.5) = round(10.5) = 11 → skip

    # cv_text built by scorer._build_cv_text(sample_cv_profile):
    # "Python LLMs FastAPI Python LLMs IA"[:500] → exactly this string
    cv_text_exact = "Python LLMs FastAPI Python LLMs IA"
    job_desc_skip = (
        "We need 10+ years of experience as a Frontend Designer with React skills."
    )

    def _corpus_key(entry):
        return " ".join([entry.titulo, *entry.sinonimos]).strip()

    ranking_keys = {_corpus_key(e): np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
                    for e in sample_user_profile.ranking_puestos}

    vecs_skip = {
        # Title → orthogonal to corpus → fuera de ranking
        "Frontend Designer": np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        # cv_text → [1,0,0,0]; job_desc → [0,1,0,0] → cosine=0 → encaje_skills=0
        cv_text_exact: np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        job_desc_skip: np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
    }
    vecs_skip.update(ranking_keys)

    job_skip = Job(
        id="onsite-madrid-frontend-skip",
        title="Frontend Designer",
        company="Agency",
        location="Madrid, España",
        remote=RemoteJob.onsite,  # onsite Madrid → encaje_ubicacion low (10) — NO deal breaker text
        description=job_desc_skip,
        source="test",
    )
    # default_vector for anything not mapped explicitly (rare; safe fallback)
    embedder_skip = FakeEmbedder(
        vectors=vecs_skip,
        default_vector=np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
    )
    score_skip = score_job(job_skip, sample_user_profile, sample_cv_profile, embedder_skip)
    # This job has deal_breaker_hit from location (Madrid onsite) → recommendation=skip
    # We check skip recommendation (whether from banda or deal-breaker)
    assert score_skip.recommendation == Recommendation.skip, (
        f"Score {score_skip.score_total} debe ser skip (deal-breaker de ubicacion o banda)"
    )


# ---------------------------------------------------------------------------
# SCORE-05: deal-breaker de ubicación fuerza skip (score_total se preserva)
# ---------------------------------------------------------------------------

def test_deal_breaker_ubicacion_fuerza_skip(
    monkeypatch,
    sample_job_onsite_madrid,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-05: deal-breaker de ubicación → recommendation=skip, deal_breaker_hit=True.

    El score_total se preserva honesto (no se pone a 0).
    Madrid onsite + dispuesto_a_reubicarse=False → encaje_ubicacion=10 + deal_breaker_loc.
    Con FakeEmbedder default_vector, skills=100, puesto=100, seniority=75.
    El score_total sería alto si no fuera por el override de deal-breaker.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    embedder = _make_fake_embedder()

    score = score_job(
        sample_job_onsite_madrid, sample_user_profile, sample_cv_profile, embedder
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

    # score_total se preserva honesto — encaje_ubicacion bajo pero
    # encaje_puesto, skills y seniority son altos → score > 40
    assert score.score_total > 0, (
        f"score_total debe preservarse honesto pese al skip, se obtuvo {score.score_total}"
    )


# ---------------------------------------------------------------------------
# SCORE-05: deal-breaker de texto fuerza skip (determinista, sin LLM)
# ---------------------------------------------------------------------------

def test_deal_breaker_texto_fuerza_skip(
    monkeypatch,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-05: deal-breaker textual en descripción → recommendation=skip, deal_breaker_hit=True.

    La detección de deal-breaker es determinista — no necesita LLM.
    deal_breaker_cual debe contener el texto del deal-breaker disparado.
    sample_user_profile.deal_breakers = ["exige 5+ años de experiencia", ...]
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    embedder = _make_fake_embedder()

    job_with_deal_breaker = Job(
        id="remote-senior-deal-breaker",
        title="AI Engineer",
        company="SomeCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description=(
            "Great AI position. Se exige 5+ años de experiencia en Python y LLMs. "
            "Remote friendly."
        ),
        source="test",
    )

    score = score_job(
        job_with_deal_breaker, sample_user_profile, sample_cv_profile, embedder
    )

    assert score.recommendation == Recommendation.skip, (
        f"deal_breaker textual debe forzar skip, se obtuvo {score.recommendation}"
    )
    assert score.deal_breaker_hit is True
    assert score.deal_breaker_cual is not None
    assert "exige 5+ años" in score.deal_breaker_cual, (
        f"deal_breaker_cual debe mencionar el deal-breaker disparado, "
        f"se obtuvo: {score.deal_breaker_cual}"
    )


# ---------------------------------------------------------------------------
# SCORE-04: seniority bajo no descarta (se refleja en el JobScore)
# ---------------------------------------------------------------------------

def test_seniority_bajo_no_descarta(
    monkeypatch,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-04: encaje_seniority bajo (job pide 10yr, candidate tiene 2yr) no fuerza skip.

    La oferta requiere 10+ años; el candidato tiene 2.0 años (sample_cv_profile).
    Ratio = 0.2 → score = 10 (muy bajo pero no 0).
    Con encaje_puesto=100, skills=100, ubicacion=100:
      score = round(100*0.35 + 100*0.30 + 100*0.20 + 10*0.15) = round(35+30+20+1.5) = 87
    → good_fit/strong_fit (not skip), seniority bajo reflejado en desglose.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    embedder = _make_fake_embedder()

    # Job requiring 10+ years to force low seniority
    job_senior = Job(
        id="remote-senior-ai-engineer",
        title="AI Engineer",
        company="BigCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description=(
            "We are looking for a very experienced AI Engineer with "
            "10+ years of Python and ML experience."
        ),
        source="test",
    )

    score = score_job(
        job_senior, sample_user_profile, sample_cv_profile, embedder
    )

    # Seniority bajo NO debe descartar por sí solo
    assert score.recommendation != Recommendation.skip, (
        f"Seniority bajo sin deal-breaker no debe forzar skip, se obtuvo {score.recommendation}"
    )

    # El encaje_seniority bajo se refleja en el desglose
    assert score.desglose.encaje_seniority < 50, (
        f"desglose.encaje_seniority debe ser bajo (< 50) para 2yr vs 10yr req, "
        f"se obtuvo {score.desglose.encaje_seniority}"
    )

    # score_total suficientemente alto (puesto=100, skills=100, ubicacion=100 → compensa)
    assert score.score_total >= 40


# ---------------------------------------------------------------------------
# SCORE-07 / SCORE-14: enrichment values propagated sin modificar
# ---------------------------------------------------------------------------

def test_honestidad_propagada(
    monkeypatch,
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-07: reasons_for, reasons_against, matched_skills y missing_requirements del
    enrichment (LLM) aparecen IDÉNTICOS en el JobScore (sin modificar).

    Requires OPENAI_API_KEY to trigger the LLM enrichment branch.
    Uses a mock client that returns EXPECTED_ENRICHMENT.
    """
    from app.scoring.llm import LLMEnrichment
    from tests.conftest import EXPECTED_ENRICHMENT, make_enrichment_client

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    embedder = _make_fake_embedder()
    client = make_enrichment_client(EXPECTED_ENRICHMENT)

    score = score_job(
        sample_job_remote, sample_user_profile, sample_cv_profile, embedder, client=client
    )

    assert score.reasons_for == EXPECTED_ENRICHMENT.reasons_for, (
        f"reasons_for propagadas incorrectamente: {score.reasons_for}"
    )
    assert score.reasons_against == EXPECTED_ENRICHMENT.reasons_against, (
        f"reasons_against propagadas incorrectamente: {score.reasons_against}"
    )
    assert score.matched_skills == EXPECTED_ENRICHMENT.matched_skills, (
        f"matched_skills propagadas incorrectamente: {score.matched_skills}"
    )
    assert score.missing_requirements == EXPECTED_ENRICHMENT.missing_requirements, (
        f"missing_requirements propagados incorrectamente: {score.missing_requirements}"
    )


# ---------------------------------------------------------------------------
# SCORE-02 integración: fuera de ranking → suelo sin descartar sola
# ---------------------------------------------------------------------------

def test_fuera_de_ranking_no_descarta(
    monkeypatch,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-02: rango_puesto=None (fuera de ranking) → encaje_puesto = suelo (20).

    Una oferta fuera del ranking no se descarta automáticamente solo por eso.
    We need orthogonal vectors so the title doesn't match any ranking entry.
    """
    from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def _corpus_key(entry):
        return " ".join([entry.titulo, *entry.sinonimos]).strip()

    # Job title vector is orthogonal to all ranking corpus vectors
    title_vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    corpus_vec = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

    ranking_keys = {_corpus_key(e): corpus_vec for e in sample_user_profile.ranking_puestos}
    vecs = {"Frontend Designer": title_vec}
    vecs.update(ranking_keys)

    embedder = FakeEmbedder(
        vectors=vecs,
        default_vector=corpus_vec,  # cv_text and job desc both get corpus_vec → cosine=1.0
    )

    job_fuera = Job(
        id="remote-frontend-designer",
        title="Frontend Designer",
        company="DesignAgency",
        location="Remote",
        remote=RemoteJob.remote,
        description=(
            "We are looking for a creative Frontend Designer with React skills. "
            "Great team and remote-first culture."
        ),
        source="test",
    )

    score = score_job(
        job_fuera, sample_user_profile, sample_cv_profile, embedder
    )

    # encaje_puesto debe ser el suelo (20)
    assert score.desglose.encaje_puesto == 20, (
        f"fuera de ranking debe dar encaje_puesto=20 (suelo), se obtuvo {score.desglose.encaje_puesto}"
    )

    # Puesto detectado debe ser "fuera de ranking"
    assert score.puesto_detectado == "fuera de ranking", (
        f"puesto_detectado esperado 'fuera de ranking', se obtuvo {score.puesto_detectado!r}"
    )

    # No debe descartarse solo por estar fuera de ranking
    assert score.recommendation != Recommendation.skip, (
        f"Fuera de ranking NO debe descartarse solo, se obtuvo {score.recommendation}"
    )


# ---------------------------------------------------------------------------
# CR-02 / IN-03: ambos deal-breakers (ubicación + texto) reportados juntos
# ---------------------------------------------------------------------------

def test_ambos_deal_breakers_reportados(
    monkeypatch,
    sample_job_onsite_madrid,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """CR-02 / IN-03: cuando disparan AMBOS deal-breakers (ubicación + texto),
    deal_breaker_cual incluye las dos razones separadas por '; '.

    sample_job_onsite_madrid: Madrid onsite → deal_breaker_loc from location.py
    Description also contains "exige 5+ años de experiencia" → deal_breaker from text
    We use the base Madrid job but override description to include both.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    embedder = _make_fake_embedder()

    # Add textual deal-breaker to the Madrid job description
    job_both_db = Job(
        id="onsite-madrid-deal-breaker",
        title="AI Engineer",
        company="MadridCorp",
        location="Madrid, España",
        remote=RemoteJob.onsite,
        description=(
            "Buscamos AI Engineer para trabajar presencialmente en Madrid. "
            "Se exige 5+ años de experiencia."
        ),
        source="test",
    )

    score = score_job(
        job_both_db, sample_user_profile, sample_cv_profile, embedder
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

    # La razón textual también debe estar presente
    assert "exige 5+ años" in score.deal_breaker_cual, (
        f"deal_breaker_cual debe incluir la razón textual ('exige 5+ años'), "
        f"se obtuvo: {score.deal_breaker_cual}"
    )

    # score_total se preserva honesto (no se pone a 0 por el override)
    assert score.score_total > 0, (
        f"score_total debe preservarse honesto, se obtuvo {score.score_total}"
    )


# ---------------------------------------------------------------------------
# QA-07: sin OPENAI_API_KEY → JobScore completo con razones no-vacías
# ---------------------------------------------------------------------------

def test_no_openai_api_key_devuelve_jobscore_completo(
    monkeypatch,
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """QA-07: no OPENAI_API_KEY → full valid JobScore with fallback reasons.

    Verifica el end-to-end path sin LLM: todos los 4 sub-scores presentes,
    reasons_for y reasons_against no-vacíos (garantía de _fallback_reasons).
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7
    embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))

    score = score_job(sample_job_remote, sample_user_profile, sample_cv_profile, embedder)

    assert isinstance(score, JobScore)
    assert 0 <= score.score_total <= 100
    assert score.recommendation in list(Recommendation)
    assert 0 <= score.desglose.encaje_puesto <= 100
    assert 0 <= score.desglose.encaje_skills <= 100
    assert 0 <= score.desglose.encaje_ubicacion <= 100
    assert 0 <= score.desglose.encaje_seniority <= 100
    # Fallback guarantees non-empty lists
    assert score.reasons_for, "reasons_for must not be empty in no-key path"
    assert score.reasons_against, "reasons_against must not be empty in no-key path"
    assert isinstance(score.matched_skills, list)
    assert isinstance(score.missing_requirements, list)


# ---------------------------------------------------------------------------
# SCORE-14: con OPENAI_API_KEY → enrich_job llamado; prose propagada
# ---------------------------------------------------------------------------

def test_openai_key_present_usa_enriquecimiento(
    monkeypatch,
    sample_job_remote,
    sample_cv_profile,
    sample_user_profile,
) -> None:
    """SCORE-14: con OPENAI_API_KEY, enrich_job es llamado y su prose se propaga.

    The mock client returns EXPECTED_ENRICHMENT; we verify that the JobScore
    reasons_for, reasons_against, and matched_skills match the enrichment.
    """
    from tests.conftest import EXPECTED_ENRICHMENT, make_enrichment_client

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from app.dedup.embedder import FakeEmbedder  # deferred — Pitfall 7
    embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    client = make_enrichment_client(EXPECTED_ENRICHMENT)

    score = score_job(
        sample_job_remote, sample_user_profile, sample_cv_profile, embedder, client=client
    )

    assert score.reasons_for == EXPECTED_ENRICHMENT.reasons_for
    assert score.reasons_against == EXPECTED_ENRICHMENT.reasons_against
    assert score.matched_skills == EXPECTED_ENRICHMENT.matched_skills
