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

from app.models.schemas import (
    CVProfile,
    DatosPersonales,
    Experiencia,
    Job,
    LLMJobAssessment,
    ModalidadRemoto,
    PesosScoring,
    PreferenciaRemoto,
    PreferenciasUbicacion,
    PuestoRanking,
    RemoteJob,
    UserProfile,
)


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
    el mapper falle antes de llegar a Pydantic. Este payload se usa para
    verificar que una oferta mal formada va al campo `errors` del resultado de
    normalize_jobs() y NO tumba el batch completo (NORM-04).

    Por qué es inválido:
    - "company_name": 12345  → tipo int; unicodedata.normalize(int) lanza TypeError
      en normalize_field(), llamada desde stable_job_id() antes de que Pydantic valide.
    - "title": None          → normalize_field(None) también lanza TypeError.

    Returns:
        dict con valores de tipo incorrecto para provocar ValidationError.
    """
    return {
        "company_name": 12345,
        "title": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures de scoring (Phase 3 — Olas 1 y 2)
# Consumidas por tests/scoring/test_location.py y tests/scoring/test_scorer.py
# ──────────────────────────────────────────────────────────────────────────────

# Constante módulo: LLMJobAssessment controlado y honesto que el mock del LLM devuelve.
# Representa una oferta de AI Engineer con buen match en skills y seniority razonable.
EXPECTED_ASSESSMENT = LLMJobAssessment(
    razonamiento="El candidato tiene Python y LLMs; la oferta pide exactamente eso.",
    puesto_detectado="Ingeniero de IA / AI Engineer",
    rango_puesto=1,
    encaje_skills=85,
    encaje_seniority=70,
    matched_skills=["Python", "LLMs"],
    missing_requirements=[],
    reasons_for=["Match en skills principales"],
    reasons_against=["Requiere Kubernetes (no en CV)"],
    deal_breaker_hit_texto=False,
    deal_breaker_cual_texto=None,
)


def make_scoring_client(assessment: LLMJobAssessment) -> MagicMock:
    """Devuelve un MagicMock que imita la superficie instructor para scoring.

    Mismo patrón que mock_llm_client (líneas 67-77): .messages.create() devuelve
    el assessment controlado de forma determinista.

    Args:
        assessment: LLMJobAssessment que el mock debe devolver.

    Returns:
        MagicMock con .messages.create.return_value = assessment.
    """
    mock_client = MagicMock()
    mock_client.messages.create.return_value = assessment
    return mock_client


@pytest.fixture
def mock_scoring_client() -> MagicMock:
    """Fixture (function scope): cliente LLM mockeado que devuelve EXPECTED_ASSESSMENT.

    Consumido por tests/scoring/test_scorer.py y test_llm.py para aislar
    la capa LLM de los tests de la heurística determinista.
    """
    return make_scoring_client(EXPECTED_ASSESSMENT)


@pytest.fixture
def sample_cv_profile() -> CVProfile:
    """CVProfile mínimo de ejemplo para tests de scoring.

    Skills: Python, LLMs, FastAPI — alineadas con EXPECTED_ASSESSMENT.matched_skills.
    2 años de experiencia total como AI Engineer en Acme Corp.
    Consumido por tests/scoring/test_scorer.py y test_llm.py.
    """
    return CVProfile(
        experiencia=[
            Experiencia(
                empresa="Acme Corp",
                rol="AI Engineer",
                duracion="2 años",
                tecnologias=["Python", "LLMs"],
            )
        ],
        skills_tecnicas=["Python", "LLMs", "FastAPI"],
        anios_experiencia_total=2.0,
        dominios=["IA"],
    )


@pytest.fixture
def sample_user_profile() -> UserProfile:
    """UserProfile coherente con data/profile.yaml para tests de scoring.

    Configuración real de Jaime:
    - Ciudades preferidas: Barcelona; no dispuesto a reubicarse.
    - Modalidad ideal: remote; acepta onsite solo en Barcelona.
    - Ranking: 4 puestos reales con sinónimos.
    - Deal-breakers: exige 5+ años, presencial fuera de Barcelona.
    - Pesos por defecto (suman 1.0).

    Consumido por tests/scoring/test_location.py, test_scorer.py y test_loader.py.
    """
    return UserProfile(
        datos_personales=DatosPersonales(
            nombre="Jaime Berdejo",
            email="jaimeberdejo1902@gmail.com",
            ubicacion_actual="Barcelona, España",
        ),
        preferencias_ubicacion=PreferenciasUbicacion(
            ciudades_preferidas=["Barcelona"],
            pais="España",
            dispuesto_a_reubicarse=False,
        ),
        preferencia_remoto=PreferenciaRemoto(
            modalidad_ideal=ModalidadRemoto.remote,
            acepta_onsite_solo_en=["Barcelona"],
        ),
        ranking_puestos=[
            PuestoRanking(
                titulo="Ingeniero de IA / AI Engineer",
                sinonimos=["AI Engineer", "LLM Engineer", "GenAI Engineer"],
            ),
            PuestoRanking(
                titulo="Ingeniero de ML / ML Engineer",
                sinonimos=["ML Engineer", "Machine Learning Engineer"],
            ),
            PuestoRanking(
                titulo="Ingeniero de datos / Data Engineer",
                sinonimos=["Data Engineer"],
            ),
            PuestoRanking(
                titulo="MLOps Engineer",
                sinonimos=["MLOps", "ML Platform Engineer"],
            ),
        ],
        deal_breakers=[
            "exige 5+ años de experiencia",
            "presencial fuera de Barcelona",
        ],
        pesos=PesosScoring(),
    )


@pytest.fixture
def sample_job_remote() -> Job:
    """Oferta remota de AI Engineer.

    Cubre la rama: remote + modalidad_ideal=remote → encaje_ubicacion alto.
    Consumido por tests/scoring/test_location.py y test_scorer.py.
    """
    return Job(
        id="remote-ai-engineer-techcorp",
        title="AI Engineer",
        company="TechCorp",
        location="Remote",
        remote=RemoteJob.remote,
        description="We are looking for an AI Engineer with Python and LLMs experience.",
        source="test",
    )


@pytest.fixture
def sample_job_onsite_barcelona() -> Job:
    """Oferta presencial en Barcelona de AI Engineer.

    Cubre la rama: onsite + ciudad en acepta_onsite_solo_en → encaje_ubicacion alto.
    Consumido por tests/scoring/test_location.py y test_scorer.py.
    """
    return Job(
        id="onsite-ai-engineer-barcelona",
        title="AI Engineer",
        company="BarcelonaStartup",
        location="Barcelona, España",
        remote=RemoteJob.onsite,
        description="Buscamos AI Engineer para trabajar en nuestra oficina de Barcelona.",
        source="test",
    )


@pytest.fixture
def sample_job_onsite_madrid() -> Job:
    """Oferta presencial en Madrid de AI Engineer.

    Cubre la rama: onsite + ciudad NO en preferidas + dispuesto_a_reubicarse=False
    → encaje_ubicacion muy bajo + potencial deal-breaker de ubicación.
    Consumido por tests/scoring/test_location.py y test_scorer.py.
    """
    return Job(
        id="onsite-ai-engineer-madrid",
        title="AI Engineer",
        company="MadridCorp",
        location="Madrid, España",
        remote=RemoteJob.onsite,
        description="Buscamos AI Engineer para trabajar presencialmente en Madrid.",
        source="test",
    )


@pytest.fixture
def sample_job_fuera_ranking() -> Job:
    """Oferta remota de Frontend Designer (fuera del ranking de puestos).

    Cubre la rama: rango_puesto=None → encaje_puesto = suelo (no 0).
    Consumido por tests/scoring/test_scorer.py para verificar que ofertas
    fuera de ranking no se descartan automáticamente.
    """
    return Job(
        id="remote-frontend-designer",
        title="Frontend Designer",
        company="DesignAgency",
        location="Remote",
        remote=RemoteJob.remote,
        description="We are looking for a creative Frontend Designer with React skills.",
        source="test",
    )
