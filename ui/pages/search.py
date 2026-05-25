"""Search Config page (UI-02) — edit and persist search parameters.

The save_search_settings() helper is a pure Python function at module top level
so it is importable + testable without a Streamlit runtime (the page-render
body is gated behind streamlit.runtime.exists() per D-12/SC2).

Settings keys persisted (upsert via set_setting):
  search_query, search_country, search_language,
  date_posted, employment_types, remote_only.

All values are stored as strings; remote_only is serialized as "true"/"false".

Security (threat model T-10-04-03):
- date_posted constrained to a fixed selectbox set ("month"/"3days"/"today").
- remote_only serialized deterministically to "true"/"false".
- All values coerced to str via set_setting before entering the settings table.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Pure helper — importable without Streamlit runtime (for unit tests, SC2)
# ---------------------------------------------------------------------------


def save_search_settings(
    storage,
    *,
    search_query: str,
    search_country: str,
    search_language: str,
    date_posted: str,
    employment_types: str,
    remote_only: bool,
) -> None:
    """Persist all search_* settings via set_setting (upsert).

    Called by the page on save and unit-tested directly (SC2).

    Args:
        storage:           SQLiteStorage instance (from ui.services.get_storage()).
        search_query:      Free-text query / job titles.
        search_country:    ISO country code (e.g. "ES", "US").
        search_language:   Language code (e.g. "es", "en").
        date_posted:       One of "month", "3days", "today".
        employment_types:  Comma-separated type string (e.g. "FULLTIME,CONTRACTOR").
        remote_only:       Whether to filter remote-only results.
    """
    storage.set_setting("search_query", search_query)
    storage.set_setting("search_country", search_country)
    storage.set_setting("search_language", search_language)
    storage.set_setting("date_posted", date_posted)
    storage.set_setting("employment_types", employment_types)
    storage.set_setting("remote_only", "true" if remote_only else "false")


# ---------------------------------------------------------------------------
# Page render — gated so importing this module under pytest does not require
# a running Streamlit server (D-12 pattern).
# ---------------------------------------------------------------------------


def _render() -> None:
    """Streamlit page body for Search Config (UI-02)."""
    import streamlit as st

    from ui.services import get_storage

    st.header("Búsqueda")

    storage = get_storage()
    settings = storage.get_settings()

    # ── Current persisted values (pre-fill widgets) ───────────────────────
    search_query = st.text_input(
        "Puestos / consulta de búsqueda",
        value=settings.get("search_query", "AI Engineer OR ML Engineer"),
        help="Términos separados por OR. Ej: AI Engineer OR MLOps Engineer",
    )

    search_country = st.text_input(
        "País (código ISO, ej. ES, US, DE)",
        value=settings.get("search_country", "ES"),
    )

    search_language = st.text_input(
        "Idioma de resultados (ej. es, en)",
        value=settings.get("search_language", "es"),
    )

    _date_options = ["month", "3days", "today"]
    current_date_posted = settings.get("date_posted", "3days")
    date_posted_index = _date_options.index(current_date_posted) if current_date_posted in _date_options else 1

    date_posted = st.selectbox(
        "Publicadas en los últimos…",
        options=_date_options,
        index=date_posted_index,
        format_func=lambda x: {"month": "Último mes", "3days": "Últimos 3 días", "today": "Hoy"}[x],
    )

    employment_types = st.text_input(
        "Tipos de contrato (separados por coma, ej. FULLTIME,CONTRACTOR)",
        value=settings.get("employment_types", "FULLTIME"),
    )

    remote_only = st.toggle(
        "Solo empleos en remoto",
        value=(settings.get("remote_only") == "true"),
    )

    # ── Save button ────────────────────────────────────────────────────────
    if st.button("Guardar", type="primary"):
        save_search_settings(
            storage,
            search_query=search_query,
            search_country=search_country,
            search_language=search_language,
            date_posted=date_posted,
            employment_types=employment_types,
            remote_only=remote_only,
        )
        st.success("Guardado — el próximo run del worker usará estos parámetros.")


# Gate: only run the page body when a Streamlit runtime is active.
# This keeps the module import-safe for unit tests (SC2 / D-12 pattern).
try:
    from streamlit.runtime import exists as _st_running

    if _st_running():
        _render()
except Exception:  # noqa: BLE001
    # Not in a Streamlit context — module imported for testing only.
    pass
