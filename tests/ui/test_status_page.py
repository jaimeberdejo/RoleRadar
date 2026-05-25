"""Tests for ui/pages/status.py — summarize_status pure helper.

These tests run without a Streamlit runtime (the page render body is gated
behind streamlit.runtime.exists() per D-12). Only the summarize_status() helper
is imported directly.

Covers:
  - summarize_status with a non-empty runs list: last_run, next_run, counts
  - summarize_status with empty runs: all None/zero, next_run is None
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_summarize_with_runs():
    """With runs present: last_run, next_run, new_seen and notified are populated."""
    from ui.pages.status import summarize_status

    started_at = "2026-05-25T10:00:00+00:00"
    runs = [
        {
            "started_at": started_at,
            "finished_at": "2026-05-25T10:02:00+00:00",
            "new_seen": 3,
            "notified": 2,
        }
    ]
    settings = {"schedule_interval_hours": "6"}

    s = summarize_status(runs, settings)

    # last_run is the started_at string from runs[0]
    assert s["last_run"] == started_at

    # next_run = started_at + 6 hours
    expected_next = datetime.fromisoformat(started_at) + timedelta(hours=6)
    assert s["next_run"] == expected_next

    # counts from runs[0]
    assert s["new_seen"] == 3
    assert s["notified"] == 2


def test_summarize_empty():
    """With no runs: last_run is None, next_run is None, counts are 0."""
    from ui.pages.status import summarize_status

    s = summarize_status([], {})

    assert s["last_run"] is None
    assert s["next_run"] is None
    assert s["new_seen"] == 0
    assert s["notified"] == 0


def test_summarize_default_interval():
    """When schedule_interval_hours missing from settings, defaults to 6."""
    from ui.pages.status import summarize_status

    started_at = "2026-05-25T08:00:00+00:00"
    runs = [{"started_at": started_at, "new_seen": 1, "notified": 1}]

    # No schedule_interval_hours in settings → should default to 6
    s = summarize_status(runs, {})

    expected_next = datetime.fromisoformat(started_at) + timedelta(hours=6)
    assert s["next_run"] == expected_next


def test_summarize_respects_interval_setting():
    """schedule_interval_hours=12 in settings → next_run = last + 12h."""
    from ui.pages.status import summarize_status

    started_at = "2026-05-25T06:00:00+00:00"
    runs = [{"started_at": started_at, "new_seen": 5, "notified": 3}]
    settings = {"schedule_interval_hours": "12"}

    s = summarize_status(runs, settings)

    expected_next = datetime.fromisoformat(started_at) + timedelta(hours=12)
    assert s["next_run"] == expected_next


def test_summarize_missing_counts_default_to_zero():
    """If new_seen/notified keys absent from run dict, default to 0."""
    from ui.pages.status import summarize_status

    runs = [{"started_at": "2026-05-25T10:00:00+00:00"}]  # no new_seen/notified
    s = summarize_status(runs, {"schedule_interval_hours": "6"})

    assert s["new_seen"] == 0
    assert s["notified"] == 0


def test_summarize_status_importable_without_runtime():
    """summarize_status can be imported without a Streamlit runtime — no side effects."""
    # If this import triggers _render() or st.* calls, it would raise StreamlitAPIException.
    from ui.pages.status import summarize_status  # noqa: F401
    assert callable(summarize_status)
