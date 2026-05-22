"""
Tests para app/scoring/location.py — evaluar_ubicacion determinista.

Cubre las 8 ramas del mapa de decisión (RESEARCH Pattern 4) + casos de robustez:
  1. remote + modalidad_ideal=remote         → (100, None)
  2. remote + modalidad_ideal=hybrid         → (100, None)
  3. remote + modalidad_ideal=indiferente    → (100, None)
  4. remote + modalidad_ideal=onsite         → (60, None)
  5. onsite + ciudad aceptada (Barcelona)    → (90, None)
  6. onsite + "Barcelona, España" matchea    → (90, None)  [Pitfall 6 substring NFD]
  7. onsite + ciudad no aceptada + no reubicar → (10, str con "Madrid")
  8. onsite + ciudad no aceptada + sí reubicar → (40, None)
  9. hybrid + ciudad aceptada                → (80, None)
 10. hybrid + ciudad no aceptada + no reubicar → (10, str)
 11. hybrid + ciudad no aceptada + sí reubicar → (50, None)
 12. unknown → (50, None)
 13. location=None + onsite no aceptada → (10, str) — robustez T-03-06

Todos los tests verifican AMBOS valores de la tupla (encaje exacto + deal_breaker).
"""
from __future__ import annotations

import pytest

from app.models.schemas import (
    Job,
    ModalidadRemoto,
    PreferenciaRemoto,
    PreferenciasUbicacion,
    RemoteJob,
    UserProfile,
)
from app.scoring.location import evaluar_ubicacion


# ---------------------------------------------------------------------------
# Helpers para construir variantes del perfil sin duplicar toda la fixture
# ---------------------------------------------------------------------------

def _perfil_con_remoto(
    sample_user_profile: UserProfile,
    *,
    modalidad: ModalidadRemoto | None = None,
    dispuesto_a_reubicarse: bool | None = None,
) -> UserProfile:
    """Crea una copia del perfil con preferencias modificadas."""
    prefs_ub = sample_user_profile.preferencias_ubicacion
    pref_rem = sample_user_profile.preferencia_remoto

    if dispuesto_a_reubicarse is not None:
        prefs_ub = PreferenciasUbicacion(
            ciudades_preferidas=prefs_ub.ciudades_preferidas,
            pais=prefs_ub.pais,
            dispuesto_a_reubicarse=dispuesto_a_reubicarse,
        )

    if modalidad is not None:
        pref_rem = PreferenciaRemoto(
            modalidad_ideal=modalidad,
            acepta_onsite_solo_en=pref_rem.acepta_onsite_solo_en,
        )

    return sample_user_profile.model_copy(
        update={
            "preferencias_ubicacion": prefs_ub,
            "preferencia_remoto": pref_rem,
        }
    )


def _job(remote: RemoteJob, location: str | None = None) -> Job:
    """Construye un Job mínimo para test de ubicación."""
    return Job(
        id=f"test-{remote.value}-{location or 'noloc'}",
        title="AI Engineer",
        company="TestCorp",
        location=location,
        remote=remote,
        source="test",
    )


# ---------------------------------------------------------------------------
# Rama 1-3: remote + modalidad que permite remote
# ---------------------------------------------------------------------------

def test_remote_modalidad_remote(sample_user_profile: UserProfile) -> None:
    """remote + modalidad_ideal=remote → (100, None)."""
    job = _job(RemoteJob.remote, location="Remote")
    # sample_user_profile ya tiene modalidad_ideal=remote
    encaje, deal_breaker = evaluar_ubicacion(job, sample_user_profile)
    assert encaje == 100
    assert deal_breaker is None


def test_remote_modalidad_hybrid(sample_user_profile: UserProfile) -> None:
    """remote + modalidad_ideal=hybrid → (100, None)."""
    perfil = _perfil_con_remoto(sample_user_profile, modalidad=ModalidadRemoto.hybrid)
    job = _job(RemoteJob.remote, location="Remote")
    encaje, deal_breaker = evaluar_ubicacion(job, perfil)
    assert encaje == 100
    assert deal_breaker is None


def test_remote_modalidad_indiferente(sample_user_profile: UserProfile) -> None:
    """remote + modalidad_ideal=indiferente → (100, None)."""
    perfil = _perfil_con_remoto(
        sample_user_profile, modalidad=ModalidadRemoto.indiferente
    )
    job = _job(RemoteJob.remote, location="Remote")
    encaje, deal_breaker = evaluar_ubicacion(job, perfil)
    assert encaje == 100
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 4: remote + modalidad_ideal=onsite
# ---------------------------------------------------------------------------

def test_remote_modalidad_onsite(sample_user_profile: UserProfile) -> None:
    """remote + modalidad_ideal=onsite → (60, None). Remote es flexible aunque prefiera onsite."""
    perfil = _perfil_con_remoto(sample_user_profile, modalidad=ModalidadRemoto.onsite)
    job = _job(RemoteJob.remote, location="Remote")
    encaje, deal_breaker = evaluar_ubicacion(job, perfil)
    assert encaje == 60
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 5: onsite + ciudad aceptada (Barcelona exacto)
# ---------------------------------------------------------------------------

