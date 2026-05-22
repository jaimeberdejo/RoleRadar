"""
Función de decaimiento lineal del ranking de puestos.

Responsabilidades:
  - encaje_puesto_desde_rango: convierte el rango de un puesto (decidido por el LLM)
    en un score de encaje_puesto (calculado por Python) mediante decay lineal.

Esta función es pura (stdlib only), sin dependencias externas.
Implementa SCORE-02: el ranking actúa como PESO graduado, no filtro binario.
Fuera de ranking (rango=None) devuelve el suelo > 0, nunca 0.

Parámetros configurables (defaults cubren el ranking de 4 puestos con paso=15):
  rango=1 → 100, rango=2 → 85, rango=3 → 70, rango=4 → 55
  rango alto (≥6) → 20 (suelo)
  rango=None → 20 (suelo, oferta fuera de ranking — no se descarta sola)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def encaje_puesto_desde_rango(
    rango: int | None,
    *,
    paso: int = 15,
    suelo: int = 20,
    maximo: int = 100,
) -> int:
    """Score de encaje_puesto a partir del rango del puesto (1-based).

    Fórmula: max(suelo, maximo - (rango - 1) * paso)

    Args:
        rango: Posición en el ranking de puestos (1 = máxima prioridad).
               None si la oferta está fuera del ranking.
        paso: Decremento por posición de ranking (por defecto 15).
        suelo: Score mínimo para ofertas con rango bajo o fuera de ranking
               (por defecto 20). Siempre > 0: no se descarta sola por rango.
        maximo: Score máximo para rango=1 (por defecto 100).

    Returns:
        Score entero entre suelo y maximo (ambos incluidos).

    Ejemplos con defaults (paso=15, suelo=20, maximo=100):
        rango=1  → 100
        rango=2  → 85
        rango=3  → 70
        rango=4  → 55
        rango=5  → 40
        rango=10 → 20  (suelo)
        rango=None → 20  (suelo, fuera de ranking — no se descarta sola)
    """
    if rango is None:
        return suelo
    score = maximo - (rango - 1) * paso
    return max(suelo, score)
