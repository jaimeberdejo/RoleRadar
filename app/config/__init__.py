"""Módulo de configuración del servicio.

Interfaz pública:
    load_user_profile(path: str = "data/profile.yaml") -> UserProfile
"""

from app.config.loader import load_user_profile

__all__ = ["load_user_profile"]
