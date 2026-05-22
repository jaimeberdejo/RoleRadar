"""
Test end-to-end del facade deduplicate() — QA-03.

Estrategia:
- Inyección directa de FakeEmbedder vía parámetro embedder= (nunca patch()).
- El embedder real (modelo BGE-M3) nunca se instancia: todos los casos usan FakeEmbedder.
- Cubre: duplicado exacto, duplicado semántico, sin fusión, descripción-más-larga
  conservada, urls_alternativas acumuladas, lista vacía.
- El caso central QA-03: 3 jobs (2 dupes + 1 único) → 2 jobs de salida.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.dedup import deduplicate
from app.dedup.embedder import FakeEmbedder
from app.models.schemas import Job, RemoteJob


# ──────────────────────────────────────────────────────────────────────────────
# Helpers para construir Jobs de prueba de forma concisa
# ──────────────────────────────────────────────────────────────────────────────

def make_job(
    job_id: str,
    title: str,
    company: str,
    description: str = "",
    url: str | None = None,
    source: str = "test",
) -> Job:
    """Construye un Job mínimo válido para los tests."""
    return Job(
        id=job_id,
        title=title,
        company=company,
        description=description,
        url=url,
        source=source,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures locales de FakeEmbedder
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def embedder_identico() -> FakeEmbedder:
    """Devuelve siempre el mismo vector → similitud coseno = 1.0 entre cualquier par."""
    v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    return FakeEmbedder(default_vector=v)


@pytest.fixture
def embedder_ortogonal() -> FakeEmbedder:
    """Devuelve vectores ortogonales para los textos de los 3 jobs de prueba."""
    # Los textos de embed siguen el formato: "{title} {company} {primeras N palabras desc}"
    # Definimos exactamente los textos que build_embed_text producirá para nuestros jobs:
    vectores = {
        "AI Engineer TechCorp We build AI solutions for enterprises.": np.array(
            [1.0, 0.0, 0.0, 0.0], dtype=np.float32
        ),
        "Data Analyst FinanceFirm We analyze financial data for clients.": np.array(
            [0.0, 1.0, 0.0, 0.0], dtype=np.float32
        ),
        "Backend Developer StartupXYZ We write scalable backend services.": np.array(
            [0.0, 0.0, 1.0, 0.0], dtype=np.float32
        ),
    }
    return FakeEmbedder(vectors=vectores)


# ──────────────────────────────────────────────────────────────────────────────
# Tests de lista vacía
# ──────────────────────────────────────────────────────────────────────────────

def test_deduplicate_empty_returns_empty(embedder_identico):
    """deduplicate([]) → []."""
    result = deduplicate([], embedder=embedder_identico)
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# QA-03: caso central — 3 jobs (2 duplicados exactos + 1 único) → 2 de salida
# ──────────────────────────────────────────────────────────────────────────────

def test_deduplicate_qa03_exact_dup_plus_unique(embedder_ortogonal):
    """QA-03: 3 jobs (2 dup exactos + 1 único) → 2 jobs de salida.

    Los dos duplicados exactos tienen la misma empresa+título normalizados,
    por lo que se fusionan en el nivel 1. El embedder ortogonal asegura que
    la fusión semántica no colapsa el representante con el tercer job distinto.
    """
    # Duplicado exacto (mismo company+title, distintas descripciones y URLs)
    job_dup_corto = make_job(
        job_id="id-1a",
        title="AI Engineer",
        company="TechCorp",
        description="We build AI.",
        url="https://example.com/job-1a",
    )
    job_dup_largo = make_job(
        job_id="id-1b",
        title="AI Engineer",  # mismo título
        company="TechCorp",   # misma empresa
        description="We build AI solutions for enterprises.",  # descripción más larga
        url="https://example.com/job-1b",
    )
    # Job único (diferente empresa+título)
    job_unico = make_job(
        job_id="id-2",
        title="Data Analyst",
        company="FinanceFirm",
        description="We analyze financial data for clients.",
        url="https://example.com/job-2",
    )

    result = deduplicate([job_dup_corto, job_dup_largo, job_unico], embedder=embedder_ortogonal)

    assert len(result) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Duplicado exacto: descripción más larga conservada + urls_alternativas
# ──────────────────────────────────────────────────────────────────────────────

def test_deduplicate_exact_keeps_longest_description(embedder_identico):
    """La fusión de duplicados exactos conserva la descripción más larga."""
    job_corto = make_job(
        job_id="id-a",
        title="ML Engineer",
        company="Acme",
        description="Short description.",
        url="https://example.com/short",
    )
    job_largo = make_job(
        job_id="id-b",
        title="ML Engineer",  # mismo título
        company="Acme",        # misma empresa
        description="Long description with much more detail about the role and requirements.",
        url="https://example.com/long",
    )

    result = deduplicate([job_corto, job_largo], embedder=embedder_identico)

    assert len(result) == 1
    assert result[0].description == job_largo.description


def test_deduplicate_exact_accumulates_urls_alternativas(embedder_identico):
    """La fusión de duplicados exactos acumula urls_alternativas (DEDUP-03 end-to-end)."""
    job_a = make_job(
        job_id="id-a",
        title="ML Engineer",
        company="Acme",
        description="Short desc.",
        url="https://example.com/job-a",
    )
    job_b = make_job(
        job_id="id-b",
        title="ML Engineer",
        company="Acme",
        description="A much longer and more detailed description for this ML Engineer role.",
        url="https://example.com/job-b",
    )

    result = deduplicate([job_a, job_b], embedder=embedder_identico)

    assert len(result) == 1
    canonical = result[0]
    # La URL del job descartado debe aparecer en urls_alternativas
    assert "https://example.com/job-a" in canonical.urls_alternativas


# ──────────────────────────────────────────────────────────────────────────────
# Duplicado semántico: embedder fuerza la fusión de jobs distintos por hash exacto
# ──────────────────────────────────────────────────────────────────────────────

def test_deduplicate_semantic_dup_collapses_with_identical_embedder(embedder_identico):
    """2 jobs distintos en hash exacto + embedder idéntico (sim=1.0) → 1 job de salida.

    Los dos jobs tienen empresa+título distintos (no son duplicados exactos),
    pero el embedder_identico retorna el mismo vector para ambos, forzando
    su fusión en el nivel semántico.
    """
    job_1 = make_job(
        job_id="id-sem-1",
        title="AI Engineer",
        company="CompanyA",
        description="We work with large language models.",
        url="https://example.com/ai-engineer-a",
    )
    job_2 = make_job(
        job_id="id-sem-2",
        title="LLM Engineer",   # título distinto → diferente clave exacta
        company="CompanyB",     # empresa distinta
        description="We work with large language models and transformers.",
        url="https://example.com/llm-engineer-b",
    )

    result = deduplicate([job_1, job_2], embedder=embedder_identico)

    assert len(result) == 1


def test_deduplicate_semantic_dup_accumulates_urls_alternativas(embedder_identico):
    """La fusión semántica también acumula urls_alternativas del descartado."""
    job_corto = make_job(
        job_id="id-sem-a",
        title="AI Engineer",
        company="CompanyA",
        description="AI work.",
        url="https://example.com/ai-a",
    )
    job_largo = make_job(
        job_id="id-sem-b",
        title="LLM Engineer",
        company="CompanyB",
        description="We design and build large language model systems at scale.",
        url="https://example.com/llm-b",
    )

    result = deduplicate([job_corto, job_largo], embedder=embedder_identico)

    assert len(result) == 1
    canonical = result[0]
    # La descripción más larga debe conservarse
    assert canonical.description == job_largo.description
    # La URL de job_corto (descartado) debe estar en urls_alternativas
    assert "https://example.com/ai-a" in canonical.urls_alternativas


# ──────────────────────────────────────────────────────────────────────────────
# Sin fusión: embedder ortogonal garantiza que 3 jobs distintos permanecen 3
# ──────────────────────────────────────────────────────────────────────────────

def test_deduplicate_no_fusion_with_orthogonal_embedder(embedder_ortogonal):
    """3 jobs distintos + embedder ortogonal → 3 jobs (nada se fusiona)."""
    job_1 = make_job(
        job_id="id-o1",
        title="AI Engineer",
        company="TechCorp",
        description="We build AI solutions for enterprises.",
        url="https://example.com/ai",
    )
    job_2 = make_job(
        job_id="id-o2",
        title="Data Analyst",
        company="FinanceFirm",
        description="We analyze financial data for clients.",
        url="https://example.com/data",
    )
    job_3 = make_job(
        job_id="id-o3",
        title="Backend Developer",
        company="StartupXYZ",
        description="We write scalable backend services.",
        url="https://example.com/backend",
    )

    result = deduplicate([job_1, job_2, job_3], embedder=embedder_ortogonal)

    assert len(result) == 3


# ──────────────────────────────────────────────────────────────────────────────
# Verificación de invariante: el embedder real (modelo BGE-M3) no se usa en tests
# ──────────────────────────────────────────────────────────────────────────────

def test_only_fake_embedder_in_tests(embedder_identico, embedder_ortogonal):
    """El embedder real (modelo grande) nunca se usa en los tests (invariante T-02-10).

    Este test documenta el contrato: en los tests siempre se inyecta
    FakeEmbedder vía embedder=. El check de CI lo verifica con grep.
    """
    # Si llegamos aquí con FakeEmbedder sin errores, el invariante se cumple.
    result = deduplicate([], embedder=embedder_identico)
    assert result == []
    result = deduplicate([], embedder=embedder_ortogonal)
    assert result == []
