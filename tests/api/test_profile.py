"""Tests de GET /profile (API-02).

Verifica que el endpoint devuelve el UserProfile cargado desde data/profile.yaml.
"""
from __future__ import annotations


def test_get_profile_ok(api_client):
    """GET /profile → 200 con UserProfile que contiene datos_personales."""
    response = api_client.get("/profile")
    assert response.status_code == 200
    data = response.json()
    assert "datos_personales" in data, "El UserProfile debe contener datos_personales"


def test_get_profile_contiene_ranking(api_client):
    """GET /profile → ranking_puestos presente y no vacío."""
    response = api_client.get("/profile")
    assert response.status_code == 200
    data = response.json()
    assert "ranking_puestos" in data
    assert len(data["ranking_puestos"]) > 0, "El ranking de puestos no debe estar vacío"
