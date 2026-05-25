"""JSearch HTTP client (RapidAPI).

Provides the app-owned fetch layer for JSearch RapidAPI. Returns raw dicts
from the ``data[]`` array; field mapping is done by the pipeline via
``app.dedup.mappers.jsearch_mapper`` — this module does NOT call the mapper.

Design decisions:
- Sync ``httpx.Client`` is used (not async) because the worker runs inside
  APScheduler's BlockingScheduler thread and we must not leak event-loop state.
- Per-query error isolation (SRC-02): a 429 or network error on one query logs
  a warning and returns [] for that query; other queries continue unaffected.
- RAPIDAPI_KEY is read from os.environ inside each call, never at module level
  and never hardcoded (MIG-03 / T-08-02).
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

JSEARCH_BASE = "https://jsearch.p.rapidapi.com/search"
JSEARCH_HOST = "jsearch.p.rapidapi.com"
DEFAULT_TIMEOUT = 20.0


def fetch_jsearch_query(
    query: str,
    *,
    date_posted: str = "3days",
    num_pages: int = 1,
    country: str = "es",
    language: str | None = None,
    employment_types: str | None = None,
    remote_only: bool = False,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch a single JSearch query and return the raw ``data[]`` elements.

    Args:
        query:            Search query string (e.g. "AI Engineer Barcelona").
        date_posted:      JSearch date_posted param (e.g. "3days", "month").
        num_pages:        Number of result pages to fetch (usually 1).
        country:          ISO country code for the search (e.g. "es").
        language:         Optional language code → JSearch ``language`` param
                          (e.g. "es", "en"). Omitted when falsy (CR-01).
        employment_types: Optional comma-separated JSearch employment_types
                          (e.g. "FULLTIME,CONTRACTOR"). Omitted when falsy (CR-01).
        remote_only:      When True, sets JSearch ``remote_jobs_only=true`` so
                          only remote postings are returned (CR-01).
        client:           Optional pre-created httpx.Client to reuse (for
                          connection-pool sharing across multiple queries).
                          If None, a short-lived client is created and closed.

    Returns:
        List of raw job dicts from the ``data`` array, or [] on error.
        Never raises — per-query isolation is an invariant.
    """
    # Read key inside the function — never at module level (T-08-02).
    headers = {
        "X-RapidAPI-Key": os.environ.get("RAPIDAPI_KEY", ""),
        "X-RapidAPI-Host": JSEARCH_HOST,
    }
    params = {
        "query": query,
        "page": "1",
        "num_pages": str(num_pages),
        "date_posted": date_posted,
        "country": country,
    }
    # CR-01: plumb the saved Search Config knobs into the JSearch request.
    # Only add optional params when set so we never send empty/false noise.
    if language:
        params["language"] = language
    if employment_types:
        params["employment_types"] = employment_types
    if remote_only:
        params["remote_jobs_only"] = "true"

    try:
        if client is None:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as _client:
                return _do_get(_client, headers, params, query)
        else:
            return _do_get(client, headers, params, query)
    except httpx.HTTPError as exc:
        logger.warning("JSearch HTTP error for query=%r: %s", query, exc)
        return []


def _do_get(
    client: httpx.Client,
    headers: dict,
    params: dict,
    query: str,
) -> list[dict]:
    """Execute GET, handle 429/auth errors, parse response. May raise httpx.HTTPError."""
    resp = client.get(JSEARCH_BASE, headers=headers, params=params)
    if resp.status_code == 429:
        logger.warning("JSearch 429 for query=%r — skipping", query)
        return []
    if resp.status_code in (401, 403):
        logger.error(
            "JSearch auth failure (status=%d) for query=%r — "
            "check RAPIDAPI_KEY env var",
            resp.status_code,
            query,
        )
        return []
    resp.raise_for_status()
    try:
        return resp.json().get("data", [])
    except (ValueError, KeyError) as exc:
        # json.JSONDecodeError is a subclass of ValueError; catches HTML/plain error pages
        logger.warning(
            "JSearch non-JSON response for query=%r (status=%d): %s",
            query,
            resp.status_code,
            exc,
        )
        return []


def fetch_all_queries(
    queries: list[str],
    settings: dict,
    *,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch all search queries and return all raw job dicts combined.

    Each query is executed independently; a 429 or network error on one query
    does not abort the others (SRC-02).

    Args:
        queries:  List of query strings to fetch.
        settings: Dict with optional keys:
                    - date_posted_override (str, default "3days")
                    - search_country (str, default "es")
                    - num_pages (str|int, default "1")
                    - search_language (str, optional) → JSearch language param
                    - employment_types (str, optional) → JSearch employment_types
                    - remote_only ("true"/"false", optional) → remote_jobs_only
        client:   Optional pre-created httpx.Client. If None, a shared client
                  is created for all queries and closed when done.

    Returns:
        Combined list of raw job dicts from all queries.
    """
    date_posted = settings.get("date_posted_override", "3days")
    country = settings.get("search_country", "es")
    num_pages = int(settings.get("num_pages", "1"))
    # CR-01: plumb the user's saved Search Config knobs through to the request.
    language = settings.get("search_language") or None
    employment_types = settings.get("employment_types") or None
    remote_only = str(settings.get("remote_only", "false")).lower() == "true"

    all_raw: list[dict] = []

    if client is None:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as _client:
            for q in queries:
                raw = fetch_jsearch_query(
                    q,
                    date_posted=date_posted,
                    num_pages=num_pages,
                    country=country,
                    language=language,
                    employment_types=employment_types,
                    remote_only=remote_only,
                    client=_client,
                )
                logger.info("JSearch query=%r fetched=%d", q, len(raw))
                all_raw.extend(raw)
    else:
        for q in queries:
            raw = fetch_jsearch_query(
                q,
                date_posted=date_posted,
                num_pages=num_pages,
                country=country,
                language=language,
                employment_types=employment_types,
                remote_only=remote_only,
                client=client,
            )
            logger.info("JSearch query=%r fetched=%d", q, len(raw))
            all_raw.extend(raw)

    return all_raw
