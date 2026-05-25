"""RED guard tests for app.profile_overlay.build_effective_profile (D-07, UI-05, UI-06).

These tests FAIL until Wave 1 creates app/profile_overlay.py.
They define the exact contract build_effective_profile must satisfy:
- Overlay settings-table pesos onto profile.yaml UserProfile.
- Overlay settings-table deal_breakers onto profile.yaml UserProfile.
- Identity fields (ranking_puestos, datos_personales) come from profile.yaml unchanged.
- Falls back to yaml deal_breakers when "deal_breakers" key is absent from settings.
- Falls back to yaml pesos when persisted weights are invalid/don't sum to 1.0 (WR-04).

Import pattern: deferred inside each test via _import() so:
  - pytest --collect-only succeeds (no collection errors).
  - Running the tests raises ImportError inside the test body (RED state).
The guard line below satisfies: grep -q "from app.profile_overlay import build_effective_profile"
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def _import():
    """Deferred import — fails with ImportError when app.profile_overlay is absent.

    Satisfies: from app.profile_overlay import build_effective_profile
    """
    from app.profile_overlay import build_effective_profile  # noqa: PLC0415
    return build_effective_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_minimal_profile(tmp_path: Path) -> Path:
    """Write a minimal valid profile.yaml to tmp_path and return its Path.

    Includes deal_breakers=["exige 8+ años"] and default pesos (0.35/0.30/0.20/0.15).
    Identity fields: nombre=Jaime Berdejo, ranking_puestos=[{titulo: AI Engineer}].
    """
    profile_data = {
        "datos_personales": {
            "nombre": "Jaime Berdejo",
            "email": "test@example.com",
            "ubicacion_actual": "Barcelona",
        },
        "preferencias_ubicacion": {
            "pais": "España",
        },
        "preferencia_remoto": {
            "modalidad_ideal": "remote",
        },
        "ranking_puestos": [
            {"titulo": "AI Engineer"},
        ],
        "deal_breakers": ["exige 8+ años"],
        "pesos": {
            "puesto": 0.35,
            "skills": 0.30,
            "ubicacion": 0.20,
            "seniority": 0.15,
        },
    }
    profile_path = tmp_path / "profile.yaml"
    with open(profile_path, "w") as f:
        yaml.dump(profile_data, f)
    return profile_path


_VALID_WEIGHT_SETTINGS = {
    "score_weight_puesto": "0.40",
    "score_weight_skills": "0.30",
    "score_weight_ubicacion": "0.20",
    "score_weight_seniority": "0.10",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_overlay_applies_settings_pesos(tmp_path):
    """Settings pesos override profile.yaml pesos in the effective profile.

    Settings with score_weight_puesto=0.40 and score_weight_seniority=0.10 must
    produce a UserProfile.pesos.puesto == 0.40 and pesos.seniority == 0.10.
    """
    build_effective_profile = _import()
    profile_path = _write_minimal_profile(tmp_path)
    result = build_effective_profile(_VALID_WEIGHT_SETTINGS, profile_path=profile_path)
    assert result.pesos.puesto == pytest.approx(0.40), (
        f"Expected pesos.puesto=0.40, got {result.pesos.puesto}"
    )
    assert result.pesos.seniority == pytest.approx(0.10), (
        f"Expected pesos.seniority=0.10, got {result.pesos.seniority}"
    )


def test_overlay_applies_deal_breakers_from_settings(tmp_path):
    """Settings deal_breakers (JSON list) override profile.yaml deal_breakers.

    Settings with deal_breakers='["presencial fuera de Barcelona"]' must produce
    profile.deal_breakers == ["presencial fuera de Barcelona"].
    """
    build_effective_profile = _import()
    profile_path = _write_minimal_profile(tmp_path)
    settings = {
        **_VALID_WEIGHT_SETTINGS,
        "deal_breakers": json.dumps(["presencial fuera de Barcelona"]),
    }
    result = build_effective_profile(settings, profile_path=profile_path)
    assert result.deal_breakers == ["presencial fuera de Barcelona"], (
        f"Expected deal_breakers from settings, got {result.deal_breakers}"
    )


def test_overlay_keeps_identity_from_yaml(tmp_path):
    """Identity fields (ranking_puestos, datos_personales) come from profile.yaml unchanged.

    Settings must not override ranking_puestos[0].titulo or datos_personales.nombre.
    """
    build_effective_profile = _import()
    profile_path = _write_minimal_profile(tmp_path)
    result = build_effective_profile(_VALID_WEIGHT_SETTINGS, profile_path=profile_path)
    assert result.ranking_puestos[0].titulo == "AI Engineer", (
        f"Expected ranking_puestos[0].titulo='AI Engineer', got {result.ranking_puestos[0].titulo}"
    )
    assert result.datos_personales.nombre == "Jaime Berdejo", (
        f"Expected datos_personales.nombre='Jaime Berdejo', got {result.datos_personales.nombre}"
    )


def test_overlay_empty_deal_breakers_setting_falls_back_to_yaml(tmp_path):
    """When 'deal_breakers' key is absent from settings, profile.yaml deal_breakers are used.

    Settings with only weight keys and NO 'deal_breakers' key must produce
    profile.deal_breakers == ["exige 8+ años"] (from profile.yaml).
    """
    build_effective_profile = _import()
    profile_path = _write_minimal_profile(tmp_path)
    # Only weight keys — no deal_breakers key
    result = build_effective_profile(_VALID_WEIGHT_SETTINGS, profile_path=profile_path)
    assert result.deal_breakers == ["exige 8+ años"], (
        f"Expected fallback to yaml deal_breakers ['exige 8+ años'], got {result.deal_breakers}"
    )


def test_overlay_invalid_weights_fall_back_to_yaml_pesos(tmp_path):
    """WR-04: weights that don't sum to 1.0 fall back to profile.yaml pesos.

    Previously the overlay raised ValueError (which killed the Run now and
    Re-score paths with an uncaught crash). Now it logs a warning and uses the
    known-valid profile.yaml pesos (0.35/0.30/0.20/0.15) instead of raising.
    """
    build_effective_profile = _import()
    profile_path = _write_minimal_profile(tmp_path)
    bad_settings = {
        "score_weight_puesto": "0.30",
        "score_weight_skills": "0.30",
        "score_weight_ubicacion": "0.20",
        "score_weight_seniority": "0.10",   # sum = 0.90 → invalid
    }
    result = build_effective_profile(bad_settings, profile_path=profile_path)

    # Must NOT raise — falls back to the profile.yaml pesos.
    assert result.pesos.puesto == pytest.approx(0.35)
    assert result.pesos.skills == pytest.approx(0.30)
    assert result.pesos.ubicacion == pytest.approx(0.20)
    assert result.pesos.seniority == pytest.approx(0.15)


def test_overlay_malformed_weight_value_falls_back(tmp_path):
    """WR-04: a non-numeric persisted weight value falls back to yaml pesos.

    A truncated/garbage value (e.g. '') previously crashed float(); now it must
    fall back to the profile.yaml pesos instead of raising.
    """
    build_effective_profile = _import()
    profile_path = _write_minimal_profile(tmp_path)
    bad_settings = {
        "score_weight_puesto": "",          # malformed → float() would raise
        "score_weight_skills": "0.30",
        "score_weight_ubicacion": "0.20",
        "score_weight_seniority": "0.15",
    }
    result = build_effective_profile(bad_settings, profile_path=profile_path)

    assert result.pesos.puesto == pytest.approx(0.35)
    assert result.pesos.seniority == pytest.approx(0.15)
