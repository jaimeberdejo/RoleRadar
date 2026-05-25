"""
Tests for app/scoring/seniority.py — deterministic seniority rule engine.

TDD RED phase: these tests define the expected behaviour before implementation.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Import guard: seniority.py must load without any heavy deps (torch, etc.)
# ---------------------------------------------------------------------------
def test_importable_without_heavy_deps() -> None:
    """The module must import cleanly; no torch/embedding stack pulled in."""
    from app.scoring.seniority import SeniorityResult, evaluar_seniority  # noqa: F401


# ---------------------------------------------------------------------------
# Return-type contract
# ---------------------------------------------------------------------------
def test_returns_seniority_result() -> None:
    from app.scoring.seniority import SeniorityResult, evaluar_seniority

    result = evaluar_seniority("5+ years Python experience", 3.0)
    assert isinstance(result, SeniorityResult)
    assert isinstance(result.encaje_seniority, int)
    assert isinstance(result.seniority_nota, str)


def test_seniority_nota_never_empty() -> None:
    from app.scoring.seniority import evaluar_seniority

    cases = [
        ("5+ years required", None),
        ("5+ years required", 2.0),
        ("2+ years of experience required", 4.0),
        ("senior engineer needed", 6.0),
        ("junior developer", 1.0),
        ("no specific mention", 3.0),
    ]
    for desc, anios in cases:
        r = evaluar_seniority(desc, anios)
        assert r.seniority_nota, (
            f"seniority_nota must never be empty for desc={desc!r}, anios={anios}"
        )


def test_score_always_0_to_100() -> None:
    from app.scoring.seniority import evaluar_seniority

    cases = [
        ("10+ years required", 1.0),
        ("1+ years required", 15.0),
        ("senior lead principal staff director", 0.5),
        ("junior developer", 0.5),
        ("no signal", None),
    ]
    for desc, anios in cases:
        r = evaluar_seniority(desc, anios)
        assert 0 <= r.encaje_seniority <= 100, (
            f"Score out of range for desc={desc!r}, anios={anios}: got {r.encaje_seniority}"
        )


# ---------------------------------------------------------------------------
# None / unknown candidate case — STATE blocker
# ---------------------------------------------------------------------------
def test_none_anios_returns_neutral_50() -> None:
    """Critical: anios_candidato=None must always return encaje_seniority=50."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("5+ years Python required", None)
    assert r.encaje_seniority == 50, (
        f"anios=None should give neutral 50, got {r.encaje_seniority}"
    )


def test_none_anios_nota_mentions_desconocida() -> None:
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("5+ years required", None)
    assert "desconocida" in r.seniority_nota.lower(), (
        f"Note should contain 'desconocida' for None anios, got: {r.seniority_nota!r}"
    )


def test_none_anios_with_no_description_signal() -> None:
    """Even with no years in description, None anios still returns 50."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("no specific years mentioned", None)
    assert r.encaje_seniority == 50


# ---------------------------------------------------------------------------
# Candidate EXCEEDS requirement
# ---------------------------------------------------------------------------
def test_candidate_exceeds_requirement_high_score() -> None:
    """4 years vs 2 required → ratio 2.0 → score >= 85."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("2+ years of experience required", 4.0)
    assert r.encaje_seniority >= 85, (
        f"4yr vs 2yr req → ratio 2.0 should give >=85, got {r.encaje_seniority}"
    )
    assert r.anos_requeridos == 2.0, (
        f"Should parse 2.0 years, got {r.anos_requeridos}"
    )


def test_candidate_significantly_exceeds_requirement() -> None:
    """10 years vs 3 required → ratio ~3.3 → score == 100."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("3+ years experience required", 10.0)
    assert r.encaje_seniority == 100, (
        f"10yr vs 3yr → should be 100, got {r.encaje_seniority}"
    )


# ---------------------------------------------------------------------------
# Candidate BELOW requirement — must NOT be 0 (CLAUDE.md rule 3)
# ---------------------------------------------------------------------------
def test_candidate_below_requirement_low_but_nonzero() -> None:
    """2 years vs 5 required → ratio 0.4 → score in (0, 50]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("Minimum 5+ years of experience", 2.0)
    assert 0 < r.encaje_seniority <= 50, (
        f"2yr vs 5yr → should be low (>0 and <=50), got {r.encaje_seniority}"
    )


def test_very_junior_for_senior_role_not_zero() -> None:
    """1 year vs 10 required → very low but must NOT be 0 (not auto-skip)."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("10+ years of senior experience", 1.0)
    assert r.encaje_seniority > 0, (
        f"Very low seniority must NOT be 0 (no auto-skip), got {r.encaje_seniority}"
    )
    assert r.encaje_seniority <= 20, (
        f"Very low seniority should be quite low, got {r.encaje_seniority}"
    )


def test_below_requirement_nota_mentions_por_debajo() -> None:
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("5+ years required", 2.0)
    assert "debajo" in r.seniority_nota.lower() or "below" in r.seniority_nota.lower(), (
        f"Note should mention 'debajo' for below-requirement case: {r.seniority_nota!r}"
    )


# ---------------------------------------------------------------------------
# Level keyword signals
# ---------------------------------------------------------------------------
def test_senior_keyword_high_experience() -> None:
    """'senior engineer' + 6 years → encaje_seniority in [70, 100]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("Looking for a senior engineer to join our team", 6.0)
    assert 70 <= r.encaje_seniority <= 100, (
        f"senior + 6yr should be 70-100, got {r.encaje_seniority}"
    )


