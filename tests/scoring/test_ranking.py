"""
Tests de la función encaje_puesto_desde_rango (decay lineal del ranking).

Cubre SCORE-02: el ranking de puestos actúa como PESO graduado (no filtro binario).
- rango None → suelo > 0 (fuera de ranking no se descarta sola).
- rango 1 → máximo (100 por defecto).
- Monotonía estricta decreciente por posición de ranking.
"""
from __future__ import annotations

import pytest

from app.scoring.ranking import encaje_puesto_desde_rango


# ──────────────────────────────────────────────────────────────────────────────
# Valores exactos (tabla verificada: paso=15, suelo=20, maximo=100)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "rango, esperado",
    [
        (1, 100),
        (2, 85),
        (3, 70),
        (4, 55),
        (None, 20),
    ],
)
def test_valores_exactos(rango: int | None, esperado: int) -> None:
    """Tabla de valores exactos con defaults paso=15, suelo=20, maximo=100."""
    assert encaje_puesto_desde_rango(rango) == esperado


# ──────────────────────────────────────────────────────────────────────────────
# Monotonía: cada posición mayor devuelve un score menor o igual
# ──────────────────────────────────────────────────────────────────────────────

def test_monotonia() -> None:
    """El score es monotónico decreciente con el rango."""
    scores = [encaje_puesto_desde_rango(i) for i in range(1, 6)]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"No monotónico: rango {i+1} → {scores[i]}, rango {i+2} → {scores[i+1]}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Suelo > 0 para rango None (fuera de ranking no se descarta sola — SCORE-02)
# ──────────────────────────────────────────────────────────────────────────────

def test_suelo_mayor_que_cero() -> None:
    """Rango None devuelve suelo > 0 (oferta fuera de ranking no se descarta sola)."""
    resultado = encaje_puesto_desde_rango(None)
    assert resultado > 0, f"Suelo debe ser > 0, obtenido: {resultado}"


# ──────────────────────────────────────────────────────────────────────────────
# Suelo respetado para rangos muy altos
# ──────────────────────────────────────────────────────────────────────────────

def test_suelo_respetado_rango_alto() -> None:
    """Un rango muy alto (10) no puede bajar del suelo=20."""
    assert encaje_puesto_desde_rango(10) == 20


# ──────────────────────────────────────────────────────────────────────────────
# Parámetros configurables por keyword
# ──────────────────────────────────────────────────────────────────────────────

def test_parametros_configurables() -> None:
    """Los parámetros paso/suelo/maximo son configurables por keyword."""
    assert encaje_puesto_desde_rango(2, paso=20, maximo=100) == 80


def test_parametros_suelo_custom() -> None:
    """Un suelo custom se respeta cuando la fórmula caería por debajo."""
    assert encaje_puesto_desde_rango(10, paso=15, suelo=30, maximo=100) == 30


def test_maximo_custom() -> None:
    """El maximo custom determina el valor para rango=1."""
    assert encaje_puesto_desde_rango(1, maximo=80) == 80
