"""
Guard tests (RED → GREEN via Wave 2 refactor of scorer.py).

These tests verify the NEW scorer.py contract introduced in Phase 7:
  - score_job(job, user_profile, cv_profile, embedder, *, client=None)
  - All 4 numeric sub-scores computed deterministically (no OpenAI call)
  - embedder=None raises a clear error (not silent 0)
  - Deal-breaker detection is deterministic (keyword match, no LLM)

Run with: pytest tests/scoring/test_scorer_v2_guards.py -v
Expected before Phase 7 Wave 2: ALL FAIL (they define the target).
Expected after Phase 7 Wave 2: ALL PASS (they green the refactor).

CRITICAL: FakeEmbedder is imported INSIDE each test function body, NOT at module top.
This prevents accidental torch/sentence-transformers import at collection time (Pitfall 7).
"""
from __future__ import annotations

import os

import numpy as np
import pytest

from app.models.schemas import Job, Recommendation, RemoteJob
from app.scoring.scorer import score_job


# ---------------------------------------------------------------------------
# G-01: New signature — positional embedder as 4th argument
# ---------------------------------------------------------------------------

def test_g01_new_signature_positional_embedder(
    sample_job_remote,
    sample_user_profile,
    sample_cv_profile,
) -> None:
    """G-01: score_job accepts the new signature with embedder as 4th positional arg.

    Calling score_job(job, user_profile, cv_profile, embedder) must NOT raise
    TypeError. The old signature (job, cv_profile, user_profile, client=None)
    only accepts 3 positional args; this test fails against the old scorer.

    Expected before Wave 2: FAIL (TypeError: score_job() takes 3 positional args)
    Expected after Wave 2: PASS
    """
    from app.dedup.embedder import FakeEmbedder  # import deferido — Pitfall 7

    fake_embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0]))

    # Must not raise TypeError — new signature accepts embedder as 4th positional arg
    try:
        result = score_job(sample_job_remote, sample_user_profile, sample_cv_profile, fake_embedder)
        assert result is not None, "score_job debe devolver un resultado no-None"
    except TypeError as exc:
        pytest.fail(
            f"score_job debe aceptar embedder como 4.º argumento posicional. "
            f"TypeError: {exc}"
        )


# ---------------------------------------------------------------------------
# G-02: No-OPENAI_API_KEY path returns full valid JobScore
# ---------------------------------------------------------------------------

