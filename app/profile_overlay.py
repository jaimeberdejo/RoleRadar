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
import logging
from pathlib import Path

from pydantic import ValidationError

from app.config.loader import load_user_profile
from app.models.schemas import PesosScoring, UserProfile

logger = logging.getLogger(__name__)


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
        FileNotFoundError: If profile.yaml is missing.

    Notes:
        WR-04: if the persisted score_weight_* are malformed or do not sum to 1.0
        (legacy/partial data, manual DB edit, weights from an older build), this
        falls back to the profile.yaml pesos (known valid) with a logged warning
        instead of raising. This keeps both the Run now and Re-score paths alive
        rather than dying with an uncaught ValueError.
    """
    base = load_user_profile(path=profile_path)

    # --- Overlay pesos (score weights) ---
    # WR-04: PesosScoring's validator raises if the weights don't sum to 1.0, and
    # float() raises if a value is malformed. Either way, fall back to base.pesos
    # (the profile.yaml weights, already known valid) so a bad DB value can never
    # crash the worker / Run now / Re-score paths.
    try:
        new_pesos = PesosScoring(
            puesto=float(settings.get("score_weight_puesto", "0.35")),
            skills=float(settings.get("score_weight_skills", "0.30")),
            ubicacion=float(settings.get("score_weight_ubicacion", "0.20")),
            seniority=float(settings.get("score_weight_seniority", "0.15")),
        )
    except (ValidationError, ValueError, TypeError) as exc:
        logger.warning(
            "build_effective_profile: persisted score_weight_* invalid (%s) — "
            "falling back to profile.yaml pesos %s",
            exc,
            base.pesos,
        )
        new_pesos = base.pesos

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
