"""Tests de autenticación por cabecera X-API-Key (task 260524-sg6).

Dos modos de operación cubiertos:

  Modo A — auth DESACTIVADA (API_KEY no configurada, entorno por defecto en tests):
    Las peticiones pasan sin cabecera y sin código 401.

  Modo B — auth ACTIVADA (API_KEY configurada vía monkeypatch.setenv):
    - Sin cabecera → 401 con envelope {"error": {"type": "Unauthorized", ...}}
    - Cabecera incorrecta → 401 (mismo mensaje, no se distingue de sin cabecera)
    - Cabecera correcta → no 401 (200 o 404 según si el recurso existe)
    - GET /health → siempre 200 (ruta pública, exenta de auth)
    - GET /docs, GET /openapi.json → 401 sin cabecera (middleware cubre Swagger)

Fixture: `api_client` de tests/api/conftest.py (ya sobreescribe todas las deps).
Env isolation: monkeypatch de pytest limpia API_KEY al finalizar cada test
(scope function, automático). No se usa módulo-scope para evitar contaminación.
"""
from __future__ import annotations


# ─── Modo A: Auth desactivada (API_KEY ausente) ───────────────────────────────

def test_auth_disabled_no_header(api_client):
    """Sin API_KEY en el entorno, GET /profile sin cabecera → no es 401."""
    response = api_client.get("/profile")
    assert response.status_code != 401, (
        f"Expected non-401 when API_KEY unset, got {response.status_code}"
    )


def test_auth_disabled_with_header(api_client):
    """Sin API_KEY en el entorno, cualquier cabecera → no es 401."""
    response = api_client.get("/profile", headers={"X-API-Key": "cualquier-valor"})
    assert response.status_code != 401


def test_health_always_public_when_disabled(api_client):
    """GET /health → 200 cuando API_KEY no está configurada."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ─── Modo B: Auth activada (API_KEY configurada) ──────────────────────────────

def test_auth_enforced_no_header(api_client, monkeypatch):
    """Con API_KEY, GET /profile sin X-API-Key → 401 con envelope correcto."""
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    response = api_client.get("/profile")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["type"] == "Unauthorized"
    assert "Invalid or missing API key" in data["error"]["message"]


def test_auth_enforced_wrong_key(api_client, monkeypatch):
    """Con API_KEY, clave incorrecta → 401 (mismo body que sin cabecera)."""
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    response = api_client.get("/profile", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["type"] == "Unauthorized"


def test_auth_enforced_correct_key(api_client, monkeypatch):
    """Con API_KEY, clave correcta → no es 401 (200 o 404 según el recurso)."""
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    response = api_client.get("/profile", headers={"X-API-Key": "test-secret-abc123"})
    assert response.status_code != 401, (
        f"Correct key should pass auth, got {response.status_code}"
    )


def test_health_exempt_when_enforced(api_client, monkeypatch):
    """Con API_KEY, GET /health sin cabecera → 200 (ruta pública exenta)."""
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_protected_when_enforced(api_client, monkeypatch):
    """Con API_KEY, GET /docs sin cabecera → 401 (Swagger UI protegida)."""
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    response = api_client.get("/docs")
    assert response.status_code == 401


def test_openapi_protected_when_enforced(api_client, monkeypatch):
    """Con API_KEY, GET /openapi.json sin cabecera → 401 (schema protegido)."""
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    response = api_client.get("/openapi.json")
    assert response.status_code == 401


def test_auth_response_no_distinction(api_client, monkeypatch):
    """Cabecera ausente y cabecera incorrecta devuelven exactamente el mismo body.

    Anti information disclosure: el cliente no puede saber si falló por ausencia
    o por valor incorrecto de la clave.
    """
    monkeypatch.setenv("API_KEY", "test-secret-abc123")
    r_missing = api_client.get("/profile")
    r_wrong = api_client.get("/profile", headers={"X-API-Key": "bad"})
    assert r_missing.status_code == r_wrong.status_code == 401
    assert r_missing.json() == r_wrong.json()
