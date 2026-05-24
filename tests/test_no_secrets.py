"""Tests de secretos en ficheros de configuración — MIG-03.

Verifica que docker-compose.yml no contiene la RAPIDAPI_KEY literal
(la clave fue expuesta en el working tree; este test previene regresiones).
"""
from __future__ import annotations

from pathlib import Path

# Ruta resuelta desde __file__ para funcionar independientemente del CWD
_REPO_ROOT = Path(__file__).parent.parent


def test_docker_compose_no_literal_rapidapi_key() -> None:
    """docker-compose.yml no contiene la RAPIDAPI_KEY literal. (MIG-03)

    La clave expuesta anteriormente era:
        dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148
    Este test falla si esa cadena aparece en el fichero.
    """
    compose_path = _REPO_ROOT / "docker-compose.yml"
    assert compose_path.exists(), f"docker-compose.yml no encontrado en {_REPO_ROOT}"

    content = compose_path.read_text(encoding="utf-8")

    # La clave expuesta no debe aparecer nunca más
    assert "dfae5ddf3fmshc64763c72ab92c1p17c53fjsnee4d98fb1148" not in content, (
        "RAPIDAPI_KEY literal encontrada en docker-compose.yml — usar ${RAPIDAPI_KEY:-}"
    )
    # Verificación estructural: no debe haber asignación literal con la clave
    assert "RAPIDAPI_KEY: dfae" not in content
