"""
Tests de app/config/loader.py: carga y validación de UserProfile desde YAML.

Cubre SCORE-06: los pesos configurables se cargan desde profile.yaml y se
validan (suma=1.0). También verifica manejo de errores claros para rutas
inexistentes y schemas inválidos.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.config import load_user_profile


# ──────────────────────────────────────────────────────────────────────────────
# Test 1: carga del perfil real
# ──────────────────────────────────────────────────────────────────────────────

def test_carga_perfil_real() -> None:
    """load_user_profile() sin argumentos devuelve un UserProfile coherente.

    WR-05: el default usa _PROJECT_ROOT / 'data/profile.yaml' resuelto desde
    __file__ del loader, por lo que funciona independientemente del CWD actual.
    Usa _PROJECT_ROOT explícitamente para que el test sea igualmente robusto.
    """
    from app.config.loader import _PROJECT_ROOT

    profile_path = _PROJECT_ROOT / "data" / "profile.yaml"
    if not profile_path.exists():
        pytest.skip(f"data/profile.yaml no existe en {_PROJECT_ROOT} (entorno sin datos reales)")
    profile = load_user_profile(profile_path)

    # Primer puesto del ranking es AI Engineer
    assert "AI Engineer" in profile.ranking_puestos[0].titulo

    # Deal-breaker de presencial fuera de Barcelona
    assert "presencial fuera de Barcelona" in profile.deal_breakers

    # Pesos por defecto (puesto = 0.35)
    assert profile.pesos.puesto == pytest.approx(0.35)

    # Los pesos deben sumar 1.0 (validados por PesosScoring.check_sum)
    total = (
        profile.pesos.puesto
        + profile.pesos.skills
        + profile.pesos.ubicacion
        + profile.pesos.seniority
    )
    assert abs(total - 1.0) < 1e-6


# ──────────────────────────────────────────────────────────────────────────────
# Test 2: ruta inexistente → FileNotFoundError
# ──────────────────────────────────────────────────────────────────────────────

def test_ruta_inexistente_lanza_filenotfound() -> None:
    """Ruta inexistente lanza FileNotFoundError con mensaje claro."""
    with pytest.raises(FileNotFoundError, match="No se encontró profile.yaml en"):
        load_user_profile("data/no_existe.yaml")


# ──────────────────────────────────────────────────────────────────────────────
# Test 3: pesos inválidos → ValueError (pesos no suman 1.0)
# ──────────────────────────────────────────────────────────────────────────────

def test_yaml_invalido_pesos_lanza_valueerror(tmp_path: Path) -> None:
    """YAML con pesos que no suman 1.0 lanza ValueError con mensaje claro."""
    yaml_invalido = textwrap.dedent("""\
        datos_personales:
          nombre: "Test"
          email: "test@example.com"
          ubicacion_actual: "Barcelona"

        preferencias_ubicacion:
          ciudades_preferidas: ["Barcelona"]
          pais: "España"
          dispuesto_a_reubicarse: false

        preferencia_remoto:
          modalidad_ideal: "remote"
          acepta_onsite_solo_en: ["Barcelona"]

        ranking_puestos:
          - titulo: "AI Engineer"
            sinonimos: []

        deal_breakers: []

        pesos:
          puesto: 0.90
          skills: 0.90
          ubicacion: 0.90
          seniority: 0.90
    """)
    yaml_file = tmp_path / "profile_invalido.yaml"
    yaml_file.write_text(yaml_invalido, encoding="utf-8")

    with pytest.raises(ValueError, match="profile.yaml inválido"):
        load_user_profile(str(yaml_file))


# ──────────────────────────────────────────────────────────────────────────────
# Test 4: profile mínimo válido en tmp_path
# ──────────────────────────────────────────────────────────────────────────────

def test_carga_perfil_valido_minimo(tmp_path: Path) -> None:
    """Un profile.yaml mínimo con todos los campos requeridos devuelve UserProfile."""
    yaml_minimo = textwrap.dedent("""\
        datos_personales:
          nombre: "Test User"
          email: "test@example.com"
          ubicacion_actual: "Madrid"

        preferencias_ubicacion:
          ciudades_preferidas: ["Madrid"]
          pais: "España"
          dispuesto_a_reubicarse: false

        preferencia_remoto:
          modalidad_ideal: "indiferente"
          acepta_onsite_solo_en: []

        ranking_puestos:
          - titulo: "Software Engineer"
            sinonimos: ["SWE", "Dev"]

        deal_breakers:
          - "sin contrato"

        pesos:
          puesto: 0.35
          skills: 0.30
          ubicacion: 0.20
          seniority: 0.15
    """)
    yaml_file = tmp_path / "profile_minimo.yaml"
    yaml_file.write_text(yaml_minimo, encoding="utf-8")

    profile = load_user_profile(str(yaml_file))

    assert profile.datos_personales.nombre == "Test User"
    assert len(profile.ranking_puestos) == 1
    assert profile.ranking_puestos[0].titulo == "Software Engineer"
    assert profile.deal_breakers == ["sin contrato"]
    assert profile.pesos.puesto == pytest.approx(0.35)
