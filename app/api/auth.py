"""Autenticación por cabecera X-API-Key para el servicio BuscadorDeEmpleo.

Diseño:
  - API_KEY ausente del entorno → autenticación DESACTIVADA. Cualquier petición
    pasa sin restricciones. En el arranque (ver log_auth_startup_warning) se emite
    un WARNING ruidoso. Esto mantiene los tests existentes verdes sin modificarlos
    (no exportan API_KEY).
  - API_KEY presente → se exige la cabecera X-API-Key en TODAS las rutas salvo
    las incluidas en _PUBLIC_PATHS (actualmente solo GET /health).
    Cabecera ausente o incorrecta → 401 con el mismo mensaje (no se distingue entre
    los dos casos — anti information disclosure). Comparación con
    secrets.compare_digest para evitar timing attacks (T-sg6-01).

Mecanismo de enforcement: ApiKeyMiddleware (Starlette BaseHTTPMiddleware).
Usando middleware en lugar de FastAPI dependencies=[] se cubren también
/docs, /openapi.json y /redoc con un solo código path (T-sg6-03).

Uso en main.py:
    from app.api.auth import ApiKeyMiddleware, log_auth_startup_warning

    app = FastAPI(...)
    app.add_middleware(ApiKeyMiddleware)

    # En lifespan, llamar log_auth_startup_warning() tras configure_logging()
"""
from __future__ import annotations

import logging
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse as StarletteJSONResponse

logger = logging.getLogger(__name__)

# Rutas exentas de autenticación (siempre públicas).
# GET /health es pública para que Docker healthcheck y n8n puedan verificar
# disponibilidad sin necesitar la clave (T-sg6-03: /docs sí está protegida).
_PUBLIC_PATHS: frozenset[str] = frozenset({"/health"})


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Middleware que aplica autenticación X-API-Key a todas las rutas
    excepto las de _PUBLIC_PATHS.

    Cuando API_KEY no está en el entorno → pasa todo sin tocar (modo dev/test).
    Cuando API_KEY está → exige la cabecera en rutas no exentas.

    La comprobación usa secrets.compare_digest para tiempo constante (T-sg6-01).
    El mismo 401 para cabecera ausente y para cabecera incorrecta (T-sg6-02).
    """

    async def dispatch(self, request: StarletteRequest, call_next):  # type: ignore[override]
        expected = os.environ.get("API_KEY", "")
        if not expected or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        provided = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(provided, expected):
            return StarletteJSONResponse(
                status_code=401,
                content={
                    "error": {
                        "type": "Unauthorized",
                        "message": "Invalid or missing API key",
                    }
                },
            )
        return await call_next(request)


def log_auth_startup_warning() -> None:
    """Emite WARNING ruidoso si API_KEY no está configurada.

    Llamar desde lifespan (app/api/main.py) tras configure_logging() para que
    el mensaje aparezca con el formato correcto desde el inicio del servicio.

    Cuando API_KEY está configurada emite INFO confirmando que auth está activa.
    """
    if not os.environ.get("API_KEY", ""):
        logger.warning(
            "API_KEY not set — authentication DISABLED, service is open. "
            "Set API_KEY in .env to protect all endpoints (except GET /health)."
        )
    else:
        logger.info(
            "API_KEY configured — authentication ENABLED on all routes except GET /health."
        )
