"""Tests for ui/results_logic.py pure helpers.

Tests the filter_history, build_results_df, and run_status_label functions
without requiring a Streamlit runtime.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_history() -> list[dict]:
    """Three scored job rows with varying scores and recommendations."""
    return [
        {
            "id": "job-1",
            "title": "AI Engineer",
            "company": "Acme Corp",
            "score_total": 90,
            "recommendation": "strong_fit",
            "score": {},
        },
        {
            "id": "job-2",
            "title": "Data Scientist",
            "company": "Globex",
            "score_total": 60,
            "recommendation": "maybe",
            "score": {},
        },
        {
            "id": "job-3",
            "title": "Backend Developer",
            "company": "Initech",
            "score_total": 30,
            "recommendation": "skip",
            "score": {},
        },
    ]


# ---------------------------------------------------------------------------
# filter_history tests
# ---------------------------------------------------------------------------

def test_filter_by_score(sample_history):
    """Only rows with score_total >= min_score are kept."""
    from ui.results_logic import filter_history

    result = filter_history(
        sample_history, 70, ["strong_fit", "good_fit", "maybe", "skip"]
    )
    assert len(result) == 1
    assert result[0]["score_total"] == 90


def test_filter_by_recommendation(sample_history):
    """Only rows with matching recommendation are kept."""
    from ui.results_logic import filter_history

    result = filter_history(sample_history, 0, ["strong_fit"])
    assert len(result) == 1
    assert result[0]["recommendation"] == "strong_fit"


def test_filter_combined(sample_history):
    """Both score and recommendation filters apply simultaneously."""
    from ui.results_logic import filter_history

    result = filter_history(sample_history, 50, ["maybe", "strong_fit"])
    # 90/strong_fit -> kept; 60/maybe -> kept; 30/skip -> excluded by rec
    assert len(result) == 2
    titles = {r["title"] for r in result}
    assert titles == {"AI Engineer", "Data Scientist"}


def test_filter_empty_history():
    """Empty history returns empty list."""
    from ui.results_logic import filter_history

    result = filter_history([], 0, ["strong_fit", "good_fit", "maybe", "skip"])
    assert result == []


# ---------------------------------------------------------------------------
# build_results_df tests
# ---------------------------------------------------------------------------

def test_build_df_columns(sample_history):
    """build_results_df produces correct columns, row count, and _idx values."""
    from ui.results_logic import build_results_df

    df = build_results_df(sample_history)
    assert list(df.columns) == ["Título", "Empresa", "Score", "Recomendación", "_idx"]
    assert len(df) == 3
    # _idx must point back to the source list index
    assert df.iloc[0]["_idx"] == 0
    assert df.iloc[1]["_idx"] == 1
    assert df.iloc[2]["_idx"] == 2


def test_build_df_values(sample_history):
    """build_results_df maps the right values from history rows."""
    from ui.results_logic import build_results_df

    df = build_results_df(sample_history)
    assert df.iloc[0]["Título"] == "AI Engineer"
    assert df.iloc[0]["Empresa"] == "Acme Corp"
    assert df.iloc[0]["Score"] == 90
    assert df.iloc[0]["Recomendación"] == "strong_fit"


def test_build_df_empty():
    """build_results_df on empty list returns a DataFrame with correct columns."""
    from ui.results_logic import build_results_df

    df = build_results_df([])
    assert list(df.columns) == ["Título", "Empresa", "Score", "Recomendación", "_idx"]
    assert len(df) == 0


# ---------------------------------------------------------------------------
# run_status_label tests
# ---------------------------------------------------------------------------

def test_run_status_running():
    """Running status returns ('running', loading message)."""
    from ui.results_logic import run_status_label

    state, msg = run_status_label({"running": True, "result": None, "error": None})
    assert state == "running"
    assert "ofertas" in msg.lower()


def test_run_status_done():
    """Done status returns ('done', message with scored count)."""
    from ui.results_logic import run_status_label

    class _FakeResult:
        scored = 5

    state, msg = run_status_label(
        {"running": False, "result": _FakeResult(), "error": None}
    )
    assert state == "done"
    assert "5" in msg
    assert "nuevas" in msg


def test_run_status_error():
    """Error status returns ('error', error message)."""
    from ui.results_logic import run_status_label

    state, msg = run_status_label(
        {"running": False, "result": None, "error": "Connection refused"}
    )
    assert state == "error"
    assert "Connection refused" in msg


def test_run_status_idle():
    """Idle status (no result, no error, not running) returns ('idle', '')."""
    from ui.results_logic import run_status_label

    state, msg = run_status_label({"running": False, "result": None, "error": None})
    assert state == "idle"
    assert msg == ""
