"""Settings page (UI-05 + UI-06) — scoring weights, deal-breakers, threshold, channel status.

Page body is gated behind streamlit.runtime.exists() so importing this module
under pytest does not require a running Streamlit runtime (D-12 pattern).

Security:
  - Secrets are NEVER displayed as values. channel_status() returns booleans only
    (T-10-06-01). The page calls channel_status() and renders ✓/✗ — it never reads
    TELEGRAM_BOT_TOKEN, SMTP_PASSWORD, or OPENAI_API_KEY directly.
  - Weights go through validate_and_pack_weights() (runs PesosScoring validator)
    BEFORE any set_setting() call (T-10-06-02). Invalid weights block the save.

Persistence keys written to the settings table:
  score_weight_puesto, score_weight_skills, score_weight_ubicacion,
  score_weight_seniority, notification_min_score, deal_breakers (JSON list),
  notification_channel.
"""
from __future__ import annotations

import json

from ui.settings_logic import channel_status, pack_deal_breakers, validate_and_pack_weights


def _to_float(s, default: float) -> float:
    """Safely coerce a persisted setting string to float (WR-03).

    settings.get(key, default) only applies the default when the KEY is absent.
    A present-but-malformed value (empty string, "none", partial write) would
    crash float(). This helper falls back to `default` instead of raising, so a
    bad persisted value can never blank out the whole Settings page.
    """
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def _to_int(s, default: int) -> int:
    """Safely coerce a persisted setting string to int (WR-03). See _to_float."""
    try:
        return int(s)
    except (TypeError, ValueError):
        return default


def _render() -> None:
    """Streamlit page body for Settings (UI-05 + UI-06)."""
    import streamlit as st

    from ui.services import get_storage

    st.header("Configuración")

    storage = get_storage()
    settings = storage.get_settings()

    # ── Scoring weights (UI-05) ───────────────────────────────────────────
    st.subheader("Pesos de puntuación")
    st.caption(
        "Los cuatro pesos deben sumar 1.0. "
        "Cambiarlos afecta al worker y a «↻ Re-score»."
    )

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        peso_puesto = st.number_input(
            "Puesto",
            value=_to_float(settings.get("score_weight_puesto"), 0.35),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            format="%.2f",
            key="weight_puesto",
        )
    with col2:
        peso_skills = st.number_input(
            "Skills",
            value=_to_float(settings.get("score_weight_skills"), 0.30),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            format="%.2f",
            key="weight_skills",
        )
    with col3:
        peso_ubicacion = st.number_input(
            "Ubicación",
            value=_to_float(settings.get("score_weight_ubicacion"), 0.20),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            format="%.2f",
            key="weight_ubicacion",
        )
    with col4:
        peso_seniority = st.number_input(
            "Seniority",
            value=_to_float(settings.get("score_weight_seniority"), 0.15),
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            format="%.2f",
            key="weight_seniority",
        )

    if st.button("Guardar pesos", type="primary"):
        ok, payload = validate_and_pack_weights(
            peso_puesto, peso_skills, peso_ubicacion, peso_seniority
        )
        if not ok:
            # payload is the Spanish error message (T-10-06-02 / D-08)
            st.error(payload)
        else:
            # payload is a dict of score_weight_* keys → string values
            for k, v in payload.items():
                storage.set_setting(k, v)
            st.success("Guardado — afecta al worker y a «Re-score».")

    st.divider()

    # ── Threshold (UI-05) ─────────────────────────────────────────────────
    st.subheader("Umbral de notificación")
    threshold = st.number_input(
        "Umbral mínimo de score",
        value=_to_int(settings.get("notification_min_score"), 70),
        min_value=0,
        max_value=100,
        step=5,
        key="threshold",
    )
    if st.button("Guardar umbral"):
        storage.set_setting("notification_min_score", str(threshold))
        st.success("Guardado — afecta al worker y a «Re-score».")

    st.divider()

    # ── Deal-breakers (UI-06) ─────────────────────────────────────────────
    st.subheader("Deal-breakers")
    st.caption("Uno por línea. Si una oferta cumple alguno → recommendation = skip.")

    # Load persisted deal_breakers JSON and convert to textarea text.
    # WR-02: guard against malformed/legacy values (non-JSON, non-list, truncated
    # write) — a bad value must not crash the whole Settings page.
    raw_db = settings.get("deal_breakers", "[]")
    try:
        current_db = json.loads(raw_db)
        if not isinstance(current_db, list):
            current_db = []
    except (json.JSONDecodeError, TypeError):
        current_db = []
    deal_breakers_text = st.text_area(
        "Deal-breakers (uno por línea)",
        value="\n".join(current_db),
        height=150,
        key="deal_breakers_text",
    )
    if st.button("Guardar deal-breakers"):
        lines = deal_breakers_text.split("\n")
        storage.set_setting("deal_breakers", pack_deal_breakers(lines))
        st.success("Guardado — afecta al worker y a «Re-score».")

    st.divider()

    # ── Canal de notificación (UI-05 / NOTIF-02) ─────────────────────────
    st.subheader("Canal de notificación")
    _channel_options = ["auto", "telegram", "email", "none"]
    current_channel = settings.get("notification_channel", "none")
    # Guard: if a persisted value is not in the valid set, fall back to "none"
    if current_channel not in _channel_options:
        current_channel = "none"
    channel_index = _channel_options.index(current_channel)
    notification_channel = st.selectbox(
        "Canal de notificación",
        options=_channel_options,
        index=channel_index,
        key="notification_channel",
    )
    st.caption(
        "auto = detecta Telegram/email según las variables de entorno; "
        "telegram/email fuerzan ese canal; none = sin notificaciones."
    )
    if st.button("Guardar canal"):
        if notification_channel in _channel_options:
            storage.set_setting("notification_channel", notification_channel)
            st.success("Guardado — afecta al próximo run del worker.")
        else:
            st.error("Valor de canal no válido.")

    st.divider()

    # ── Channel status — booleans ONLY, never secret values (T-10-06-01) ─
    st.subheader("Canales de notificación")
    st.caption("Muestra solo si el canal está configurado — nunca los valores secretos.")

    cs = channel_status()
    st.write("Telegram configurado:", "✓" if cs["telegram"] else "✗")
    st.write("Email configurado:", "✓" if cs["email"] else "✗")
    st.write("OpenAI:", "✓" if cs["openai"] else "✗")


# Gate: only render the page body when a Streamlit runtime is active.
# Keeps the module import-safe for unit tests (D-12 pattern).
try:
    from streamlit.runtime import exists as _st_running

    if _st_running():
        _render()
except Exception:  # noqa: BLE001
    # Not in a Streamlit context — module imported for testing only.
    pass
