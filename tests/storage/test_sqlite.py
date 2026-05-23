"""Tests unitarios de SQLiteStorage — STORE-01, STORE-02, STORE-03.

Cubre:
    - STORE-01: backend SQLite local; ruta configurable vía SQLITE_DB_PATH.
    - STORE-02: persistencia con fecha (first_seen/last_seen); upsert preserva first_seen.
    - STORE-03: control de ya-vistas (was_seen); historial paginable.

Todos los tests usan una DB temporal en tmp_path — nunca tocan data/jobs.db.
"""
from __future__ import annotations

import time

import pytest

from app.models.schemas import (
    Desglose,
    Job,
    JobScore,
    Recommendation,
    RemoteJob,
    ScoredJob,
)
from app.storage import get_storage_backend
from app.storage.sqlite import SQLiteStorage


# ──────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _make_scored_job(job_id: str = "job-1") -> ScoredJob:
    """Construye un ScoredJob de prueba con valores deterministas."""
    job = Job(
        id=job_id,
        title="AI Engineer",
        company="TestCorp",
        location="Barcelona",
        remote=RemoteJob.remote,
        description="We build AI.",
        source="test",
    )
    score = JobScore(
        score_total=80,
        recommendation=Recommendation.good_fit,
        desglose=Desglose(
            encaje_puesto=90,
            encaje_skills=85,
            encaje_ubicacion=95,
            encaje_seniority=70,
        ),
        puesto_detectado="Ingeniero de IA / AI Engineer",
        rango_puesto=1,
        reasons_for=["Python match", "Remote disponible"],
        reasons_against=["Kubernetes no en CV"],
        matched_skills=["Python", "LLMs"],
        missing_requirements=["Kubernetes"],
        deal_breaker_hit=False,
        deal_breaker_cual=None,
    )
    return ScoredJob(job=job, score=score)


@pytest.fixture
def db(tmp_path):
    """Fixture: SQLiteStorage apuntando a una DB temporal en tmp_path."""
    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()
    return storage


# ──────────────────────────────────────────────────────────────────────────────
# STORE-03: was_seen
# ──────────────────────────────────────────────────────────────────────────────


def test_upsert_y_was_seen(db: SQLiteStorage) -> None:
    """was_seen False antes de insertar; True después del upsert. (STORE-03)"""
    assert db.was_seen("job-1") is False

    db.upsert_scored_jobs([_make_scored_job("job-1")])

    assert db.was_seen("job-1") is True


def test_was_seen_id_inexistente_devuelve_false(db: SQLiteStorage) -> None:
    """was_seen devuelve False para cualquier id no persistido."""
    db.upsert_scored_jobs([_make_scored_job("job-existe")])

    assert db.was_seen("job-no-existe") is False


# ──────────────────────────────────────────────────────────────────────────────
# STORE-02: upsert preserva first_seen (T-04-07)
# ──────────────────────────────────────────────────────────────────────────────


def test_upsert_preserva_first_seen(db: SQLiteStorage) -> None:
    """Segundo upsert del mismo id: first_seen NO cambia; last_seen SÍ cambia. (STORE-02)

    IN-03: se verifica AMBAS mitades del contrato STORE-02:
    - first_seen no se sobreescribe (ON CONFLICT lo preserva).
    - last_seen sí se actualiza (ON CONFLICT lo renueva).
    El sleep de 20 ms garantiza que el reloj del sistema avance lo suficiente.
    """
    db.upsert_scored_jobs([_make_scored_job("job-1")])
    first_seen_original = db.get_history()[0]["first_seen"]
    last_seen_after_first = db.get_history()[0]["last_seen"]

    # Esperar para que last_seen sea estrictamente posterior al primer upsert
    time.sleep(0.02)
    db.upsert_scored_jobs([_make_scored_job("job-1")])

    row = db.get_history()[0]
    assert row["first_seen"] == first_seen_original, (
        "ON CONFLICT no debe sobreescribir first_seen en el segundo upsert"
    )
    assert row["last_seen"] > last_seen_after_first, (
        "ON CONFLICT debe actualizar last_seen en el segundo upsert"
    )


# ──────────────────────────────────────────────────────────────────────────────
# STORE-02: get_history devuelve score y fechas
# ──────────────────────────────────────────────────────────────────────────────