def test_g02_no_api_key_returns_full_jobscore(
    monkeypatch,
    sample_job_remote,
    sample_user_profile,
    sample_cv_profile,
) -> None:
    """G-02: With no OPENAI_API_KEY and a FakeEmbedder, score_job returns a complete JobScore.

    All 4 numeric sub-scores must be populated (not None) as integers in [0, 100].
    score_total must be in [0, 100]. recommendation must be a Recommendation enum.
    reasons_for and reasons_against must be non-None lists (may be rule-based strings).
    matched_skills must be a list (may be empty).

    Expected before Wave 2: FAIL (current scorer always calls the LLM)
    Expected after Wave 2: PASS
    """
    from app.dedup.embedder import FakeEmbedder  # import deferido — Pitfall 7

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    fake_embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0]))

    # Call with no client (no OpenAI) — must produce a full valid JobScore
    result = score_job(
        sample_job_remote,
        sample_user_profile,
        sample_cv_profile,
        fake_embedder,
        # client=None by default
    )

    # score_total in [0, 100]
    assert isinstance(result.score_total, int), (
        f"score_total debe ser int, se obtuvo {type(result.score_total)}"
    )
    assert 0 <= result.score_total <= 100, (
        f"score_total debe estar en [0, 100], se obtuvo {result.score_total}"
    )

    # recommendation is a Recommendation enum
    assert isinstance(result.recommendation, Recommendation), (
        f"recommendation debe ser Recommendation, se obtuvo {type(result.recommendation)}"
    )

    # All 4 desglose sub-scores are populated integers in [0, 100]
    d = result.desglose
    for field_name, value in [
        ("encaje_puesto", d.encaje_puesto),
        ("encaje_skills", d.encaje_skills),
        ("encaje_ubicacion", d.encaje_ubicacion),
        ("encaje_seniority", d.encaje_seniority),
    ]:
        assert isinstance(value, int), (
            f"desglose.{field_name} debe ser int, se obtuvo {type(value)}"
        )
        assert 0 <= value <= 100, (
            f"desglose.{field_name} debe estar en [0, 100], se obtuvo {value}"
        )

    # puesto_detectado is a string
    assert isinstance(result.puesto_detectado, str), (
        f"puesto_detectado debe ser str, se obtuvo {type(result.puesto_detectado)}"
    )

    # deal_breaker_hit is a bool
    assert isinstance(result.deal_breaker_hit, bool), (
        f"deal_breaker_hit debe ser bool, se obtuvo {type(result.deal_breaker_hit)}"
    )

    # reasons_for and reasons_against are non-None lists (rule-based fallbacks)
    assert result.reasons_for is not None, "reasons_for no debe ser None"
    assert isinstance(result.reasons_for, list), (
        f"reasons_for debe ser list, se obtuvo {type(result.reasons_for)}"
    )
    assert result.reasons_against is not None, "reasons_against no debe ser None"
    assert isinstance(result.reasons_against, list), (
        f"reasons_against debe ser list, se obtuvo {type(result.reasons_against)}"
    )

    # matched_skills is a list (may be empty — deterministic overlap is valid)
    assert isinstance(result.matched_skills, list), (
        f"matched_skills debe ser list, se obtuvo {type(result.matched_skills)}"
    )

    # missing_requirements is a list
    assert isinstance(result.missing_requirements, list), (
        f"missing_requirements debe ser list, se obtuvo {type(result.missing_requirements)}"
    )


# ---------------------------------------------------------------------------
# G-03: embedder=None raises a clear error (not silent 0)
# ---------------------------------------------------------------------------

