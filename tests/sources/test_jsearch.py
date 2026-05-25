"""RED guard tests for app/sources/jsearch.py — SRC-01, SRC-02.

These tests FAIL until Wave 1 creates app/sources/jsearch.py.
They define the exact expected behaviour of the JSearch HTTP client:
- Successful single-query fetch (SRC-01)
- Per-query 429 isolation: one 429 does not abort other queries (SRC-02)
- Per-query non-JSON isolation (CR-01): HTML/non-JSON response does not abort sibling queries
- Auth failure returns [] with targeted log (WR-04)
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


def _make_non_json_response(status_code: int = 200) -> MagicMock:
    """Build a mock response whose .json() raises json.JSONDecodeError (e.g. HTML page)."""
    import json
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = lambda: None
    resp.json.side_effect = json.JSONDecodeError("No JSON object could be decoded", "", 0)
    return resp


def _make_auth_failure_response(status_code: int = 401) -> MagicMock:
    """Build a mock response for auth failures (401/403)."""
    resp = MagicMock()
    resp.status_code = status_code
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


# ---------------------------------------------------------------------------
# CR-01: non-JSON response per-query isolation (SRC-02 invariant)
# ---------------------------------------------------------------------------

def test_fetch_jsearch_query_non_json_returns_empty():
    """fetch_jsearch_query returns [] when the response body is not valid JSON.

    CR-01: json.JSONDecodeError (a ValueError subclass) from resp.json() must
    be caught inside _do_get and return [] — it must NOT propagate as an
    unhandled exception.
    """
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = _make_non_json_response(status_code=200)

        result = fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert result == [], "Non-JSON 200 response must return empty list, not raise"


def test_fetch_all_queries_non_json_does_not_abort_sibling_queries():
    """fetch_all_queries: a non-JSON response on one query does not abort other queries.

    CR-01 / SRC-02: verifies that json.JSONDecodeError from resp.json() is
    contained per-query. The sibling query still runs and returns its jobs.
    """
    from app.sources.jsearch import fetch_all_queries  # noqa: PLC0415

    ok_job = {"job_title": "Data Engineer", "employer_name": "DataCo", "job_description": "d"}

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.side_effect = [
            _make_non_json_response(status_code=200),   # first query → HTML page
            _make_ok_response([ok_job]),                 # second query → ok
        ]

        settings = {
            "search_country": "es",
            "num_pages": "1",
            "date_posted_override": "3days",
        }
        result = fetch_all_queries(["ML Engineer", "Data Engineer"], settings)

    assert len(result) == 1, (
        "Sibling query job must be present; non-JSON first query must not abort"
    )
    assert result[0]["job_title"] == "Data Engineer"


# ---------------------------------------------------------------------------
# CR-01: saved Search Config knobs reach the JSearch request params
# ---------------------------------------------------------------------------

def test_fetch_all_queries_plumbs_settings_into_params():
    """CR-01: employment_types / remote_only / search_language from settings
    must land in the JSearch request params dict.

    Without the fix, fetch_all_queries only forwarded date_posted/country/
    num_pages, so these three saved settings were silently dropped (no-op).
    """
    from app.sources.jsearch import fetch_all_queries  # noqa: PLC0415

    captured_params: dict = {}

    ok_resp = _make_ok_response([])

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value

        def capture_get(url, *, headers, params, **kwargs):
            captured_params.update(params)
            return ok_resp

        instance.get.side_effect = capture_get

        settings = {
            "search_country": "es",
            "num_pages": "1",
            "date_posted_override": "3days",
            "search_language": "en",
            "employment_types": "FULLTIME,CONTRACTOR",
            "remote_only": "true",
        }
        fetch_all_queries(["AI Engineer"], settings)

    assert captured_params.get("language") == "en", (
        "search_language must be forwarded to the JSearch 'language' param"
    )
    assert captured_params.get("employment_types") == "FULLTIME,CONTRACTOR", (
        "employment_types must be forwarded to the JSearch 'employment_types' param"
    )
    assert captured_params.get("remote_jobs_only") == "true", (
        "remote_only=true must map to JSearch 'remote_jobs_only=true'"
    )


def test_fetch_all_queries_omits_unset_optional_params():
    """CR-01: when the optional knobs are not set, they must NOT appear in params.

    remote_only=false must not emit remote_jobs_only, and an empty language /
    employment_types must be omitted entirely (no empty-string noise).
    """
    from app.sources.jsearch import fetch_all_queries  # noqa: PLC0415

    captured_params: dict = {}

    ok_resp = _make_ok_response([])

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value

        def capture_get(url, *, headers, params, **kwargs):
            captured_params.update(params)
            return ok_resp

        instance.get.side_effect = capture_get

        settings = {
            "search_country": "es",
            "num_pages": "1",
            "date_posted_override": "3days",
            "search_language": "",
            "employment_types": "",
            "remote_only": "false",
        }
        fetch_all_queries(["AI Engineer"], settings)

    assert "language" not in captured_params, "empty search_language must be omitted"
    assert "employment_types" not in captured_params, "empty employment_types must be omitted"
    assert "remote_jobs_only" not in captured_params, "remote_only=false must omit remote_jobs_only"


# ---------------------------------------------------------------------------
# WR-04: auth failure (401/403) returns [] with targeted log
# ---------------------------------------------------------------------------

def test_fetch_jsearch_query_401_returns_empty():
    """fetch_jsearch_query returns [] on 401 Unauthorized — does not raise.

    WR-04: a 401 (missing/invalid RAPIDAPI_KEY) must be caught before
    raise_for_status() and return [], not propagate as an HTTPStatusError.
    """
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = _make_auth_failure_response(status_code=401)

        result = fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert result == [], "401 must return empty list, not raise"


def test_fetch_jsearch_query_403_returns_empty():
    """fetch_jsearch_query returns [] on 403 Forbidden — does not raise.

    WR-04: a 403 (bad/missing RAPIDAPI_KEY plan) must be caught before
    raise_for_status() and return [], not propagate as an HTTPStatusError.
    """
    from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415

    with patch("app.sources.jsearch.httpx.Client") as MockClient:
        instance = MockClient.return_value.__enter__.return_value
        instance.get.return_value = _make_auth_failure_response(status_code=403)

        result = fetch_jsearch_query(
            "AI Engineer", date_posted="3days", num_pages=1, country="es"
        )

    assert result == [], "403 must return empty list, not raise"