def test_get_history_devuelve_score_y_fecha(db: SQLiteStorage) -> None:
    """get_history incluye score_total, recommendation, first_seen, last_seen y score (dict). (STORE-02)"""
    db.upsert_scored_jobs([_make_scored_job("job-1")])

    history = db.get_history()

    assert len(history) == 1
    row = history[0]
    assert row["id"] == "job-1"
    assert row["score_total"] == 80
    assert row["recommendation"] == Recommendation.good_fit.value
    assert "first_seen" in row and row["first_seen"]
    assert "last_seen" in row and row["last_seen"]
    assert isinstance(row["score"], dict)


# ──────────────────────────────────────────────────────────────────────────────
# STORE-03: paginación de get_history
# ──────────────────────────────────────────────────────────────────────────────


def test_get_history_paginacion(db: SQLiteStorage) -> None:
    """get_history(limit=2, offset=2) devuelve exactamente 2 resultados de 5. (STORE-03)"""
    scored_jobs = [_make_scored_job(f"job-{i}") for i in range(5)]
    db.upsert_scored_jobs(scored_jobs)

    page = db.get_history(limit=2, offset=2)

    assert len(page) == 2


def test_get_history_offset_fuera_de_rango(db: SQLiteStorage) -> None:
    """get_history con offset mayor al total de filas devuelve lista vacía."""
    db.upsert_scored_jobs([_make_scored_job("job-1")])

    page = db.get_history(limit=10, offset=100)

    assert page == []


# ──────────────────────────────────────────────────────────────────────────────
# Pitfall-6: round-trip Pydantic v2 de JobScore
# ──────────────────────────────────────────────────────────────────────────────


def test_score_json_roundtrip(db: SQLiteStorage) -> None:
    """El dict score del history reconstruye los campos del JobScore original. (Pitfall-6)"""
    original_score = _make_scored_job("job-1").score
    db.upsert_scored_jobs([_make_scored_job("job-1")])

    history = db.get_history()
    score_dict = history[0]["score"]

    assert score_dict["score_total"] == original_score.score_total
    assert score_dict["recommendation"] == original_score.recommendation.value
    assert score_dict["desglose"]["encaje_puesto"] == original_score.desglose.encaje_puesto
    assert score_dict["desglose"]["encaje_skills"] == original_score.desglose.encaje_skills
    # Verificar que el dict puede reconstruir un JobScore válido
    reconstructed = JobScore.model_validate(score_dict)
    assert reconstructed.score_total == original_score.score_total
    assert reconstructed.recommendation == original_score.recommendation


# ──────────────────────────────────────────────────────────────────────────────
# STORE-02: fila con score_json corrupto no rompe get_history
# ──────────────────────────────────────────────────────────────────────────────


def test_get_history_omite_fila_corrupta(db: SQLiteStorage, tmp_path) -> None:
    """Una fila con score_json corrupto se omite silenciosamente (log warning). (STORE-02)"""
    import sqlite3

    db.upsert_scored_jobs([_make_scored_job("job-bueno")])

    # Insertar directamente una fila con score_json inválido
    conn = sqlite3.connect(str(tmp_path / "test.db"))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        INSERT INTO jobs (id, title, company, score_total, recommendation, score_json,
                          first_seen, last_seen, seen)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), 0)
        """,
        ("job-corrupto", "Bad Job", "BadCorp", 0, "skip", "CORRUPTO_NO_JSON"),
    )
    conn.commit()
    conn.close()

    history = db.get_history()

    # Solo debe aparecer la fila válida
    ids = [row["id"] for row in history]
    assert "job-bueno" in ids
    assert "job-corrupto" not in ids


# ──────────────────────────────────────────────────────────────────────────────
# STORE-01: selección de backend por env
# ──────────────────────────────────────────────────────────────────────────────


def test_seleccion_sqlite_por_defecto(monkeypatch, tmp_path) -> None:
    """get_storage_backend devuelve SQLiteStorage local. (STORE-01)"""
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "backend_test.db"))

    backend = get_storage_backend()

    assert isinstance(backend, SQLiteStorage)


def test_seleccion_respeta_sqlite_db_path(monkeypatch, tmp_path) -> None:
    """get_storage_backend usa SQLITE_DB_PATH para ubicar el fichero. (STORE-01)"""
    db_file = tmp_path / "custom_path.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_file))

    backend = get_storage_backend()

    assert isinstance(backend, SQLiteStorage)
    assert db_file.exists()  # init_db() creó el fichero en la ruta configurada
