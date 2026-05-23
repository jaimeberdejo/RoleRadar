"""Tests de validación y aceptación para examples/*.json.

Verifica:
- Que los tres ficheros JSON son JSON válido y tienen la forma esperada.
- Que el payload de examples/process_request.json es aceptado por POST /jobs/process
  (LLM + embedder mockeados por api_client_with_cv; cero red, cero I/O externo).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# Rutas relativas a la raíz del repo (los tests se ejecutan desde la raíz).
EXAMPLES_DIR = Path("examples")
ARBEITNOW_FILE = EXAMPLES_DIR / "arbeitnow_offers.json"
GENERIC_FILE = EXAMPLES_DIR / "generic_offers.json"
PROCESS_FILE = EXAMPLES_DIR / "process_request.json"


def test_examples_son_json_valido() -> None:
    """Los tres ficheros de examples/ existen y son JSON válido.

    - arbeitnow_offers.json: lista de al menos 1 oferta.
    - generic_offers.json: lista de al menos 1 oferta.
    - process_request.json: dict con clave "sources".
    """
    # Arbeitnow
    assert ARBEITNOW_FILE.exists(), f"{ARBEITNOW_FILE} no existe"
    arbeitnow_data = json.loads(ARBEITNOW_FILE.read_text(encoding="utf-8"))
    assert isinstance(arbeitnow_data, list), "arbeitnow_offers.json debe ser una lista"
    assert len(arbeitnow_data) >= 1, "arbeitnow_offers.json debe tener al menos 1 oferta"

    # Generic
    assert GENERIC_FILE.exists(), f"{GENERIC_FILE} no existe"
    generic_data = json.loads(GENERIC_FILE.read_text(encoding="utf-8"))
    assert isinstance(generic_data, list), "generic_offers.json debe ser una lista"
    assert len(generic_data) >= 1, "generic_offers.json debe tener al menos 1 oferta"

    # Process request
    assert PROCESS_FILE.exists(), f"{PROCESS_FILE} no existe"
    process_data = json.loads(PROCESS_FILE.read_text(encoding="utf-8"))
    assert isinstance(process_data, dict), "process_request.json debe ser un dict"
    assert "sources" in process_data, "process_request.json debe tener clave 'sources'"
    assert len(process_data["sources"]) >= 2, (
        "process_request.json debe tener al menos 2 fuentes (arbeitnow + generic)"
    )


def test_process_request_aceptado_por_endpoint(api_client_with_cv) -> None:
    """El payload de examples/process_request.json es aceptado por POST /jobs/process.

    - El endpoint devuelve 200.
    - La respuesta tiene claves "results" y "errors".
    - LLM + embedder están mockeados (api_client_with_cv); cero llamadas a la red.
    """
    payload = json.loads(PROCESS_FILE.read_text(encoding="utf-8"))
    resp = api_client_with_cv.post("/jobs/process", json=payload)
    assert resp.status_code == 200, (
        f"POST /jobs/process devolvió {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "results" in body, f"Respuesta sin clave 'results': {body}"
    assert "errors" in body, f"Respuesta sin clave 'errors': {body}"
