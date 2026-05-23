"""Tests de los endpoints del router cv.

Cubre:
    - POST /cv/parse: happy path (PDF válido → CVProfile + _current escrito)
    - POST /cv/parse: el cliente inyectado vía Depends se usa realmente (CR-01)
    - POST /cv/parse: rechazo de ficheros que no son PDF (400)
    - POST /cv/parse: ValueError de parse_cv (PDF sin texto) → 400
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.api.deps import get_cv_llm_client
from app.api.main import app
from tests.conftest import EXPECTED_PROFILE


def test_parse_cv_ok(api_client, sample_pdf_bytes, tmp_path, monkeypatch):
    """POST /cv/parse con un PDF válido devuelve 200 y CVProfile con skills_tecnicas.

    Con la corrección CR-01, el cliente inyectado por Depends(get_cv_llm_client)
    se pasa a parse_cv() — el mock configurado en api_client es el que se usa.
    """
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))
    # No es necesario parchear build_instructor_client: el cliente inyectado
    # (mock_cv del fixture api_client) se usa directamente gracias a CR-01.
    response = api_client.post(
        "/cv/parse",
        files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200, f"Esperado 200, obtenido {response.status_code}: {response.text}"
    data = response.json()
    assert "skills_tecnicas" in data, "La respuesta debe contener 'skills_tecnicas'"


def test_parse_cv_escribe_current(api_client, sample_pdf_bytes, tmp_path, monkeypatch):
    """POST /cv/parse escribe el fichero _current en el directorio de caché."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))

    response = api_client.post(
        "/cv/parse",
        files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 200
    current_file = tmp_path / "_current"
    assert current_file.exists(), "_current debe existir tras /cv/parse"
    content_hash = current_file.read_text(encoding="utf-8").strip()
    assert len(content_hash) == 64, "_current debe contener un sha256 hexadecimal de 64 chars"


def test_parse_cv_usa_cliente_inyectado(sample_pdf_bytes, tmp_path, monkeypatch):
    """CR-01: el cliente inyectado vía Depends(get_cv_llm_client) llega a parse_cv.

    Sobreescribe get_cv_llm_client con un mock exclusivo para este test.
    Verifica que el mock ES LLAMADO cuando se sube un PDF (cache miss).
    Si la ruta no reenviara el cliente, el mock nunca se llamaría y el
    test fallaría con AssertionError en assert_called().
    """
    from fastapi.testclient import TestClient
    from app.api.deps import get_embedder, get_storage
    from app.dedup.embedder import FakeEmbedder
    import numpy as np

    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))

    mock_cv_client = MagicMock()
    mock_cv_client.messages.create.return_value = EXPECTED_PROFILE

    fake_embedder = FakeEmbedder(default_vector=np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32))

    # Storage mínimo (no se usa en /cv/parse pero lifespan lo requiere)
    class _MinStorage:
        def init_db(self) -> None:
            pass
        def upsert_scored_jobs(self, s): pass
        def was_seen(self, j): return False
        def get_history(self, limit=50, offset=0): return []

    app.dependency_overrides[get_cv_llm_client] = lambda: mock_cv_client
    app.dependency_overrides[get_embedder] = lambda: fake_embedder
    app.dependency_overrides[get_storage] = lambda: _MinStorage()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/cv/parse",
                files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")},
            )
        assert response.status_code == 200, response.text
        # El mock debe haber sido llamado por parse_cv — prueba que CR-01 está activo
        mock_cv_client.messages.create.assert_called()
    finally:
        app.dependency_overrides = {}


def test_parse_cv_rechaza_no_pdf(api_client):
    """POST /cv/parse con content_type text/plain devuelve 400."""
    response = api_client.post(
        "/cv/parse",
        files={"file": ("documento.txt", b"contenido de texto", "text/plain")},
    )
    assert response.status_code == 400, f"Esperado 400 para no-PDF, obtenido {response.status_code}"
    detail = response.json().get("detail", "")
    assert detail, "El mensaje de error no debe estar vacío"


def test_parse_cv_value_error_devuelve_422(api_client, tmp_path, monkeypatch):
    """POST /cv/parse cuando parse_cv lanza ValueError → CVParseError → 422 con envelope tipado.

    WR-02: la ruta mapea ValueError de parse_cv a CVParseError para que el handler tipado
    de main.py devuelva un envelope {"error": {"type": "CVParseError", ...}} consistente
    con el resto de errores de dominio, en lugar de un HTTPException 400 ad-hoc.
    """
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))

    # PDF mínimo que el extractor puede leer pero parse_cv lanza ValueError
    with patch("app.api.routes.cv.parse_cv", side_effect=ValueError("PDF sin texto extraíble")):
        response = api_client.post(
            "/cv/parse",
            files={"file": ("cv.pdf", b"%PDF-1.4 empty", "application/pdf")},
        )

    assert response.status_code == 422, f"Esperado 422 (CVParseError) para ValueError, obtenido {response.status_code}"
    body = response.json()
    assert "error" in body, "Respuesta debe contener envelope 'error'"
    assert body["error"]["type"] == "CVParseError"
    assert "PDF" in body["error"]["message"] or "sin texto" in body["error"]["message"].lower() or "extraíble" in body["error"]["message"]
