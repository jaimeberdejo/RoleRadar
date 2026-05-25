"""Profile overlay helper — BuscadorDeEmpleo v2.0.

Import-clean (no streamlit). Used by run_pipeline, Run now, and Re-score so all
three agree on effective weights/deal-breakers (D-07).

The settings table is the cross-process config bus (v2.0 architecture decision).
profile.yaml stays as the identity source (ranking_puestos, datos_personales,
preferencias_*). The overlay applies only the mutable scoring config from the
UI's Settings page (score weights + deal-breakers) on top of profile.yaml.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.config.loader import load_user_profile
from app.models.schemas import PesosScoring, UserProfile


def build_effective_profile(
    settings: dict,
    profile_path: str | Path | None = None,
) -> UserProfile:
    """Build an effective UserProfile by overlaying settings onto profile.yaml.

    Reads score_weight_puesto/skills/ubicacion/seniority and deal_breakers (JSON
    list string) from the settings dict (sourced from the settings table), and
    overlays them onto the base UserProfile loaded from profile.yaml.

    Identity fields (ranking_puestos, datos_personales, preferencias_ubicacion,
    preferencia_remoto, expectativas, dedup_umbral) are never overridden — they
    come from profile.yaml unchanged.

    Args:
        settings: Dict from storage.get_settings() (all values are strings).
        profile_path: Override path to profile.yaml (used in tests / worker inject).
                      None → resolves to <project_root>/data/profile.yaml.

    Returns:
        UserProfile with pesos and deal_breakers from settings, identity from yaml.

    Raises:
        ValueError: If PesosScoring sum-to-1.0 validator fires (bad weights in DB).
                    Surfaces early at overlay construction time (T-10-02-02 mitig.).
        FileNotFoundError: If profile.yaml is missing.
    """
    base = load_user_profile(path=profile_path)

    # --- Overlay pesos (score weights) ---
    # PesosScoring validator raises ValueError if sum != 1.0 (D-08 / T-10-02-02).
    new_pesos = PesosScoring(
        puesto=float(settings.get("score_weight_puesto", "0.35")),
        skills=float(settings.get("score_weight_skills", "0.30")),
        ubicacion=float(settings.get("score_weight_ubicacion", "0.20")),
        seniority=float(settings.get("score_weight_seniority", "0.15")),
    )

    # --- Overlay deal_breakers (JSON list string from settings table) ---
    # T-10-02-01: bad JSON / wrong type → fall back to profile.yaml's deal_breakers.
    raw_db = settings.get("deal_breakers", "")
    try:
        new_deal_breakers = json.loads(raw_db) if raw_db else base.deal_breakers
        if not isinstance(new_deal_breakers, list):
            new_deal_breakers = base.deal_breakers
    except (json.JSONDecodeError, TypeError):
        new_deal_breakers = base.deal_breakers

    return base.model_copy(update={"pesos": new_pesos, "deal_breakers": new_deal_breakers})
