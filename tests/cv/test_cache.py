"""
Tests unitarios para app/cv/cache.py.

Verifica que:
- El round-trip save→load preserva CVProfile completo (skills_tecnicas, anios_experiencia_total)
- load_cached_profile devuelve None si no existe el fichero en caché
- CV_CACHE_DIR es honrado: los tests aíslan la caché en tmp_path
"""
from __future__ import annotations

import pytest

from app.cv.cache import load_cached_profile, save_cached_profile
from app.models.schemas import CVProfile, Experiencia


@pytest.fixture
def sample_profile() -> CVProfile:
    """CVProfile con datos conocidos para verificar roundtrip de serialización."""
    return CVProfile(
        experiencia=[Experiencia(empresa="Acme Corp", rol="AI Engineer", duracion="2 años")],
        skills_tecnicas=["Python", "LLMs"],
        anios_experiencia_total=2.0,
        dominios=["IA"],
    )


def test_cache_roundtrip(tmp_path, monkeypatch, sample_profile: CVProfile) -> None:
    """save_cached_profile seguido de load_cached_profile devuelve un CVProfile igual."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    h = "abc123"
    save_cached_profile(h, sample_profile)
    loaded = load_cached_profile(h)
    assert loaded is not None
    assert loaded.skills_tecnicas == ["Python", "LLMs"]
    assert loaded.anios_experiencia_total == 2.0


def test_cache_miss_returns_none(tmp_path, monkeypatch) -> None:
    """load_cached_profile devuelve None para un hash sin fichero en caché."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    assert load_cached_profile("nonexistent_hash") is None
