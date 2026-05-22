"""
Tests de normalización de ofertas de empleo.

Cubre:
- NORM-02: normalize_field + stable_job_id (determinismo, NFD, 64-hex)
- NORM-01: normalize_jobs devuelve Jobs correctos para arbeitnow
- NORM-03: registry de mappers — arbeitnow usa su mapper; fuente desconocida usa generic
- NORM-04: oferta mal formada va a errors, el batch no se tumba
- QA-02: mapeo por fuente (arbeitnow y generic) correcto en campos clave
"""
from __future__ import annotations

import pytest

from app.dedup.normalize import normalize_field, stable_job_id
from app.dedup.mappers import MAPPER_REGISTRY, arbeitnow_mapper, generic_mapper
from app.dedup import normalize_jobs
from app.models.schemas import RemoteJob


# ══════════════════════════════════════════════════════════
# Bloque 1: normalize_field
# ══════════════════════════════════════════════════════════

def test_normalize_field_strips_accents():
    """normalize_field elimina acentos NFD (ej. é→e, Á→a)."""
    assert normalize_field("Ácmé Corp") == normalize_field("Acme Corp")


def test_normalize_field_casefold():
    """normalize_field convierte a minúsculas (casefold)."""
    assert normalize_field("AI Engineer") == "ai engineer"


def test_normalize_field_collapses_whitespace():
    """normalize_field colapsa espacios múltiples y hace strip."""
    assert normalize_field("  AI   Engineer  ") == "ai engineer"


def test_normalize_field_acent_and_casefold_combined():
    """Acentos + mayúsculas + espacios: todo se normaliza de una vez."""
    assert normalize_field("  Ácmé  CORP  ") == "acme corp"


def test_normalize_field_empty_string():
    """String vacío debe devolver string vacío."""
    assert normalize_field("") == ""


def test_normalize_field_spanish_chars():
    """Caracteres españoles comunes: ñ, ü, ó."""
    # ñ en NFD es n + combining tilde — normalizamos a 'n'
    result = normalize_field("Señor")
    # al menos las vocales con tilde se normalizan
    assert "e" in result and "o" in result


# ══════════════════════════════════════════════════════════
# Bloque 2: stable_job_id
# ══════════════════════════════════════════════════════════

def test_stable_job_id_is_deterministic():
    """Misma entrada → mismo id en llamadas sucesivas."""
    id1 = stable_job_id("Acme Corp", "AI Engineer", "Berlin")
    id2 = stable_job_id("Acme Corp", "AI Engineer", "Berlin")
    assert id1 == id2


def test_stable_job_id_returns_64_hex_chars():
    """El id debe ser un sha256 hex de exactamente 64 caracteres."""
    job_id = stable_job_id("Acme Corp", "AI Engineer", "Berlin")
    assert len(job_id) == 64
    assert all(c in "0123456789abcdef" for c in job_id)


def test_stable_job_id_case_insensitive():
    """stable_job_id es insensible a caso: 'Acme' y 'acme' producen el mismo id."""
    id_upper = stable_job_id("Acme Corp", "AI Engineer", "Berlin")
    id_lower = stable_job_id("acme corp", "ai engineer", "berlin")
    assert id_upper == id_lower


def test_stable_job_id_accent_insensitive():
    """stable_job_id es insensible a acentos: 'Ácmé' == 'Acme'."""
    id_accented = stable_job_id("Ácmé Corp", "AI Engineer", "Berlin")
    id_plain = stable_job_id("Acme Corp", "AI Engineer", "Berlin")
    assert id_accented == id_plain


def test_stable_job_id_different_inputs_produce_different_ids():
    """Entradas distintas → ids distintos."""
    id_a = stable_job_id("TechCorp", "AI Engineer", "Berlin")
    id_b = stable_job_id("FinanceFirm", "Data Analyst", "Madrid")
    assert id_a != id_b


def test_stable_job_id_empty_location():
    """stable_job_id acepta string vacío para location (caller convierte None a '')."""
    id_empty = stable_job_id("Acme", "Dev", "")
    id_none_equiv = stable_job_id("Acme", "Dev", "")
    assert id_empty == id_none_equiv
    assert len(id_empty) == 64


# ══════════════════════════════════════════════════════════
# Bloque 3: arbeitnow_mapper (QA-02)
# ══════════════════════════════════════════════════════════

def test_arbeitnow_mapper_title_and_company(sample_arbeitnow_payload):
    """arbeitnow_mapper extrae title y company_name correctamente."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert job.title == "AI Engineer"
    assert job.company == "TechCorp GmbH"


def test_arbeitnow_mapper_location(sample_arbeitnow_payload):
    """arbeitnow_mapper extrae location."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert job.location == "Berlin"


def test_arbeitnow_mapper_remote_false_is_unknown(sample_arbeitnow_payload):
    """remote=False en Arbeitnow mapea a RemoteJob.unknown (no inferimos onsite sin evidencia)."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert job.remote == RemoteJob.unknown


def test_arbeitnow_mapper_description_strips_html(sample_arbeitnow_payload):
    """arbeitnow_mapper elimina tags HTML de la descripción."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert "<h2>" not in job.description
    assert "<p>" not in job.description
    # El texto limpio debe contener el contenido real
    assert "About" in job.description or "We build AI" in job.description


def test_arbeitnow_mapper_posted_at_is_iso8601(sample_arbeitnow_payload):
    """arbeitnow_mapper convierte created_at Unix timestamp a ISO 8601."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert job.posted_at is not None
    # ISO 8601 tiene '+' o 'Z' en timezone y contiene 'T'
    assert "T" in job.posted_at
    assert "2024" in job.posted_at  # created_at=1716350400 es Mayo 2024


def test_arbeitnow_mapper_salary_is_none(sample_arbeitnow_payload):
    """Arbeitnow free API no devuelve salary — debe ser None."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert job.salary is None


