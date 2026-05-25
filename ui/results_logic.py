"""Pure helper functions for the Results page — no Streamlit dependency.

These functions are extracted from ui/pages/results.py so that the data
logic is unit-testable without a running Streamlit server (SC3/D-10).

All functions are pure Python: no st.* imports, no side effects.
pandas is used only for build_results_df.
"""
from __future__ import annotations

import pandas as pd


def filter_history(
    history: list[dict],
    min_score: int,
    recommendations: list[str],
) -> list[dict]:
    """Keep only rows that pass both the score and recommendation filters.

    Args:
        history:         List of history dicts from storage.get_history().
        min_score:       Minimum score_total (inclusive).
        recommendations: Allowed recommendation values (e.g. ["strong_fit","maybe"]).

    Returns:
        Filtered list preserving the original ordering.
    """
    return [
        r for r in history
        if r["score_total"] >= min_score and r["recommendation"] in recommendations
    ]


def build_results_df(history: list[dict]) -> pd.DataFrame:
    """Build a display DataFrame from a (filtered) history list.

    Columns: Título, Empresa, Score, Recomendación, _idx.
    _idx is the index into the history list — used to look up the full row
    when the user selects a row in st.dataframe (D-10 pattern).

    Args:
        history: List of history dicts (already filtered if desired).

    Returns:
        pandas DataFrame with the five columns above.
    """
    return pd.DataFrame(
        [
            {
                "Título": r["title"],
                "Empresa": r["company"],
                "Score": r["score_total"],
                "Recomendación": r["recommendation"],
                "_idx": i,
            }
            for i, r in enumerate(history)
        ],
        columns=["Título", "Empresa", "Score", "Recomendación", "_idx"],
    )


def run_status_label(status: dict) -> tuple[str, str]:
    """Map the module-level _RUN_STATUS dict to a (state, message) pair.

    States:
        "running"  — pipeline in progress.
        "done"     — pipeline finished successfully; result is set.
        "error"    — pipeline raised an exception; error message is set.
        "idle"     — not running, no result yet (initial or after clear).

    Args:
        status: dict with keys "running" (bool), "result" (PipelineResult|None),
                "error" (str|None).

    Returns:
        Tuple of (state_string, human_readable_message).
    """
    if status.get("running"):
        return "running", "Buscando y puntuando ofertas…"
    if status.get("error"):
        return "error", f"Error en el run: {status['error']}"
    if status.get("result") is not None:
        r = status["result"]
        return "done", f"Run completado — {r.scored} nuevas ofertas puntuadas."
    return "idle", ""
