"""
QA-01 — Tests de aceptación para parse_cv (parser.py).

Validan el flujo end-to-end del orquestador:
  CV-01/CV-02: parse_cv devuelve un CVProfile tipado con los campos esperados.
  CV-03:       la segunda llamada con el mismo PDF usa la caché y NO llama al LLM.

Aislamiento:
  - CV_CACHE_DIR se redirige a tmp_path (evita contaminar data/.cache real).
  - OPENAI_API_KEY se fija a "test-key" (evita error de clave ausente al
    construir el cliente si algún path llega a invocar build_instructor_client real).
  - build_instructor_client se parchea en su import-site (app.cv.parser) para que
    el mock_llm_client sea el cliente inyectado — sin llamadas reales a OpenAI.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.cv.parser import parse_cv
from app.models.schemas import CVProfile
from tests.conftest import EXPECTED_PROFILE


def test_parse_cv_returns_cv_profile(
    sample_pdf_bytes: bytes,
    mock_llm_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """CV-01/CV-02: parse_cv devuelve un CVProfile con los campos esperados.

    Verifica que el orquestador convierte los bytes del PDF de ejemplo en un
    CVProfile tipado cuyo campo skills_tecnicas coincide con el perfil del mock.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))

    with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
        result = parse_cv(sample_pdf_bytes)

    assert isinstance(result, CVProfile)
    assert result.skills_tecnicas == ["Python", "LLMs"]


def test_cache_avoids_second_llm_call(
    sample_pdf_bytes: bytes,
    mock_llm_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """CV-03: la segunda llamada con el mismo PDF se sirve desde caché (LLM = 1 vez).

    Llama a parse_cv dos veces con los mismos bytes dentro del mismo bloque de patch.
    El LLM debe invocarse exactamente una vez: la primera llamada lo usa y guarda en
    caché; la segunda lo omite porque el hash ya existe en CV_CACHE_DIR.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))

    with patch("app.cv.parser.build_instructor_client", return_value=mock_llm_client):
        first_result = parse_cv(sample_pdf_bytes)
        second_result = parse_cv(sample_pdf_bytes)

    assert mock_llm_client.chat.completions.create.call_count == 1
    assert first_result.skills_tecnicas == second_result.skills_tecnicas


def test_parse_cv_raises_for_invalid_pdf(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """IN-03: parse_cv lanza ValueError para bytes que no son un PDF válido.

    Verifica el contrato documentado en el docstring de parse_cv: bytes no-PDF
    no deben producir una excepción pymupdf raw, sino un ValueError limpio.
    """
    monkeypatch.setenv("CV_CACHE_DIR", str(tmp_path / ".cache"))
    with pytest.raises(ValueError):
        parse_cv(b"not a pdf")
