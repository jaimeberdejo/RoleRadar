"""Tests de los endpoints del router cv.

Cubre:
    - POST /cv/parse: happy path (PDF válido → CVProfile + _current escrito)
    - POST /cv/parse: rechazo de ficheros que no son PDF (400)
    - POST /cv/parse: ValueError de parse_cv (PDF sin texto) → 400
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import EXPECTED_PROFILE


def test_parse_cv_ok(api_client, sample_pdf_bytes, tmp_path, monkeypatch):
    """POST /cv/parse con un PDF válido devuelve 200 y CVProfile con skills_tecnicas."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))

    with patch("app.cv.parser.build_instructor_client") as mock_builder:
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_client.messages.create.return_value = EXPECTED_PROFILE
        mock_builder.return_value = mock_client

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

    with patch("app.cv.parser.build_instructor_client") as mock_builder:
        from unittest.mock import MagicMock
        mock_client = MagicMock()
        mock_client.messages.create.return_value = EXPECTED_PROFILE
        mock_builder.return_value = mock_client

        response = api_client.post(
            "/cv/parse",
            files={"file": ("cv.pdf", sample_pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    current_file = tmp_path / "_current"
    assert current_file.exists(), "_current debe existir tras /cv/parse"
    content_hash = current_file.read_text(encoding="utf-8").strip()
    assert len(content_hash) == 64, "_current debe contener un sha256 hexadecimal de 64 chars"


def test_parse_cv_rechaza_no_pdf(api_client):
    """POST /cv/parse con content_type text/plain devuelve 400."""
    response = api_client.post(
        "/cv/parse",
        files={"file": ("documento.txt", b"contenido de texto", "text/plain")},
    )
    assert response.status_code == 400, f"Esperado 400 para no-PDF, obtenido {response.status_code}"
    detail = response.json().get("detail", "")
    assert detail, "El mensaje de error no debe estar vacío"


def test_parse_cv_value_error_devuelve_400(api_client, tmp_path, monkeypatch):
    """POST /cv/parse cuando parse_cv lanza ValueError → 400 con el mensaje de la excepción."""
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path))

    # PDF mínimo que el extractor puede leer pero parse_cv lanza ValueError
    with patch("app.api.routes.cv.parse_cv", side_effect=ValueError("PDF sin texto extraíble")):
        response = api_client.post(
            "/cv/parse",
            files={"file": ("cv.pdf", b"%PDF-1.4 empty", "application/pdf")},
        )

    assert response.status_code == 400, f"Esperado 400 para ValueError, obtenido {response.status_code}"
    detail = response.json().get("detail", "")
    assert "PDF" in detail or "sin texto" in detail.lower() or "extraíble" in detail
