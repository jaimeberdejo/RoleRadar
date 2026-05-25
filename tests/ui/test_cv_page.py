"""Tests for ui/cv_logic.py — cache-first CV resolution (SC1, D-12).

These tests verify that:
- SC1: A cache HIT does NOT call parse_cv (same PDF → no re-parse).
- Cache MISS calls parse_cv exactly once and then saves the result.

All tests are pure-Python (no Streamlit runtime required).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.schemas import CVProfile, Experiencia


# ---------------------------------------------------------------------------
# Sample CVProfile for use in tests
# ---------------------------------------------------------------------------

_SAMPLE_PROFILE = CVProfile(
    experiencia=[
        Experiencia(empresa="Acme Corp", rol="AI Engineer", duracion="2 años")
    ],
    skills_tecnicas=["Python", "LLMs"],
    anios_experiencia_total=2.0,
    dominios=["IA"],
)

_FAKE_PDF_BYTES = b"%PDF-1.4 fake content for hashing"


# ---------------------------------------------------------------------------
# SC1: cache hit skips parse_cv
# ---------------------------------------------------------------------------


def test_cache_hit_skips_parse():
    """cache HIT → parse_cv is NOT called; was_cached is True (SC1)."""
    with (
        patch("ui.cv_logic.load_cached_profile", return_value=_SAMPLE_PROFILE) as mock_load,
        patch("ui.cv_logic.parse_cv") as mock_parse,
        patch("ui.cv_logic.save_cached_profile") as mock_save,
    ):
        from ui.cv_logic import resolve_cv_profile

        profile, was_cached = resolve_cv_profile(_FAKE_PDF_BYTES)

    assert was_cached is True
    assert profile is _SAMPLE_PROFILE
    mock_parse.assert_not_called()
    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Cache miss: parse once, save once
# ---------------------------------------------------------------------------


def test_cache_miss_parses_and_saves():
    """cache MISS → parse_cv called once, result saved; was_cached is False."""
    with (
        patch("ui.cv_logic.load_cached_profile", return_value=None) as mock_load,
        patch("ui.cv_logic.parse_cv", return_value=_SAMPLE_PROFILE) as mock_parse,
        patch("ui.cv_logic.save_cached_profile") as mock_save,
    ):
        from ui.cv_logic import resolve_cv_profile

        profile, was_cached = resolve_cv_profile(_FAKE_PDF_BYTES)

    assert was_cached is False
    assert profile is _SAMPLE_PROFILE
    mock_parse.assert_called_once()
    mock_save.assert_called_once()