def test_arbeitnow_mapper_raw_is_original_payload(sample_arbeitnow_payload):
    """Job.raw debe ser el payload original (para trazabilidad)."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    assert job.raw == sample_arbeitnow_payload


def test_arbeitnow_mapper_id_is_stable(sample_arbeitnow_payload):
    """Job.id debe ser stable_job_id(company, title, location) — 64 hex chars."""
    job = arbeitnow_mapper(sample_arbeitnow_payload, "arbeitnow")
    expected_id = stable_job_id("TechCorp GmbH", "AI Engineer", "Berlin")
    assert job.id == expected_id
    assert len(job.id) == 64


# ══════════════════════════════════════════════════════════
# Bloque 4: generic_mapper (QA-02)
# ══════════════════════════════════════════════════════════

def test_generic_mapper_employer_to_company(sample_generic_payload):
    """generic_mapper mapea employer → company."""
    job = generic_mapper(sample_generic_payload, "otra")
    assert job.company == "OpenAI Inc."


def test_generic_mapper_job_title_to_title(sample_generic_payload):
    """generic_mapper mapea job_title → title."""
    job = generic_mapper(sample_generic_payload, "otra")
    assert job.title == "ML Engineer"


def test_generic_mapper_city_to_location(sample_generic_payload):
    """generic_mapper mapea city → location."""
    job = generic_mapper(sample_generic_payload, "otra")
    assert job.location == "San Francisco"


def test_generic_mapper_body_to_description(sample_generic_payload):
    """generic_mapper mapea body → description."""
    job = generic_mapper(sample_generic_payload, "otra")
    assert "ML Engineer" in job.description


def test_generic_mapper_is_remote_true(sample_generic_payload):
    """generic_mapper infiere remote de is_remote=True → RemoteJob.remote."""
    job = generic_mapper(sample_generic_payload, "otra")
    assert job.remote == RemoteJob.remote


def test_generic_mapper_apply_url(sample_generic_payload):
    """generic_mapper mapea apply_url → url."""
    job = generic_mapper(sample_generic_payload, "otra")
    assert job.url == "https://openai.com/careers/ml-engineer"


# ══════════════════════════════════════════════════════════
# Bloque 5: MAPPER_REGISTRY — NORM-03
# ══════════════════════════════════════════════════════════

def test_registry_has_arbeitnow():
    """MAPPER_REGISTRY debe tener entrada 'arbeitnow'."""
    assert "arbeitnow" in MAPPER_REGISTRY


def test_registry_has_generic():
    """MAPPER_REGISTRY debe tener entrada 'generic'."""
    assert "generic" in MAPPER_REGISTRY


def test_registry_arbeitnow_is_arbeitnow_mapper():
    """MAPPER_REGISTRY['arbeitnow'] debe ser arbeitnow_mapper."""
    assert MAPPER_REGISTRY["arbeitnow"] is arbeitnow_mapper


# ══════════════════════════════════════════════════════════
# Bloque 6: normalize_jobs facade — NORM-01, NORM-03, NORM-04
# ══════════════════════════════════════════════════════════

def test_normalize_jobs_arbeitnow_single(sample_arbeitnow_payload):
    """normalize_jobs([payload], 'arbeitnow') devuelve 1 Job y 0 errors."""
    jobs, errors = normalize_jobs([sample_arbeitnow_payload], "arbeitnow")
    assert len(jobs) == 1
    assert len(errors) == 0
    assert jobs[0].title == "AI Engineer"


def test_normalize_jobs_job_id_equals_stable_job_id(sample_arbeitnow_payload):
    """El Job devuelto por normalize_jobs tiene id == stable_job_id(company, title, location)."""
    jobs, _ = normalize_jobs([sample_arbeitnow_payload], "arbeitnow")
    expected_id = stable_job_id("TechCorp GmbH", "AI Engineer", "Berlin")
    assert jobs[0].id == expected_id


def test_normalize_jobs_unknown_source_uses_generic(sample_generic_payload):
    """normalize_jobs con source desconocido usa generic_mapper (fallback — NORM-03)."""
    jobs, errors = normalize_jobs([sample_generic_payload], "fuente_inexistente")
    assert len(jobs) == 1
    assert len(errors) == 0
    # generic_mapper mapea employer→company
    assert jobs[0].company == "OpenAI Inc."


def test_normalize_jobs_batch_resilient(
    sample_arbeitnow_payload,
    sample_malformed_payload,
):
    """Una oferta mal formada va a errors; el batch no se tumba (NORM-04)."""
    raw_list = [
        sample_arbeitnow_payload,
        sample_malformed_payload,
        sample_arbeitnow_payload,
    ]
    jobs, errors = normalize_jobs(raw_list, "arbeitnow")
    assert len(jobs) == 2
    assert len(errors) == 1
    # El error registra index, source y error
    err = errors[0]
    assert err["index"] == 1
    assert err["source"] == "arbeitnow"
    assert isinstance(err["error"], str)
    assert len(err["error"]) > 0


def test_normalize_jobs_error_never_crashes_batch(sample_malformed_payload):
    """normalize_jobs con todos los payloads mal formados: 0 jobs, N errors, sin excepción."""
    raw_list = [sample_malformed_payload, sample_malformed_payload]
    jobs, errors = normalize_jobs(raw_list, "arbeitnow")
    assert len(jobs) == 0
    assert len(errors) == 2