def test_junior_keyword_low_experience_good_match() -> None:
    """'junior developer' + 1 year → encaje_seniority in [80, 100]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("junior developer", 1.0)
    assert 80 <= r.encaje_seniority <= 100, (
        f"junior + 1yr should be 80-100, got {r.encaje_seniority}"
    )


def test_lead_keyword_senior_candidate() -> None:
    """'lead' keyword + strong candidate → reasonable match."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("We need a strong lead engineer for our platform", 8.0)
    assert r.encaje_seniority >= 65, (
        f"lead + 8yr should be >=65, got {r.encaje_seniority}"
    )


# ---------------------------------------------------------------------------
# No signal in description
# ---------------------------------------------------------------------------
def test_no_signal_in_description_generous() -> None:
    """No years, no level words → generous assumption for known candidate."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("We are looking for a great developer to join", 3.0)
    assert 50 <= r.encaje_seniority <= 100, (
        f"No signal should be generous (50-100), got {r.encaje_seniority}"
    )
    assert r.anos_requeridos is None


# ---------------------------------------------------------------------------
# anos_requeridos field accuracy
# ---------------------------------------------------------------------------
def test_years_parsed_correctly_simple() -> None:
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("Must have 3+ years Python experience", 5.0)
    assert r.anos_requeridos == 3.0, (
        f"Should parse 3.0 from '3+ years', got {r.anos_requeridos}"
    )


def test_years_parsed_anos_spanish() -> None:
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("Se requieren 4 años de experiencia", 4.0)
    assert r.anos_requeridos == 4.0, (
        f"Should parse 4.0 from '4 años', got {r.anos_requeridos}"
    )


def test_years_parsed_range_takes_lower_bound() -> None:
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("5-7 years of experience preferred", 5.0)
    assert r.anos_requeridos == 5.0, (
        f"Range '5-7 years' should use lower bound 5.0, got {r.anos_requeridos}"
    )


def test_years_parsed_at_least() -> None:
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("at least 6 years of experience in ML", 7.0)
    assert r.anos_requeridos == 6.0, (
        f"Should parse 6.0 from 'at least 6 years', got {r.anos_requeridos}"
    )


# ---------------------------------------------------------------------------
# Plan-specified behaviour examples
# ---------------------------------------------------------------------------
def test_plan_example_5yr_vs_2yr_low() -> None:
    """Plan spec: evaluar_seniority('5+ years Python experience', 2.0) → [20, 45]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("5+ years Python experience", 2.0)
    assert 20 <= r.encaje_seniority <= 45, (
        f"Plan example 5yr req vs 2yr cand should be 20-45, got {r.encaje_seniority}"
    )


def test_plan_example_2yr_vs_4yr_high() -> None:
    """Plan spec: evaluar_seniority('2+ years experience', 4.0) → [85, 100]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("2+ years experience", 4.0)
    assert 85 <= r.encaje_seniority <= 100, (
        f"Plan example 2yr req vs 4yr cand should be 85-100, got {r.encaje_seniority}"
    )


def test_plan_example_senior_keyword_5yr() -> None:
    """Plan spec: evaluar_seniority('senior engineer required', 5.0) → [70, 100]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("senior engineer required", 5.0)
    assert 70 <= r.encaje_seniority <= 100, (
        f"Plan example senior + 5yr should be 70-100, got {r.encaje_seniority}"
    )


def test_plan_example_junior_1yr() -> None:
    """Plan spec: evaluar_seniority('junior developer', 1.0) → [80, 100]."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("junior developer", 1.0)
    assert 80 <= r.encaje_seniority <= 100, (
        f"Plan example junior + 1yr should be 80-100, got {r.encaje_seniority}"
    )


def test_plan_example_no_signal_none_anios() -> None:
    """Plan spec: evaluar_seniority('no specific years mentioned', None) → 50."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("no specific years mentioned", None)
    assert r.encaje_seniority == 50


def test_plan_example_5yr_required_none_anios() -> None:
    """Plan spec: evaluar_seniority('5+ years required', None) → 50 (neutral even with req)."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("5+ years required", None)
    assert r.encaje_seniority == 50


# ---------------------------------------------------------------------------
# CR-01 fix: ZeroDivisionError on "0 years" / "0-2 years" descriptions
# ---------------------------------------------------------------------------
def test_zero_years_requirement_no_crash() -> None:
    """'0-2 years' must not raise ZeroDivisionError — treated as no-signal (score=75)."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("0-2 years experience preferred", 3.0)
    assert 0 < r.encaje_seniority <= 100, (
        f"Must not raise ZeroDivisionError; got score={r.encaje_seniority}"
    )


def test_zero_plus_years_no_crash() -> None:
    """'0+ years' (sometimes used in internship listings) must not crash."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("0+ years of experience required", 2.0)
    assert 0 < r.encaje_seniority <= 100


def test_zero_years_treated_as_no_signal_returns_75() -> None:
    """When anos_requeridos is 0, the generous no-signal score (75) is returned."""
    from app.scoring.seniority import evaluar_seniority

    r = evaluar_seniority("0-2 years experience preferred", 3.0)
    assert r.encaje_seniority == 75, (
        f"anos_requeridos=0 should fall back to no-signal score 75, got {r.encaje_seniority}"
    )
    assert r.anos_requeridos is None, (
        f"anos_requeridos should be None (treated as no signal), got {r.anos_requeridos}"
    )
