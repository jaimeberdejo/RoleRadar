"""Implementación SQLite de Storage para BuscadorDeEmpleo.

Usa stdlib sqlite3 (sin SQLAlchemy). Backend de persistencia local del
servicio. Configurable vía SQLITE_DB_PATH (default data/jobs.db).

Decisiones de diseño:
    - Conexión por llamada (_connect()): thread-safe con check_same_thread=False.
      En v2.0 dos procesos (UI Streamlit + worker APScheduler) acceden a la misma
      DB. WAL mode permite lecturas concurrentes mientras hay un escritor.
      busy_timeout=5000 aplica en cada conexión (es un parámetro de conexión,
      no de la base de datos) — evita OperationalError inmediato en contención.
    - ON CONFLICT(id) DO UPDATE: upsert atómico que preserva first_seen.
      INSERT OR REPLACE borraría y reinserstaría (perdiría first_seen y seen).
    - score.model_dump_json() / JobScore.model_validate_json(): Pydantic v2 API
      — serializa enums correctamente; nunca .dict() ni .json() (v1 deprecado).
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
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
        """Crea y devuelve una nueva conexión SQLite con WAL + busy_timeout.

        journal_mode=WAL: database-level setting; persiste en el fichero tras la
            primera vez. Permite lecturas concurrentes mientras hay un escritor.
            En v2.0: UI Streamlit lee, worker APScheduler escribe — sin bloqueos.
        busy_timeout=5000: connection-level setting — se resetea a 0 en cada nueva
            conexión. DEBE aplicarse aquí, no solo en init_db().
            Espera hasta 5 segundos antes de lanzar OperationalError en lock contention.
        """
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def init_db(self) -> None:
        """Crea las tablas jobs y settings si no existen. Idempotente."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            with conn:  # commit/rollback automático
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
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key   TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
                _SETTING_DEFAULTS = {
                    "search_query": '"AI Engineer" OR "ML Engineer"',
                    "search_country": "ES",
                    "schedule_interval_hours": "6",
                    "dedup_threshold": "0.85",
                    "score_weight_puesto": "0.35",
                    "score_weight_skills": "0.30",
                    "score_weight_ubicacion": "0.20",
                    "score_weight_seniority": "0.15",
                    "notification_min_score": "70",
                    "notification_channel": "none",
                }
                conn.executemany(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    list(_SETTING_DEFAULTS.items()),
                )
        logger.debug(
            "SQLiteStorage.init_db: tablas jobs + settings listas en %s", self._db_path
        )

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None:
        """Persiste (inserta o actualiza) una lista de ofertas puntuadas.

        Upsert atómico en una sola transacción: si el job ya existe actualiza
        last_seen, score_total, recommendation y score_json; si no, inserta.
        first_seen y seen (ya notificado) se preservan en el conflicto.
        """
        now = _now_iso()
        with closing(self._connect()) as conn:
            with conn:  # commit/rollback automático (toda la lista en una transacción)
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
        logger.info("upsert_scored_jobs: %d ofertas persistidas en %s", len(scored), self._db_path)

    def was_seen(self, job_id: str) -> bool:
        """Devuelve True si job_id ya fue persistido en un run anterior."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
        return row is not None

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Devuelve el historial de ofertas guardadas, ordenado por last_seen desc.

        Cada dict incluye campos básicos de la oferta + score deserializado.
        Filas con score_json corrupto se omiten con log de warning.
        """
        with closing(self._connect()) as conn:
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

    def get_settings(self) -> dict[str, str]:
        """Devuelve todas las settings como {key: value_str}. Valores son strings.

        Llamado por el worker al inicio de cada run y por la UI para mostrar config.
        Los valores numéricos se devuelven como strings — el caller hace la conversión.
        """
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_setting(self, key: str, value: str) -> None:
        """Upsert de una setting. value debe ser un string (JSON-encoded si complejo).

        Usa ON CONFLICT(key) DO UPDATE para sobreescribir el valor existente.
        A diferencia de init_db() que usa INSERT OR IGNORE (no destruye valores ya
        configurados por el usuario), set_setting() siempre actualiza.
        Nunca borra otras claves — upsert atómico solo del par (key, value).
        """
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
