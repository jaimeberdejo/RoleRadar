"""
Fixtures compartidas para todos los tests de BuscadorDeEmpleo.

Expone:
- sample_pdf_bytes  (session scope): PDF mínimo con texto de CV conocido, generado
  en memoria con pymupdf. Usado por los tests de extractor, caché y parser.
- EXPECTED_PROFILE: constante CVProfile determinista que el mock del LLM devuelve.
- mock_llm_client   (function scope): MagicMock del cliente instructor (Anthropic).
  Su método .messages.create devuelve siempre EXPECTED_PROFILE.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pymupdf
import pytest

from app.models.schemas import CVProfile, Experiencia


# ──────────────────────────────────────────────────────────────────────────────
# Constante global: perfil esperado devuelto por el LLM mockeado
# ──────────────────────────────────────────────────────────────────────────────

EXPECTED_PROFILE = CVProfile(
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


# ──────────────────────────────────────────────────────────────────────────────
# Fixture: PDF mínimo con texto de CV conocido (sin dependencia de reportlab)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Genera un PDF mínimo con texto de CV conocido, en memoria (sin escritura a disco).

    El texto incluye literales conocidos ("AI Engineer", "Acme Corp", "Python", "LLMs")
    que los tests de extractor y parser pueden afirmar explícitamente.
    """
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Jaime Berdejo - AI Engineer\n"
        "Empresa: Acme Corp | Rol: AI Engineer | 2022-2024\n"
        "Skills: Python, LLMs, FastAPI\n"
        "Formación: Grado Informática, UPC, 2020\n",
        fontsize=12,
    )
    return doc.tobytes()


# ──────────────────────────────────────────────────────────────────────────────
# Fixture: cliente instructor mockeado (Anthropic surface)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Devuelve un MagicMock que imita la superficie de instructor.from_anthropic().

    El método .messages.create() devuelve EXPECTED_PROFILE de forma determinista,
    permitiendo que los tests de parser.py parcheen build_instructor_client sin
    realizar llamadas reales a la API de Anthropic.
    """
    mock_client = MagicMock()
    mock_client.messages.create.return_value = EXPECTED_PROFILE
    return mock_client
