"""Pure digest helpers: channel resolution + plain-text formatting (Phase 9).

No HTTP, no SMTP, no DB. resolve_channel reads os.environ + the settings dict;
the formatting helpers are pure string transforms. Imports only stdlib —
keeps app.notifications import-clean (D-02). Secrets are read from env only and
NEVER logged (D-04).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from app.models.schemas import ScoredJob

logger = logging.getLogger(__name__)

TELEGRAM_MAX_CHARS = 4096


# ---------------------------------------------------------------------------
# Private env-presence helpers (read env inside the function, never at module level)
# ---------------------------------------------------------------------------

def _telegram_env_present() -> bool:
    """True when both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in env."""
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def _smtp_env_present() -> bool:
    """True when SMTP_HOST, SMTP_USER, and SMTP_PASSWORD are all set in env."""
    return bool(
        os.environ.get("SMTP_HOST")
        and os.environ.get("SMTP_USER")
        and os.environ.get("SMTP_PASSWORD")
    )


# ---------------------------------------------------------------------------
# Channel resolution (D-03)
# ---------------------------------------------------------------------------

def resolve_channel(settings: dict[str, str]) -> str | None:
    """Resolve which notification channel to use from settings + env.

    Resolution logic (D-03):
    - "telegram" explicit: return "telegram" if env vars present, else None + warning
    - "email" explicit: return "email" if SMTP trio present, else None + warning
    - "auto" / "none" / unset: auto-detect — telegram if env present, else email,
      else None (silent info log)

    NOTE: token/password values are NEVER logged here (D-04/T-09-06). Only the
    channel name and presence flags are referenced in log messages.
    """
    choice = (settings.get("notification_channel") or "none").strip().lower()
    if choice == "telegram":
        if _telegram_env_present():
            return "telegram"
        logger.warning(
            "notification_channel=telegram but TELEGRAM_BOT_TOKEN/CHAT_ID missing — skipping"
        )
        return None
    if choice == "email":
        if _smtp_env_present():
            return "email"
        logger.warning(
            "notification_channel=email but SMTP_HOST/USER/PASSWORD missing — skipping"
        )
        return None
    # "none" / "auto" / unset → auto-detect
    if _telegram_env_present():
        return "telegram"
    if _smtp_env_present():
        return "email"
    logger.info("no notification channel configured — digest skipped silently")
    return None


# ---------------------------------------------------------------------------
# Offer formatting (D-05)
# ---------------------------------------------------------------------------

def format_offer_block(sjob: ScoredJob) -> str:
    """Render a single ScoredJob as a plain-text block for the digest.

    Includes: title, company, score_total, recommendation, top ≤3 reasons_for, URL.

    SECURITY NOTE (T-09-07 SSRF guard): job.url is attacker-influenced data from
    JSearch. It is placed ONLY as literal text inside this block — never used to
    construct an HTTP request target. The Telegram POST URL is always the fixed
    constant in telegram.py (api.telegram.org); the email body goes through
    set_content (not headers). No SSRF or header-injection risk here.
    """
    score, job = sjob.score, sjob.job
    reasons = score.reasons_for[:3]
    # Strip embedded newlines/control chars from title/company so an attacker- or
    # LLM-influenced field cannot distort the digest's line-based layout (IN-03).
    title = job.title.replace("\n", " ").replace("\r", " ").strip()
    company = job.company.replace("\n", " ").replace("\r", " ").strip()
    lines = [
        f"{title} @ {company}",
        f"  Score: {score.score_total}/100 ({score.recommendation.value})",
    ]
    lines += [f"  + {r}" for r in reasons]
    if job.url:
        lines.append(f"  {job.url}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram chunking (D-06)
# ---------------------------------------------------------------------------

def chunk_offers_with_indices(
    header: str, offer_blocks: list[str]
) -> list[tuple[str, list[int]]]:
    """Split offer_blocks into Telegram chunks, recording each chunk's block indices.

    Identical packing to chunk_offers but ALSO returns, for every chunk, the list
    of original ``offer_blocks`` indices it contains — captured AT CONSTRUCTION
    TIME. This is the sound source of truth for pairing job IDs to chunks: callers
    must NOT reverse-engineer chunk membership via substring matching, which
    misassigns IDs when two blocks are byte-identical or one is a substring of
    another (CR-01).

    Same rules as chunk_offers (D-06): never splits a block across chunks, header
    on the first chunk only, an over-long single block still gets its own chunk.
    Every block index appears in exactly one chunk.
    """
    chunks: list[tuple[str, list[int]]] = []
    current = header
    idxs: list[int] = []
    for i, block in enumerate(offer_blocks):
        candidate = current + "\n\n" + block
        if len(candidate) > TELEGRAM_MAX_CHARS and current != header and current:
            chunks.append((current, idxs))
            current = block
            idxs = [i]
        else:
            current = candidate
            idxs = idxs + [i]
    if current:
        chunks.append((current, idxs))
    return chunks


def chunk_offers(header: str, offer_blocks: list[str]) -> list[str]:
    """Split offer_blocks into Telegram messages of ≤4096 chars each.

    Never splits a single offer block across two messages. The header appears on
    the first chunk only. If a single block exceeds 4096 chars by itself, it still
    gets its own chunk (no truncation — D-06: never split mid-offer).

    Invariant: every offer block appears in exactly one chunk, intact. This
    guarantee is required by the per-chunk mark_seen logic in send_digest (D-11).

    Thin wrapper over chunk_offers_with_indices that drops the index metadata;
    kept with its original signature/behavior because other code and tests depend
    on the plain list[str] return.
    """
    return [text for text, _idxs in chunk_offers_with_indices(header, offer_blocks)]


# ---------------------------------------------------------------------------
# Subject + header builders
# ---------------------------------------------------------------------------

def build_subject(n: int) -> str:
    """Build email subject: 'BuscadorDeEmpleo: N nuevas ofertas (DD/MM)'."""
    return f"BuscadorDeEmpleo: {n} nuevas ofertas ({datetime.now().strftime('%d/%m')})"


def build_telegram_header(n: int) -> str:
    """Build Telegram digest header line with offer count."""
    return f"\U0001f514 {n} nuevas ofertas"
