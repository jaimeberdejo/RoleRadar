"""Status page helpers — BuscadorDeEmpleo v2.0.

Import-clean (no streamlit, no apscheduler). Pure Python datetime logic so this
module is fully unit-testable from any context (worker, tests, UI page).

Satisfies SC6 / UI-09: the Status page needs to display the next scheduled run
time without importing APScheduler or Streamlit into the computation.
"""
from __future__ import annotations

from datetime import datetime, timedelta


def compute_next_run(
    runs: list[dict],
    schedule_interval_hours: float,
) -> datetime | None:
    """Compute the datetime of the next expected pipeline run.

    Uses the most recent run's started_at timestamp plus the configured interval.
    Returns None when there are no recorded runs or when the timestamp is missing
    or unparseable — the UI page renders "unknown" in those cases.

    Args:
        runs: List of run dicts as returned by storage.get_recent_runs().
              runs[0] is the most recent run (ordered by id DESC).
        schedule_interval_hours: Interval between scheduled runs (hours).
              Converted from the settings table string by the caller before passing.

    Returns:
        datetime (timezone-aware if started_at was aware) of next expected run,
        or None if it cannot be determined.
    """
    if not runs:
        return None

    started_at_raw = runs[0].get("started_at")
    if not started_at_raw:
        return None

    try:
        last_started = datetime.fromisoformat(started_at_raw)
    except (ValueError, TypeError):
        return None

    return last_started + timedelta(hours=schedule_interval_hours)
