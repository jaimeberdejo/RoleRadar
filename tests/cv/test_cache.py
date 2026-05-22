"""
Tests unitarios para app/cv/cache.py.

Verifica que:
- El round-trip save→load preserva CVProfile completo (skills_tecnicas, anios_experiencia_total)
- load_cached_profile devuelve None si no existe el fichero en caché
- load_cached_profile devuelve None (y elimina el fichero) ante caché corrupta
- save/load rechazan con ValueError si el hash no es sha256 hexadecimal válido
- CV_CACHE_DIR es honrado: los tests aíslan la caché en tmp_path
"""
from __future__ import annotations

import json

import pytest

from app.cv.cache import load_cached_profile, save_cached_profile
from app.models.schemas import CVProfile, Experiencia

# Hash sha256 válido (64 hex en minúsculas) usado como clave de prueba.
_VALID_HASH = "a" * 64


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
    save_cached_profile(_VALID_HASH, sample_profile)
    loaded = load_cached_profile(_VALID_HASH)
    assert loaded is not None
    assert loaded.skills_tecnicas == ["Python", "LLMs"]
    assert loaded.anios_experiencia_total == 2.0


def test_cache_miss_returns_none(tmp_path, monkeypatch) -> None:
    """load_cached_profile devuelve None para un hash válido sin fichero en caché."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    absent_hash = "b" * 64
    assert load_cached_profile(absent_hash) is None


def test_cache_corrupt_file_returns_none(tmp_path, monkeypatch) -> None:
    """load_cached_profile devuelve None y elimina el fichero si el JSON está corrupto."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    corrupt_file = tmp_path / f"{_VALID_HASH}.json"
    corrupt_file.write_text("{invalid json", encoding="utf-8")
    result = load_cached_profile(_VALID_HASH)
    assert result is None
    assert not corrupt_file.exists()


def test_invalid_hash_raises_for_load(tmp_path, monkeypatch) -> None:
    """load_cached_profile lanza ValueError para hashes no sha256."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="Clave de caché inválida"):
        load_cached_profile("abc123")


def test_invalid_hash_raises_for_save(tmp_path, monkeypatch, sample_profile: CVProfile) -> None:
    """save_cached_profile lanza ValueError para hashes no sha256."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="Clave de caché inválida"):
        save_cached_profile("../evil", sample_profile)
