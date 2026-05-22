"""
Carga y validación del perfil de usuario desde data/profile.yaml.

Responsabilidades:
  - load_user_profile: lee el fichero YAML con yaml.safe_load (nunca yaml.load),
    valida con UserProfile.model_validate y lanza errores claros si la ruta
    no existe o el schema es inválido.

Satisface SCORE-06: los pesos configurables (PesosScoring) se cargan desde
profile.yaml y se validan al cargar (suma=1.0 via model_validator en schema).
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models.schemas import UserProfile

logger = logging.getLogger(__name__)

# Raíz del proyecto: app/config/loader.py → app/config → app → project root.
# Resuelto en tiempo de import (relativo a __file__) para que el default de
# load_user_profile sea robusto independientemente del CWD (WR-05).
_PROJECT_ROOT = Path(__file__).parent.parent.parent


def load_user_profile(path: str | Path | None = None) -> UserProfile:
    """Carga y valida el UserProfile desde un fichero YAML.

    Usa yaml.safe_load (nunca yaml.load — seguridad contra ejecución de código).
    La validación de pesos (suma=1.0) la realiza PesosScoring.check_sum al hacer
    model_validate; no se duplica aquí.

    Args:
        path: Ruta al fichero YAML del perfil de usuario.
              Por defecto: None → resuelve a <project_root>/data/profile.yaml
              usando __file__ (robusto ante cualquier CWD — WR-05).
              Se puede pasar str o Path para sobreescribir (ej. tests).

    Returns:
        UserProfile validado con todos los campos del perfil.

    Raises:
        FileNotFoundError: Si la ruta no existe. El mensaje incluye la ruta exacta.
        ValueError: Si el YAML es sintácticamente inválido o el schema no se cumple
                    (incluyendo pesos que no suman 1.0). El mensaje incluye el detalle
                    del error de validación de Pydantic.
    """
    resolved = Path(path) if path is not None else _PROJECT_ROOT / "data" / "profile.yaml"
    try:
        with open(resolved) as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"No se encontró profile.yaml en: {resolved}")
    try:
        profile = UserProfile.model_validate(data)
    except ValidationError as e:
        raise ValueError(f"profile.yaml inválido:\n{e}") from e
    logger.debug(
        "Perfil cargado: %s, %d puestos en ranking, pesos puesto=%.2f",
        profile.datos_personales.nombre,
        len(profile.ranking_puestos),
        profile.pesos.puesto,
    )
    return profile
