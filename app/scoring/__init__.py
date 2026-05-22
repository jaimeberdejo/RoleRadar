"""Módulo de scoring de ofertas (FASE 3).

Interfaz pública:
    score_job(job, cv_profile, user_profile, client=None) -> JobScore

CRÍTICO: NO importar app.dedup aquí ni transitivamente.
El scorer recibe Job objetos ya deduplicados (Fase 2).
Importar app.dedup arrastraría BGE-M3/torch a todos los tests de scoring
(Pitfall 7 de RESEARCH.md — haría los tests lentos 30s+ primera ejecución).
"""

from app.scoring.scorer import score_job

__all__ = ["score_job"]
