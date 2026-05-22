"""Router de perfil de usuario y health check del servicio.

Expone:
    GET /health  — devuelve {status: ok}; usado por n8n para verificar disponibilidad.
    GET /profile — devuelve el UserProfile cargado desde data/profile.yaml.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.config.loader import load_user_profile
from app.models.schemas import UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["profile"])


@router.get("/health")
def health() -> dict:
    """Endpoint de health check. Devuelve 200 {status: ok} si el servicio está vivo."""
    return {"status": "ok"}


@router.get("/profile", response_model=UserProfile)
def get_profile() -> UserProfile:
    """Devuelve el UserProfile cargado desde data/profile.yaml.

    Raises:
        HTTPException 404: si profile.yaml no existe.
        HTTPException 500: si profile.yaml tiene errores de schema.
    """
    try:
        return load_user_profile()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
