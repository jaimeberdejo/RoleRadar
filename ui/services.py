"""Shared UI helpers — BuscadorDeEmpleo v2.0.

ui imports app; app NEVER imports ui (import-cleanliness).
The background thread NEVER calls st.* (ScriptRunContext gotcha, D-04).

Public API consumed by every page module (Plans 04-06):
  get_embedder()           - @st.cache_resource BgeM3Embedder singleton (UI-10/SC7)
  get_storage()            - @st.cache_resource SQLiteStorage singleton
  get_effective_profile()  - passthrough to app.profile_overlay.build_effective_profile
  start_run()              - non-blocking pipeline launcher (D-04/D-05/D-06)
  _RUN_STATUS              - module-level run-status dict (read by polling fragments)
"""
from __future__ import annotations

import threading

import streamlit as st
from app.dedup.embedder import BgeM3Embedder
from app.storage import get_storage_backend


@st.cache_resource
def get_embedder() -> BgeM3Embedder:
    """One BgeM3Embedder per Streamlit process (UI-10 / SC7). Reused by Run now + Re-score.

    @st.cache_resource guarantees a single construction per process lifetime.
    The cached instance is injected into run_pipeline(embedder=...) so no second
    BGE-M3 model (~2.3 GB) loads when the user hits Run now (D-05).
    """
    return BgeM3Embedder()


@st.cache_resource
def get_storage():
    """One initialized SQLiteStorage per process.

    @st.cache_resource avoids repeated DB connection setup on every page rerun.
    init_db() is called inside get_storage_backend() — idempotent.
    """
    return get_storage_backend()


def get_effective_profile(profile_path=None):
    """Build the effective UserProfile by overlaying settings-table knobs onto profile.yaml.

    Reads score_weight_* and deal_breakers from the settings table (cross-process
    config bus) and overlays them on the base UserProfile from profile.yaml.

    Args:
        profile_path: Optional path override for profile.yaml (used in tests).

    Returns:
        UserProfile with settings-table pesos + deal_breakers applied.
    """
    from app.profile_overlay import build_effective_profile  # noqa: PLC0415

    settings = get_storage().get_settings()
    return build_effective_profile(settings, profile_path)


# ── Non-blocking Run now (D-04/D-05/D-06) ────────────────────────────────────
# Module-level dict — ONE instance per Streamlit process, shared across all
# reruns. For this single-user personal tool this is correct and simpler than
# per-session tracking (RESEARCH Assumption A2).
#
# All mutations go through _RUN_LOCK so the thread and the Streamlit script
# thread never race (RESEARCH Pitfall 3 / Assumption A3 — explicit lock added
# for hygiene even though CPython GIL would mostly protect simple key assigns).
_RUN_LOCK = threading.Lock()
_RUN_STATUS: dict = {"running": False, "result": None, "error": None}


def clear_run_result() -> None:
    """Clear the stored run result under _RUN_LOCK (WR-01).

    The polling fragment in results.py must NOT reach into _RUN_STATUS directly:
    the documented invariant is that ALL mutations go through _RUN_LOCK so the
    background thread and the Streamlit script thread never race.
    """
    with _RUN_LOCK:
        _RUN_STATUS["result"] = None


def clear_run_error() -> None:
    """Clear the stored run error under _RUN_LOCK (WR-01)."""
    with _RUN_LOCK:
        _RUN_STATUS["error"] = None


def _run_pipeline_thread(storage, embedder, profile_path) -> None:
    """Runs in a background thread. NEVER calls st.* functions.

    Writing to st.* from a thread that has no ScriptRunContext raises warnings
    and silently no-ops (or corrupts another session's state). Status flows
    through _RUN_STATUS only (RESEARCH Pattern 3, D-04, T-10-03-01).
    """
    from app.pipeline import run_pipeline  # noqa: PLC0415

    try:
        result = run_pipeline(storage=storage, embedder=embedder, profile_path=profile_path)
        with _RUN_LOCK:
            _RUN_STATUS["result"] = result
    except Exception as exc:  # noqa: BLE001
        with _RUN_LOCK:
            _RUN_STATUS["error"] = str(exc)
    finally:
        with _RUN_LOCK:
            _RUN_STATUS["running"] = False


def start_run(profile_path=None) -> bool:
    """Launch a pipeline run in the background.

    Returns False if a run is already in progress (D-06: double-run guard).
    Returns True if the thread was successfully started.

    The cached embedder is passed into run_pipeline so no second BGE-M3 loads
    in the UI process (D-05). The thread is daemonized so it does not prevent
    process exit if the user closes the browser.
    """
    with _RUN_LOCK:
        if _RUN_STATUS["running"]:
            return False
        _RUN_STATUS["running"] = True
        _RUN_STATUS["result"] = None
        _RUN_STATUS["error"] = None

    t = threading.Thread(
        target=_run_pipeline_thread,
        args=(get_storage(), get_embedder(), profile_path),
        daemon=True,
    )
    t.start()
    return True
