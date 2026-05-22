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


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures de dedup (Phase 2)
# NOTA: el import de FakeEmbedder es DEFERIDO dentro del cuerpo de cada fixture
# porque app/dedup/embedder.py se crea en Wave 1 (Plan 03). Un import a nivel de
# módulo rompería la colección de tests antes de que ese módulo exista.
# ──────────────────────────────────────────────────────────────────────────────

import numpy as np


@pytest.fixture
def fake_embedder_identico():
    """FakeEmbedder que devuelve siempre el mismo vector unidad para cualquier texto.

    Similitud coseno = 1.0 entre cualquier par → fuerza fusión semántica.
    Útil para verificar que dos ofertas similares SE fusionan cuando el embedder
    retorna vectores idénticos.

    Returns:
        FakeEmbedder configurado con default_vector=[1,0,0,0].
    """
    from app.dedup.embedder import FakeEmbedder  # import deferido — módulo creado en Plan 03

    vector_unidad = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    return FakeEmbedder(default_vector=vector_unidad)


@pytest.fixture
def fake_embedder_ortogonal():
    """FakeEmbedder con vectores ortogonales: similitud coseno = 0.0 entre pares distintos.

    El dict `vectors` mapea textos de embed a vectores ORTOGONALES entre sí.
    Verifica que ofertas distintas NO se fusionan con umbral 0.85.

    NOTA sobre las claves: el texto de embed que construye app/dedup/semantic.py
    sigue el formato ``f"{job.title} {job.company} {primeras N palabras desc}"``.
    Los tests de Plan 04 fijarán los textos exactos; este fixture provee vectores
    para los tres textos de ejemplo usados en los tests de dedup.

    Returns:
        FakeEmbedder configurado con vectores ortogonales por texto.
    """
    from app.dedup.embedder import FakeEmbedder  # import deferido — módulo creado en Plan 03

    vectores = {
        "AI Engineer TechCorp We build AI.": np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        "Data Analyst FinanceFirm We analyze data.": np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32),
        "Backend Developer StartupXYZ We write code.": np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32),
    }
    return FakeEmbedder(vectors=vectores)


@pytest.fixture
def sample_arbeitnow_payload() -> dict:
    """Payload de ejemplo con el shape real de Arbeitnow (campos verificados 2026-05-22).

    Campos: slug, company_name, title, description (HTML), remote (bool),
    url, tags (list[str]), job_types (list[str]), location (str), created_at (Unix int).
    Sin campo salary (no incluido en la API gratuita de Arbeitnow).

    Returns:
        dict con el formato que n8n enviaría al servicio tras llamar a Arbeitnow.
    """
    return {
        "slug": "ai-engineer-techcorp-12345",
        "company_name": "TechCorp GmbH",
        "title": "AI Engineer",
        "description": "<h2>About</h2><p>We build AI.</p>",
        "remote": False,
        "url": "https://www.arbeitnow.com/jobs/ai-engineer-techcorp-12345",
        "tags": ["Software Development", "Engineering"],
        "job_types": ["berufserfahren"],
        "location": "Berlin",
        "created_at": 1716350400,
    }


@pytest.fixture
def sample_generic_payload() -> dict:
    """Payload de ejemplo con nombres de campo de convención genérica distinta a Arbeitnow.

    Usa campos como "employer", "job_title", "city", "body", "apply_url", "is_remote"
    para ejercitar el generic_mapper (fuente desconocida o alternativa).

    Returns:
        dict con campos de convención genérica para tests del mapper de fallback.
    """
    return {
        "employer": "OpenAI Inc.",
        "job_title": "ML Engineer",
        "city": "San Francisco",
        "body": "We are looking for a motivated ML Engineer to join our team.",
        "apply_url": "https://openai.com/careers/ml-engineer",
        "is_remote": True,
    }


@pytest.fixture
def sample_malformed_payload() -> dict:
    """Payload inválido que provoca fallo de validación Pydantic en el mapper.

    Los valores de tipo incorrecto (company_name=entero, title=None) hacen que
    la validación de Job falle con ValidationError. Este payload se usa para
    verificar que una oferta mal formada va al campo `errors` del resultado de
    normalize_jobs() y NO tumba el batch completo (NORM-04).

    Por qué es inválido:
    - "company_name": 12345  → tipo int en lugar de str
    - "title": None          → campo requerido con valor nulo

    Returns:
        dict con valores de tipo incorrecto para provocar ValidationError.
    """
    return {
        "company_name": 12345,
        "title": None,
    }
