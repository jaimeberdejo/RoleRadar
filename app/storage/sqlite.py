"""Implementación SQLite de Storage para BuscadorDeEmpleo.

Usa stdlib sqlite3 (sin SQLAlchemy). Backend de persistencia local del
servicio. Configurable vía SQLITE_DB_PATH (default data/jobs.db).

Decisiones de diseño:
    - Conexión por llamada (_connect()): thread-safe con check_same_thread=False.
      FastAPI corre endpoints sync en un threadpool — una conexión compartida
      entre hilos requeriría locking explícito; conexión-por-llamada es más simple
      y suficiente para una herramienta personal de usuario único.
    - ON CONFLICT(id) DO UPDATE: upsert atómico que preserva first_seen.
      INSERT OR REPLACE borraría y reinserstaría (perdiría first_seen y seen).
    - score.model_dump_json() / JobScore.model_validate_json(): Pydantic v2 API
      — serializa enums correctamente; nunca .dict() ni .json() (v1 deprecado).
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import JobScore, ScoredJob

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Devuelve la hora actual UTC en formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


class SQLiteStorage:
    """Storage basado en sqlite3 stdlib. Implementa el Protocol Storage.

    Thread-safety: conexión-por-llamada con check_same_thread=False.
    No requiere init_db() si la tabla ya existe (CREATE TABLE IF NOT EXISTS).
    """

    def __init__(self, db_path: str = "data/jobs.db") -> None:
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Crea y devuelve una nueva conexión SQLite.

        check_same_thread=False: necesario porque FastAPI corre endpoints sync
        en un threadpool (cada request puede llegar desde un hilo distinto).
        Conexión-por-llamada es thread-safe a esta escala.
        """
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Crea la tabla jobs si no existe. Idempotente."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT,
                    remote TEXT,
                    url TEXT,
                    source TEXT,
                    score_total INTEGER,
                    recommendation TEXT,
                    score_json TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    seen INTEGER DEFAULT 0
                )
            """)
            conn.commit()
        logger.debug("SQLiteStorage.init_db: tabla jobs lista en %s", self._db_path)

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None:
        """Persiste (inserta o actualiza) una lista de ofertas puntuadas.

        Upsert atómico en una sola transacción: si el job ya existe actualiza
        last_seen, score_total, recommendation y score_json; si no, inserta.
        first_seen y seen (ya notificado) se preservan en el conflicto.
        """
        now = _now_iso()
        with self._connect() as conn:
            for item in scored:
                job, score = item.job, item.score
                conn.execute(
                    """
                    INSERT INTO jobs
                        (id, title, company, location, remote, url, source,
                         score_total, recommendation, score_json,
                         first_seen, last_seen, seen)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)
                    ON CONFLICT(id) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        score_total = excluded.score_total,
                        recommendation = excluded.recommendation,
                        score_json = excluded.score_json
                    """,
                    (
                        job.id,
                        job.title,
                        job.company,
                        job.location,
                        job.remote.value if job.remote else None,
                        job.url,
                        job.source,
                        score.score_total,
                        score.recommendation.value,
                        score.model_dump_json(),
                        now,
                        now,
                    ),
                )
            conn.commit()
        logger.info("upsert_scored_jobs: %d ofertas persistidas en %s", len(scored), self._db_path)

    def was_seen(self, job_id: str) -> bool:
        """Devuelve True si job_id ya fue persistido en un run anterior."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return row is not None

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Devuelve el historial de ofertas guardadas, ordenado por last_seen desc.

        Cada dict incluye campos básicos de la oferta + score deserializado.
        Filas con score_json corrupto se omiten con log de warning.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            try:
                score = JobScore.model_validate_json(row["score_json"])
                result.append({
                    "id": row["id"],
                    "title": row["title"],
                    "company": row["company"],
                    "score_total": row["score_total"],
                    "recommendation": row["recommendation"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "score": score.model_dump(),
                })
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error deserializando oferta %s del historial: %s",
                    row["id"],
                    exc,
                )
        return result
