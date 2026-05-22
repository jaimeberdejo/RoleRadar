"""
Tests para app/cv/llm_client.py.

Verifica:
1. extract_cv_profile devuelve un CVProfile tipado con los datos del mock.
2. extract_cv_profile pasa response_model=CVProfile, el modelo por defecto y max_retries=2
   al cliente inyectado.

NOTA: NO se llama a la fábrica de cliente real — eso construiría un cliente Anthropic real.
Solo se prueba extract_cv_profile con un mock inyectado.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.cv.llm_client import extract_cv_profile
from app.models.schemas import CVProfile, Experiencia

# Perfil de referencia determinista (misma forma que EXPECTED_PROFILE en conftest)
_MOCK_PROFILE = CVProfile(
    experiencia=[
        Experiencia(
            empresa="Acme Corp",
            rol="AI Engineer",
            duracion="2 años",
        )
    ],
    skills_tecnicas=["Python", "LLMs"],
    anios_experiencia_total=2.0,
    dominios=["IA"],
)


def _make_mock_client() -> MagicMock:
    """Construye un MagicMock que imita la superficie instructor.from_anthropic()."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _MOCK_PROFILE
    return mock_client


def test_returns_typed_cvprofile() -> None:
    """extract_cv_profile devuelve el CVProfile que el mock produce (tipado, no str)."""
    mock_client = _make_mock_client()

    result = extract_cv_profile("texto de cv", mock_client)

    assert isinstance(result, CVProfile), f"Se esperaba CVProfile, se obtuvo {type(result)}"
    assert result.skills_tecnicas == ["Python", "LLMs"]


def test_passes_response_model_and_model(monkeypatch) -> None:
    """extract_cv_profile pasa response_model=CVProfile, modelo por defecto y max_retries=2."""
    # Asegurar que ANTHROPIC_MODEL_CV no está definida para forzar el valor por defecto
    monkeypatch.delenv("ANTHROPIC_MODEL_CV", raising=False)
    mock_client = _make_mock_client()

    extract_cv_profile("texto de cv", mock_client)

    mock_client.messages.create.assert_called_once()
    kwargs = mock_client.messages.create.call_args.kwargs

    assert kwargs["response_model"] is CVProfile, (
        f"response_model debe ser CVProfile, se obtuvo {kwargs.get('response_model')}"
    )
    assert kwargs["model"] == "claude-haiku-4-5-20251001", (
        f"modelo por defecto incorrecto: {kwargs.get('model')}"
    )
    assert kwargs["max_retries"] == 2, (
        f"max_retries debe ser 2, se obtuvo {kwargs.get('max_retries')}"
    )
