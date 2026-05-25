"""Status page (UI-09 / SC6) — scheduler dashboard.

Shows last run timestamp, computed next run (using compute_next_run from
app.status_helpers), new-offers/notified counts, and a recent-runs table.

The page render body is gated behind streamlit.runtime.exists() so importing
this module under pytest does not require a running Streamlit runtime (D-12 pattern).

The summarize_status() helper is a pure Python function at module top level —
importable + testable without a Streamlit runtime (SC6).

Data source: storage.get_recent_runs(limit) — rows ordered by id DESC (newest first).
Settings read: schedule_interval_hours (for next-run computation).
"""
from __future__ import annotations

from datetime import datetime

_DISPLAY_FMT = "%Y-%m-%d %H:%M"


def _format_ts(value) -> str:
    """Format an ISO-8601 string or datetime for display (IN-03).

    Returns "YYYY-MM-DD HH:MM" for a parseable value, or "—" when value is
    None/empty/malformed. Never raises — a bad persisted timestamp must not
    crash the Status page.
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, datetime):
        return value.strftime(_DISPLAY_FMT)
    try:
        return datetime.fromisoformat(str(value)).strftime(_DISPLAY_FMT)
    except (ValueError, TypeError):
        return str(value)


def summarize_status(runs: list[dict], settings: dict) -> dict:
    """Compute the status summary dict from the runs list and settings.

    Pure Python — no Streamlit. Tested directly in tests/ui/test_status_page.py.

    Args:
        runs:     List of run dicts from storage.get_recent_runs(). runs[0] is
                  the most recent run (ordered by id DESC). May be empty.
        settings: Dict from storage.get_settings(). Used for schedule_interval_hours.

    Returns:
        dict with keys:
          last_run   (str | None):      started_at of the latest run, or None.
          next_run   (datetime | None): last started_at + interval, or None.
          new_seen   (int):             new_seen count from the latest run, or 0.
          notified   (int):             notified count from the latest run, or 0.
    """
    from app.status_helpers import compute_next_run  # deferred import (no top-level cycle)

    interval_hours = float(settings.get("schedule_interval_hours", "6"))

    if not runs:
        return {
            "last_run": None,
            "next_run": compute_next_run([], interval_hours),  # → None
            "new_seen": 0,
            "notified": 0,
        }

    latest = runs[0]
    return {
        "last_run": latest.get("started_at"),
        "next_run": compute_next_run(runs, interval_hours),
        "new_seen": latest.get("new_seen") or 0,
        "notified": latest.get("notified") or 0,
    }


def _render() -> None:
    """Streamlit page body for Status (UI-09)."""
    import streamlit as st

    from ui.services import get_storage

    st.header("Estado")

    storage = get_storage()
    runs = storage.get_recent_runs(limit=10)
    settings = storage.get_settings()

    if not runs:
        st.info("El worker aún no ha ejecutado ningún run.")
        return

    s = summarize_status(runs, settings)

    # ── Headline metrics ──────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        # IN-03: format ISO timestamp for readability (guarded against None/malformed)
        st.metric("Último run", _format_ts(s["last_run"]))
    with col2:
        # IN-03: format the computed next-run datetime the same way
        st.metric("Próximo run", _format_ts(s["next_run"]))
    with col3:
        st.metric("Nuevas ofertas", s["new_seen"])
    with col4:
        st.metric("Notificadas", s["notified"])

    st.divider()

    # ── Recent runs table ─────────────────────────────────────────────────
    st.subheader("Runs recientes")

    # Select the columns the UI-SPEC calls for; drop internal id
    display_cols = [
        "started_at", "finished_at", "fetched", "deduped", "scored",
        "new_seen", "channel", "notified",
    ]
    table_data = [
        {col: row.get(col) for col in display_cols}
        for row in runs
    ]
    st.dataframe(table_data, use_container_width=True)


# Gate: only render the page body when a Streamlit runtime is active.
# Keeps the module import-safe for unit tests (D-12 / SC6).
try:
    from streamlit.runtime import exists as _st_running

    if _st_running():
        _render()
except Exception:  # noqa: BLE001
    # Not in a Streamlit context — module imported for testing only.
    pass