def test_g03_embedder_none_raises_clear_error(
    monkeypatch,
    sample_job_remote,
    sample_user_profile,
    sample_cv_profile,
) -> None:
    """G-03: Passing embedder=None raises ValueError or TypeError with 'embedder' in message.

    The new scorer must detect a missing embedder and raise a CLEAR error
    (not silently return 0 for encaje_skills, which would be misleading).

    Expected before Wave 2: FAIL (old scorer ignores embedder arg entirely)
    Expected after Wave 2: PASS
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises((ValueError, TypeError)) as exc_info:
        score_job(
            sample_job_remote,
            sample_user_profile,
            sample_cv_profile,
            None,  # embedder=None — must raise, not silently produce 0
        )

    error_message = str(exc_info.value).lower()
    assert "embedder" in error_message, (
        f"El error debe mencionar 'embedder' para orientar al desarrollador. "
        f"Mensaje actual: {exc_info.value!r}"
    )


# ---------------------------------------------------------------------------
# G-04: Deal-breaker deterministic (works with client=None, no OPENAI_API_KEY)
# ---------------------------------------------------------------------------

def test_g04_deal_breaker_deterministic_no_llm(
    monkeypatch,
    sample_user_profile,
    sample_cv_profile,
) -> None:
    """G-04: A deal_breaker keyword in job text forces deal_breaker_hit=True and skip.

    The deal-breaker check must be deterministic (keyword match), NOT delegated to
    the LLM. This test passes client=None and clears OPENAI_API_KEY to confirm no
    LLM call is needed for deal-breaker detection.

    sample_user_profile.deal_breakers = ["exige 5+ años de experiencia", ...]
    The job description contains this exact phrase.

    Expected before Wave 2: FAIL (current scorer delegates deal-breaker to LLM assess_job)
    Expected after Wave 2: PASS
    """
    from app.dedup.embedder import FakeEmbedder  # import deferido — Pitfall 7

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Inline job with a deal-breaker phrase in the description
    deal_breaker_phrase = "exige 5+ años de experiencia"
    job_with_deal_breaker = Job(
        id="deal-breaker-test-job",
        title="AI Engineer Senior",
        company="SomeCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description=(
            f"We are looking for an AI Engineer. The position {deal_breaker_phrase}. "
            "Remote friendly, great benefits."
        ),
        source="test",
    )

    fake_embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0]))

    result = score_job(
        job_with_deal_breaker,
        sample_user_profile,
        sample_cv_profile,
        fake_embedder,
        # client=None — no LLM, deal-breaker must be caught deterministically
    )

    assert result.deal_breaker_hit is True, (
        f"Oferta con deal-breaker en descripción debe tener deal_breaker_hit=True. "
        f"Se obtuvo deal_breaker_hit={result.deal_breaker_hit}, "
        f"recommendation={result.recommendation}"
    )
    assert result.recommendation == Recommendation.skip, (
        f"deal_breaker_hit=True debe forzar recommendation=skip. "
        f"Se obtuvo {result.recommendation}"
    )


# ---------------------------------------------------------------------------
# G-05: Embedder-driven ranking match → rango_puesto=1 and encaje_puesto=100
# ---------------------------------------------------------------------------

def test_g05_embedder_driven_ranking_match(
    monkeypatch,
    sample_user_profile,
    sample_cv_profile,
) -> None:
    """G-05: FakeEmbedder with identical vectors for job title and ranking #1 entry
    yields rango_puesto=1 and encaje_puesto=100.

    The new scorer must use the injected embedder to compute cosine similarity
    between the job title and each ranking entry's nombre+sinónimos, then pick the
    best-matching entry. With cosine=1.0, the match is the top ranking entry.

    Current scorer (Wave 1): ranking match is done by LLM → this test FAILS.
    After Wave 2 refactor: ranking match via embedder cosine → this test PASSES.

    FakeEmbedder strategy:
      - key = job title ("AI Engineer") → vector [1.0, 0.0, 0.0, 0.0]
      - key = ranking entry #1 ("Ingeniero de IA / AI Engineer") → same vector
      - All other texts → fallback hash vector (low similarity to [1,0,0,0])
    """
    from app.dedup.embedder import FakeEmbedder  # import deferido — Pitfall 7

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    entry_1 = sample_user_profile.ranking_puestos[0]
    # Corpus key = titulo + sinonimos joined (SC3: puesto_match uses synonyms in corpus)
    ranking_corpus_key_1 = " ".join([entry_1.titulo, *entry_1.sinonimos]).strip()
    job_title = "AI Engineer"

    identical_vector = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    # FakeEmbedder: job title and ranking entry #1 corpus key share the same vector → cosine = 1.0
    embedder = FakeEmbedder(
        vectors={
            job_title: identical_vector,
            ranking_corpus_key_1: identical_vector,
        },
        # All other texts get a hash-based fallback (orthogonal in practice)
    )

    job = Job(
        id="ai-engineer-ranking-test",
        title=job_title,
        company="TechCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description="We need an AI Engineer with Python and LLMs.",
        source="test",
    )

    result = score_job(
        job,
        sample_user_profile,
        sample_cv_profile,
        embedder,
        # client=None — ranking match via embedder, not LLM
    )

    assert result.rango_puesto == 1, (
        f"Con cosine=1.0 contra ranking entry #1, rango_puesto debe ser 1. "
        f"Se obtuvo rango_puesto={result.rango_puesto}, "
        f"puesto_detectado={result.puesto_detectado!r}"
    )
    assert result.desglose.encaje_puesto == 100, (
        f"rango_puesto=1 debe dar encaje_puesto=100. "
        f"Se obtuvo encaje_puesto={result.desglose.encaje_puesto}"
    )
