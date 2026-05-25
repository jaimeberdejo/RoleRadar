"""Telegram digest sender via raw httpx.Client (sync). Mirrors app/sources/jsearch.py.

Uses raw httpx.Client (sync) — PTB is async-first and was removed from deps (see RESEARCH).
Token + chat_id read from env INSIDE the function, never at module level, never logged (D-04).

SSRF guard (T-09-07): the POST target is always the fixed constant
`f"{TELEGRAM_BASE}/bot{token}/sendMessage"`. Job URLs from JSearch are placed only in
the JSON `text` field (message body) — they never influence the HTTP request target.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT = 10.0


def send_telegram_digest(
    chunks: list[tuple[str, list[str]]],
    *,
    client: httpx.Client | None = None,
) -> tuple[list[str], list[str]]:
    """Send pre-chunked digest messages. Returns (delivered_job_ids, errors).

    Each element of `chunks` is (text, job_ids_in_this_chunk). For each chunk we
    POST sendMessage; on HTTP 200 the chunk's job_ids are added to delivered; on
    any error they are NOT (so a later chunk failing never un-delivers earlier
    chunks — D-11). Never raises.

    Token and chat_id are read from env inside this function, never at module level
    and never logged (D-04/T-09-06).
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    # Fixed request target — job data goes only in the 'text' body field (T-09-07)
    url = f"{TELEGRAM_BASE}/bot{token}/sendMessage"
    delivered: list[str] = []
    errors: list[str] = []

    def _send(c: httpx.Client) -> None:
        for text, job_ids in chunks:
            ok = _post_chunk(c, url, chat_id, text)
            if ok:
                delivered.extend(job_ids)
            else:
                errors.append(
                    f"telegram: chunk send failed ({len(job_ids)} offers held for next run)"
                )

    try:
        if client is None:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as _c:
                _send(_c)
        else:
            _send(client)
    except httpx.HTTPError as exc:
        logger.warning("Telegram HTTP error (outer): %s", exc)
        errors.append(f"telegram: {exc}")
    return delivered, errors


def _post_chunk(client: httpx.Client, url: str, chat_id: str, text: str) -> bool:
    """POST one sendMessage chunk to the Bot API. Returns True on 200, False otherwise.

    Never raises — per-chunk error isolation (mirrors jsearch.py _do_get pattern).
    Status code and API error description are logged (not the token — D-04/T-09-06).
    """
    try:
        resp = client.post(
            url,
            json={"chat_id": chat_id, "text": text},
            timeout=DEFAULT_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        logger.warning("Telegram HTTP error on chunk POST: %s", exc)
        return False
    if resp.status_code == 200:
        return True
    try:
        desc = resp.json().get("description")
    except Exception:  # noqa: BLE001
        desc = "(non-JSON body)"
    # Log status code + Telegram error description — never the token (T-09-06)
    logger.warning("Telegram API error %d: %s", resp.status_code, desc)
    return False
