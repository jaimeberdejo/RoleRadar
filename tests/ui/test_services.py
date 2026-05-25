"""Tests for ui/services.py — embedder singleton (SC7/UI-10) and run-status machinery (D-04/D-05/D-06).

Covers:
  - test_embedder_singleton: @st.cache_resource returns the SAME object on repeated calls
  - test_start_run_refuses_double: start_run() returns False when already running (D-06)
  - test_run_status_completes: thread sets running=False and result after pipeline completes
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from unittest.mock import patch

import numpy as np
import pytest

import ui.services
from app.dedup.embedder import FakeEmbedder


# ---------------------------------------------------------------------------
# Shared PipelineResult stub (mirrors app.pipeline.PipelineResult minimal API)
# ---------------------------------------------------------------------------

@dataclass
class _FakePipelineResult:
    fetched: int = 0
    deduped: int = 0
    scored: int = 0
    new_seen: int = 0
    errors: list[str] = field(default_factory=list)
    scored_jobs: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_run_status():
    """Reset _RUN_STATUS to idle before and after each test to avoid state leakage."""
    with ui.services._RUN_LOCK:
        ui.services._RUN_STATUS["running"] = False
        ui.services._RUN_STATUS["result"] = None
        ui.services._RUN_STATUS["error"] = None
    yield
    # teardown — ensure clean state for subsequent tests
    with ui.services._RUN_LOCK:
        ui.services._RUN_STATUS["running"] = False
        ui.services._RUN_STATUS["result"] = None
        ui.services._RUN_STATUS["error"] = None


# ---------------------------------------------------------------------------
# Test: embedder singleton (SC7 / UI-10 / D-03)
# ---------------------------------------------------------------------------

def test_embedder_singleton():
    """get_embedder() returns the SAME BgeM3Embedder instance on every call.

    @st.cache_resource caches by function identity — two calls in the same process
    return the same object. We patch BgeM3Embedder so the real 2.3 GB model is
    never loaded (Pitfall 7 from RESEARCH.md).
    """
    fake = FakeEmbedder(default_vector=np.array([1, 0, 0, 0], dtype=np.float32))

    # Clear the cache first so our patched constructor is used
    ui.services.get_embedder.clear()

    with patch("ui.services.BgeM3Embedder", return_value=fake):
        a = ui.services.get_embedder()
        b = ui.services.get_embedder()

    assert a is b, "get_embedder() must return the same instance on every call (SC7/UI-10)"

    # Restore clean state — clear so the real BgeM3Embedder constructor is not stuck
    ui.services.get_embedder.clear()


# ---------------------------------------------------------------------------
# Test: WR-01 lock-guarded clear helpers
# ---------------------------------------------------------------------------

def test_clear_run_result_clears_under_lock():
    """clear_run_result() sets _RUN_STATUS['result'] to None (WR-01)."""
    with ui.services._RUN_LOCK:
        ui.services._RUN_STATUS["result"] = _FakePipelineResult(scored=3)

    ui.services.clear_run_result()

    with ui.services._RUN_LOCK:
        assert ui.services._RUN_STATUS["result"] is None, (
            "clear_run_result() must set result to None"
        )


def test_clear_run_error_clears_under_lock():
    """clear_run_error() sets _RUN_STATUS['error'] to None (WR-01)."""
    with ui.services._RUN_LOCK:
        ui.services._RUN_STATUS["error"] = "boom"

    ui.services.clear_run_error()

    with ui.services._RUN_LOCK:
        assert ui.services._RUN_STATUS["error"] is None, (
            "clear_run_error() must set error to None"
        )


# ---------------------------------------------------------------------------
# Test: double-run guard (D-06 / T-10-03-02)
# ---------------------------------------------------------------------------

def test_start_run_refuses_double():
    """start_run() returns False immediately if a run is already in progress.

    Simulates a running state by setting _RUN_STATUS["running"]=True directly
    (no thread spawn needed) then verifying start_run() refuses.
    """
    with ui.services._RUN_LOCK:
        ui.services._RUN_STATUS["running"] = True

    result = ui.services.start_run()

    assert result is False, "start_run() must return False when already running (D-06)"
    # running flag must remain True (not cleared by the rejected call)
    assert ui.services._RUN_STATUS["running"] is True


# ---------------------------------------------------------------------------
# Test: run-status state machine — completion transition (D-04/D-05)
# ---------------------------------------------------------------------------

def test_run_status_completes():
    """After the background thread finishes, _RUN_STATUS transitions to running=False with result.

    Patches app.pipeline.run_pipeline (the deferred import target inside
    _run_pipeline_thread) to return a fake PipelineResult(scored=2) immediately,
    then polls until the thread finishes (max ~3 s timeout).
    """
    fake_result = _FakePipelineResult(scored=2)

    fake_embedder = FakeEmbedder(default_vector=np.array([1, 0, 0, 0], dtype=np.float32))
    fake_storage = object()  # storage is passed through but not called in the mock path

    # Clear embedder cache and inject fake so no real model loads
    ui.services.get_embedder.clear()

    with patch("ui.services.BgeM3Embedder", return_value=fake_embedder), \
         patch("ui.services.get_storage", return_value=fake_storage), \
         patch("app.pipeline.run_pipeline", return_value=fake_result):

        started = ui.services.start_run()

    assert started is True, "start_run() should return True when not already running"

    # Poll until the background thread sets running=False (max 3 seconds)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with ui.services._RUN_LOCK:
            still_running = ui.services._RUN_STATUS["running"]
        if not still_running:
            break
        time.sleep(0.05)

    with ui.services._RUN_LOCK:
        running = ui.services._RUN_STATUS["running"]
        result = ui.services._RUN_STATUS["result"]
        error = ui.services._RUN_STATUS["error"]

    assert running is False, "_RUN_STATUS['running'] must be False after thread completes"
    assert result is not None, "_RUN_STATUS['result'] must be set after successful run"
    assert result.scored == 2, f"Expected scored=2, got {result.scored}"
    assert error is None, f"_RUN_STATUS['error'] should be None on success, got: {error}"

    # Cleanup embedder cache
    ui.services.get_embedder.clear()
