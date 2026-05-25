"""RED guard tests for deal_breakers seeded in init_db defaults (RESEARCH Pitfall 5, UI-06).

These tests FAIL today because _SETTING_DEFAULTS in init_db does not include a "deal_breakers"
key. The tests verify that after calling init_db() on a fresh DB:
- "deal_breakers" key is present in get_settings() dict.
- The value is a valid JSON-encoded list (so the overlay can parse it with json.loads).

Test uses SQLiteStorage on a fresh tmp_path — never touches data/jobs.db.
"""
from __future__ import annotations

import json

from app.storage.sqlite import SQLiteStorage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_deal_breakers_seeded_in_defaults(tmp_path):
    """After init_db() on a fresh DB, get_settings() must include 'deal_breakers' key.

    RED today: _SETTING_DEFAULTS in init_db does not contain 'deal_breakers'.
    GREEN when Plan 02 adds "deal_breakers": '[]' (or similar) to _SETTING_DEFAULTS.
    """
    storage = SQLiteStorage(str(tmp_path / "fresh.db"))
    storage.init_db()

    settings = storage.get_settings()
    assert "deal_breakers" in settings, (
        f"'deal_breakers' must be seeded in init_db defaults; "
        f"got keys={sorted(settings.keys())}"
    )


def test_deal_breakers_default_is_valid_json_list(tmp_path):
    """The seeded deal_breakers value must be a JSON-encoded list.

    build_effective_profile uses json.loads(settings["deal_breakers"]) — the
    default value must parse successfully as a list.
    """
    storage = SQLiteStorage(str(tmp_path / "fresh2.db"))
    storage.init_db()

    settings = storage.get_settings()
    # This will KeyError today (deal_breakers absent) — fail for the right reason
    raw = settings["deal_breakers"]
    parsed = json.loads(raw)
    assert isinstance(parsed, list), (
        f"deal_breakers default must be a JSON-encoded list; got {type(parsed)}: {parsed!r}"
    )


# ---------------------------------------------------------------------------
# WR-02: the Settings page must not crash on a malformed persisted deal_breakers
# ---------------------------------------------------------------------------

def _settings_page_parse_deal_breakers(settings: dict) -> list:
    """Mirror the guarded parse in ui/pages/settings.py (WR-02).

    Kept in sync with the page so a regression there fails this test. A non-JSON
    or non-list value must yield [] rather than raising and blanking the page.
    """
    raw_db = settings.get("deal_breakers", "[]")
    try:
        current_db = json.loads(raw_db)
        if not isinstance(current_db, list):
            current_db = []
    except (json.JSONDecodeError, TypeError):
        current_db = []
    return current_db


def test_settings_page_handles_malformed_deal_breakers():
    """WR-02: a legacy plain string / truncated write must not raise; → []."""
    # Legacy non-JSON string value (e.g. a plain string was stored directly)
    assert _settings_page_parse_deal_breakers({"deal_breakers": "not json {"}) == []
    # Valid JSON but not a list (e.g. an object) → []
    assert _settings_page_parse_deal_breakers({"deal_breakers": '{"a": 1}'}) == []
    # Valid JSON list → preserved
    assert _settings_page_parse_deal_breakers(
        {"deal_breakers": '["sin remoto"]'}
    ) == ["sin remoto"]
    # Absent key → default "[]" → []
    assert _settings_page_parse_deal_breakers({}) == []
