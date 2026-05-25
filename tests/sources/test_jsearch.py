"""RED guard tests for app/sources/jsearch.py — SRC-01, SRC-02.

These tests FAIL until Wave 1 creates app/sources/jsearch.py.
They define the exact expected behaviour of the JSearch HTTP client:
- Successful single-query fetch (SRC-01)
- Per-query 429 isolation: one 429 does not abort other queries (SRC-02)
- Network errors return [] without raising
- RapidAPI key sourced from environment, never hardcoded

Mock strategy: unittest.mock.patch on app.sources.jsearch.httpx.Client.
The Client is used as a context manager in the implementation, so we configure
MockClient.return_value.__enter__.return_value as the inner client instance.
No respx dependency — uses unittest.mock throughout (project convention).
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ok_response(jobs: list[dict]) -> MagicMock:
    """Build a mock httpx response with status_code=200 and the given jobs."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"data": jobs}
    return resp


def _make_429_response() -> MagicMock:
    """Build a mock httpx response with status_code=429."""
    resp = MagicMock()
    resp.status_code = 429
    return resp


# ---------------------------------------------------------------------------
# SRC-01: successful single-query fetch
# ---------------------------------------------------------------------------

def test_fetch_jsearch_query_success(monkeypatch):
    """fetch_jsearch_query returns a list of raw dicts from data[] on 200."""
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    ok_resp = _make_ok_response([
        {"job_title": "AI Eng", "employer_name": "Corp", "job_description": "desc"}
    ])

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = ok_resp

        result = fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert isinstance(result, list), "Result must be a list"
    assert len(result) == 1, "Expected 1 job from mock response"
    assert result[0]["job_title"] == "AI Eng"


def test_fetch_jsearch_query_429_returns_empty(monkeypatch):
    """fetch_jsearch_query returns [] on 429 — does not raise."""
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = _make_429_response()

        result = fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert result == [], "429 must return empty list, not raise"


def test_fetch_jsearch_query_network_error(monkeypatch):
    """fetch_jsearch_query returns [] on ConnectError — does not raise."""
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = httpx.ConnectError("timeout")

        result = fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert result == [], "Network error must return empty list, not raise"


# ---------------------------------------------------------------------------
# SRC-02: per-query 429 isolation (multi-query)
# ---------------------------------------------------------------------------

def test_fetch_all_queries_429_isolation(monkeypatch):
    """fetch_all_queries: a 429 on one query does not abort other queries.

    Setup: first query returns 429, second returns 200 with one job.
    Expected: result has length 1 (only the second query's job), no raise.
    """
    from app.sources.jsearch import fetch_all_queries  # noqa: PLC0415

    ok_job = {"job_title": "AI Engineer", "employer_name": "TechCorp", "job_description": "desc"}

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = [
            _make_429_response(),                   # first query → 429
            _make_ok_response([ok_job]),             # second query → ok
        ]

        settings = {
            "search_country": "es",
            "num_pages": "1",
            "date_posted_override": "3days",
        }
        result = fetch_all_queries(["ML Engineer", "AI Engineer"], settings)

    assert len(result) == 1, (
        "Only the second query's job should be in results; first 429 must not abort"
    )
    assert result[0]["job_title"] == "AI Engineer"


# ---------------------------------------------------------------------------
# Auth: RAPIDAPI_KEY sourced from env (T-08-01 — no hardcoded key)
# ---------------------------------------------------------------------------

def test_fetch_jsearch_uses_rapidapi_key_from_env(monkeypatch):
    """fetch_jsearch_query reads RAPIDAPI_KEY from env and sends it in headers.

    Verifies:
    - X-RapidAPI-Key header == os.environ["RAPIDAPI_KEY"]
    - X-RapidAPI-Host header == "jsearch.p.rapidapi.com"

    No key literal in this file — monkeypatch injects the test value (T-08-01).
    """
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    monkeypatch.setenv("RAPIDAPI_KEY", "test-key-from-env")

    captured_headers: dict = {}

    ok_resp = _make_ok_response([])

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value

        def capture_get(url, *, headers, params, **kwargs):
            captured_headers.update(headers)
            return ok_resp

        instance.get.side_effect = capture_get

        fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert captured_headers.get("X-RapidAPI-Key") == "test-key-from-env", (
        "X-RapidAPI-Key must equal the value from RAPIDAPI_KEY env var"
    )
    assert captured_headers.get("X-RapidAPI-Host") == "jsearch.p.rapidapi.com", (
        "X-RapidAPI-Host must be jsearch.p.rapidapi.com"
    )