def test_onsite_ciudad_aceptada_barcelona(
    sample_user_profile: UserProfile,
    sample_job_onsite_barcelona: Job,
) -> None:
    """onsite + Barcelona en acepta_onsite_solo_en → (90, None)."""
    # sample_job_onsite_barcelona tiene location="Barcelona, España"
    encaje, deal_breaker = evaluar_ubicacion(
        sample_job_onsite_barcelona, sample_user_profile
    )
    assert encaje == 90
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 6 (Pitfall 6): substring NFD — "Barcelona, España" matchea "Barcelona"
# ---------------------------------------------------------------------------

def test_onsite_barcelona_espana_matchea_substring(
    sample_user_profile: UserProfile,
) -> None:
    """'Barcelona, España' matchea 'Barcelona' por substring NFD (Pitfall 6)."""
    job = _job(RemoteJob.onsite, location="Barcelona, España")
    encaje, deal_breaker = evaluar_ubicacion(job, sample_user_profile)
    assert encaje == 90, (
        f"Esperaba encaje=90 para 'Barcelona, España' pero obtuve {encaje}. "
        "Revisar _ciudad_aceptada: debe usar substring NFD, no igualdad exacta."
    )
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 7: onsite + ciudad no aceptada + no reubicarse
# ---------------------------------------------------------------------------

def test_onsite_ciudad_no_aceptada_no_reubicarse(
    sample_user_profile: UserProfile,
    sample_job_onsite_madrid: Job,
) -> None:
    """onsite + Madrid (no en preferidas) + dispuesto_a_reubicarse=False → (10, str con Madrid)."""
    # sample_user_profile ya tiene dispuesto_a_reubicarse=False
    encaje, deal_breaker = evaluar_ubicacion(
        sample_job_onsite_madrid, sample_user_profile
    )
    assert encaje == 10
    assert deal_breaker is not None
    assert "Madrid" in deal_breaker


# ---------------------------------------------------------------------------
# Rama 8: onsite + ciudad no aceptada + sí reubicarse
# ---------------------------------------------------------------------------

def test_onsite_ciudad_no_aceptada_si_reubicarse(
    sample_user_profile: UserProfile,
) -> None:
    """onsite + Madrid (no aceptada) + dispuesto_a_reubicarse=True → (40, None)."""
    perfil = _perfil_con_remoto(sample_user_profile, dispuesto_a_reubicarse=True)
    job = _job(RemoteJob.onsite, location="Madrid, España")
    encaje, deal_breaker = evaluar_ubicacion(job, perfil)
    assert encaje == 40
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 9: hybrid + ciudad aceptada
# ---------------------------------------------------------------------------

def test_hybrid_ciudad_aceptada(sample_user_profile: UserProfile) -> None:
    """hybrid + Barcelona (aceptada) → (80, None)."""
    job = _job(RemoteJob.hybrid, location="Barcelona")
    encaje, deal_breaker = evaluar_ubicacion(job, sample_user_profile)
    assert encaje == 80
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 10: hybrid + ciudad no aceptada + no reubicarse
# ---------------------------------------------------------------------------

def test_hybrid_ciudad_no_aceptada_no_reubicarse(
    sample_user_profile: UserProfile,
) -> None:
    """hybrid + Sevilla (no aceptada) + dispuesto_a_reubicarse=False → (10, str)."""
    job = _job(RemoteJob.hybrid, location="Sevilla")
    encaje, deal_breaker = evaluar_ubicacion(job, sample_user_profile)
    assert encaje == 10
    assert deal_breaker is not None
    assert "Sevilla" in deal_breaker


# ---------------------------------------------------------------------------
# Rama 11: hybrid + ciudad no aceptada + sí reubicarse
# ---------------------------------------------------------------------------

def test_hybrid_ciudad_no_aceptada_si_reubicarse(
    sample_user_profile: UserProfile,
) -> None:
    """hybrid + Sevilla (no aceptada) + dispuesto_a_reubicarse=True → (50, None)."""
    perfil = _perfil_con_remoto(sample_user_profile, dispuesto_a_reubicarse=True)
    job = _job(RemoteJob.hybrid, location="Sevilla")
    encaje, deal_breaker = evaluar_ubicacion(job, perfil)
    assert encaje == 50
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 12: unknown → neutro
# ---------------------------------------------------------------------------

def test_unknown_neutro(sample_user_profile: UserProfile) -> None:
    """unknown → (50, None) independientemente de la ubicación."""
    job = _job(RemoteJob.unknown, location=None)
    encaje, deal_breaker = evaluar_ubicacion(job, sample_user_profile)
    assert encaje == 50
    assert deal_breaker is None


# ---------------------------------------------------------------------------
# Rama 13: robustez — location=None con onsite ciudad no aceptada (T-03-06)
# ---------------------------------------------------------------------------

def test_onsite_location_none_no_crashea(sample_user_profile: UserProfile) -> None:
    """location=None + onsite no aceptada → (10, str) sin crash (T-03-06).

    _ciudad_aceptada debe retornar False si location es falsy.
    No debe lanzar TypeError al llamar a _normalize_city(None).
    """
    job = _job(RemoteJob.onsite, location=None)
    encaje, deal_breaker = evaluar_ubicacion(job, sample_user_profile)
    assert encaje == 10
    assert deal_breaker is not None
