"""
Evaluador determinista de ubicación/remoto para ofertas de empleo.

Responsabilidad única: mapear (Job.remote, Job.location) × UserProfile a
(encaje_ubicacion: int, deal_breaker_descripcion: str | None) usando reglas
booleanas puras sin LLM.

IMPORTANTE sobre imports:
  No importar app.dedup — arrastrarían BGE-M3/torch a los tests de scoring
  (Pitfall 7 de RESEARCH.md). El algoritmo NFD se replica localmente aquí;
  es trivial (stdlib only) y evita el acoplamiento transitivo con el pipeline
  de embeddings.

Mapa de decisión completo (RESEARCH Pattern 4, 8 ramas + unknown):
  remote + modal in (remote, hybrid, indiferente) → (100, None)
  remote + modal = onsite                         → (60, None)
  hybrid + ciudad aceptada                        → (80, None)
  hybrid + no aceptada + no reubicarse            → (10, deal_breaker str)
  hybrid + no aceptada + sí reubicarse            → (50, None)
  onsite + ciudad aceptada                        → (90, None)
  onsite + no aceptada + no reubicarse            → (10, deal_breaker str)
  onsite + no aceptada + sí reubicarse            → (40, None)
  unknown (o cualquier otro)                      → (50, None)

"Ciudades aceptadas" = ciudades_preferidas + acepta_onsite_solo_en (RESEARCH).
City matching: substring NFD normalizado (Pitfall 6 — "Barcelona, España"
matchea "Barcelona" porque se usa `c in loc` no igualdad exacta).
"""
from __future__ import annotations

import logging
import unicodedata

from app.models.schemas import Job, ModalidadRemoto, RemoteJob, UserProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers privados (stdlib pura, sin dependencias externas)
# ---------------------------------------------------------------------------

def _normalize_city(name: str) -> str:
    """Normaliza nombre de ciudad a minúsculas ASCII para comparación estable.

    Pasos:
    1. Descomposición NFD: separa base + combining marks (acentos).
    2. Filtrado de categoría "Mn" (Nonspacing_Mark = acentos, tildes, cedillas).
       Convención del proyecto: `category(c) != "Mn"` (idéntico a normalize.py).
    3. casefold + strip.

    Ejemplos:
        _normalize_city("Barcelona, España") → "barcelona, espana"
        _normalize_city("München") → "munchen"
        _normalize_city("  Málaga  ") → "malaga"
    """
    nfd = unicodedata.normalize("NFD", name.lower().strip())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _ciudad_aceptada(location: str | None, ciudades: list[str]) -> bool:
    """True si location normalizada CONTIENE alguna ciudad aceptada normalizada.

    Usa substring match (no igualdad exacta) para que "Barcelona, España"
    matchee "Barcelona" (Pitfall 6 de RESEARCH.md).

    Returns False de forma segura si location es None o vacío (T-03-06).
    """
    if not location:
        return False
    loc_norm = _normalize_city(location)
    return any(_normalize_city(c) in loc_norm for c in ciudades)


# ---------------------------------------------------------------------------
# Función pública
# ---------------------------------------------------------------------------

def evaluar_ubicacion(
    job: Job,
    profile: UserProfile,
) -> tuple[int, str | None]:
    """Evalúa el encaje de ubicación/remoto de una oferta contra el perfil del usuario.

    Devuelve (encaje_ubicacion, deal_breaker_descripcion | None).

    encaje_ubicacion: entero 0-100 calculado determinísticamente según las
    reglas del mapa de decisión (RESEARCH Pattern 4). Valores posibles:
    10, 40, 50, 60, 80, 90, 100 — nunca fuera de rango (T-03-07).

    deal_breaker_descripcion: str descriptivo si la ubicación activa un
    deal-breaker (onsite/hybrid fuera de ciudades aceptadas sin disposición
    a reubicarse), o None en todos los demás casos.

    Args:
        job:     Oferta normalizada con campos remote y location.
        profile: Perfil del usuario con preferencias de ubicación y remoto.

    Returns:
        Tupla (encaje: int, deal_breaker: str | None).
    """
    pref_ub = profile.preferencias_ubicacion
    pref_rem = profile.preferencia_remoto
    modal = pref_rem.modalidad_ideal
    reubicar = pref_ub.dispuesto_a_reubicarse

    # "Ciudades aceptadas" = ciudades_preferidas ∪ acepta_onsite_solo_en
    ciudades_aceptadas: list[str] = (
        pref_ub.ciudades_preferidas + pref_rem.acepta_onsite_solo_en
    )
    aceptada = _ciudad_aceptada(job.location, ciudades_aceptadas)

    # --- Ramas según Job.remote ---

    if job.remote == RemoteJob.remote:
        # Trabajo 100% remoto: encaja bien si el perfil acepta remoto;
        # incluso si prefiere onsite, el remoto sigue siendo flexible (60).
        if modal in (ModalidadRemoto.remote, ModalidadRemoto.hybrid, ModalidadRemoto.indiferente):
            encaje = 100
        else:  # modal == onsite
            encaje = 60
        logger.debug(
            "evaluar_ubicacion: remote job '%s' — modal=%s → encaje=%d",
            job.title,
            modal.value,
            encaje,
        )
        return (encaje, None)

    if job.remote == RemoteJob.hybrid:
        if aceptada:
            encaje, deal_breaker = 80, None
        elif not reubicar:
            encaje = 10
            deal_breaker = f"Trabajo híbrido fuera de ciudades aceptadas: {job.location}"
        else:
            encaje, deal_breaker = 50, None
        logger.debug(
            "evaluar_ubicacion: hybrid job '%s' location=%s aceptada=%s reubicar=%s → encaje=%d",
            job.title,
            job.location,
            aceptada,
            reubicar,
            encaje,
        )
        return (encaje, deal_breaker)

    if job.remote == RemoteJob.onsite:
        if aceptada:
            encaje, deal_breaker = 90, None
        elif not reubicar:
            encaje = 10
            deal_breaker = f"Presencial fuera de ciudades aceptadas: {job.location}"
        else:
            encaje, deal_breaker = 40, None
        logger.debug(
            "evaluar_ubicacion: onsite job '%s' location=%s aceptada=%s reubicar=%s → encaje=%d",
            job.title,
            job.location,
            aceptada,
            reubicar,
            encaje,
        )
        return (encaje, deal_breaker)

    # RemoteJob.unknown (o cualquier valor no gestionado) → neutro
    logger.debug(
        "evaluar_ubicacion: unknown remote='%s' job '%s' → encaje=50 (neutro)",
        job.remote,
        job.title,
    )
    return (50, None)
