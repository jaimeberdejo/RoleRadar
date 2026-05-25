"""Tests for ui/pages/search.py — search settings persistence (SC2).

Verifies that:
- save_search_settings() persists all search_* keys via set_setting (SC2).
- get_settings() returns the saved values after save_search_settings() call.
- The module is import-safe under pytest (no Streamlit runtime needed for
  the helper function).
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# SC2: save_search_settings persists all search_* keys round-trip
# ---------------------------------------------------------------------------


def test_save_search_settings_persists(tmp_path: Path) -> None:
    """All six search_* settings are persisted and readable via get_settings."""
    import os

    os.environ["SQLITE_DB_PATH"] = str(tmp_path / "test.db")

    from app.storage.sqlite import SQLiteStorage
    from ui.pages.search import save_search_settings

    storage = SQLiteStorage(str(tmp_path / "test.db"))
    storage.init_db()

    save_search_settings(
        storage,
        search_query="AI Engineer OR ML Engineer",
        search_country="ES",
        search_language="es",
        date_posted="month",
        employment_types="FULLTIME",
        remote_only=True,
    )

    s = storage.get_settings()

    assert s["search_query"] == "AI Engineer OR ML Engineer"
    assert s["search_country"] == "ES"
    assert s["search_language"] == "es"
    assert s["date_posted"] == "month"
    assert s["employment_types"] == "FULLTIME"
    assert s["remote_only"] == "true"


def test_save_search_settings_remote_only_false(tmp_path: Path) -> None:
    """remote_only=False is serialized as 'false' string."""
    from app.storage.sqlite import SQLiteStorage
    from ui.pages.search import save_search_settings

    storage = SQLiteStorage(str(tmp_path / "test2.db"))
    storage.init_db()

    save_search_settings(
        storage,
        search_query="Data Engineer",
        search_country="US",
        search_language="en",
        date_posted="3days",
        employment_types="FULLTIME,CONTRACTOR",
        remote_only=False,
    )

    s = storage.get_settings()
    assert s["remote_only"] == "false"
    assert s["date_posted"] == "3days"
    assert s["employment_types"] == "FULLTIME,CONTRACTOR"
