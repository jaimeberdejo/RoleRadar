"""RED guard tests for app.status_helpers.compute_next_run (UI-09, SC6).

These tests FAIL until Wave 1 creates app/status_helpers.py.
They define the exact contract compute_next_run must satisfy:
- Returns None when runs list is empty.
- Returns last_started + interval when last run has a valid started_at.
- Returns None when started_at is not a parseable ISO timestamp.
- Returns None when the runs dict has no started_at key.

This helper is import-clean Python (no streamlit) so it is fully unit-testable.
Plan 02 places it in app/status_helpers.py.

Import pattern: deferred inside each test via _import() so:
  - pytest --collect-only succeeds (no collection errors).
  - Running the tests raises ImportError inside the test body (RED state).
The guard line below satisfies: grep -q "from app.status_helpers import compute_next_run"
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _import():
    """Deferred import — fails with ImportError when app.status_helpers is absent.

    Satisfies: from app.status_helpers import compute_next_run
    """
    from app.status_helpers import compute_next_run  # noqa: PLC0415
    return compute_next_run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_next_run_empty_returns_none():
    """compute_next_run with an empty runs list returns None."""
    compute_next_run = _import()
    result = compute_next_run([], 6.0)
    assert result is None, f"Expected None for empty runs, got {result}"


def test_next_run_adds_interval():
    """compute_next_run returns last_started + interval hours.

    Given runs=[{"started_at": "2026-05-25T10:00:00+00:00"}] and interval=6,
    the result must equal datetime(2026-05-25T10:00:00+00:00) + timedelta(hours=6).
    """
    compute_next_run = _import()
    started_str = "2026-05-25T10:00:00+00:00"
    runs = [{"started_at": started_str}]
    result = compute_next_run(runs, 6.0)
    expected = datetime.fromisoformat(started_str) + timedelta(hours=6)
    assert result == expected, (
        f"Expected {expected}, got {result}"
    )


def test_next_run_bad_timestamp_returns_none():
    """compute_next_run returns None when started_at is not a parseable timestamp."""
    compute_next_run = _import()
    runs = [{"started_at": "not-a-date"}]
    result = compute_next_run(runs, 6.0)
    assert result is None, (
        f"Expected None for bad timestamp, got {result}"
    )


def test_next_run_missing_started_at_returns_none():
    """compute_next_run returns None when the runs dict has no started_at key."""
    compute_next_run = _import()
    runs = [{}]
    result = compute_next_run(runs, 6.0)
    assert result is None, (
        f"Expected None for missing started_at key, got {result}"
    )
