"""Notifications package — post-pipeline digest delivery (Phase 9).

Public entry: send_digest(storage, settings) -> DigestResult.

IMPORT-CLEANLINESS (D-02): this package and its submodules import ONLY httpx +
stdlib (smtplib/email). The channel transports (telegram, email_smtp) are imported
LAZILY inside send_digest with `# noqa: PLC0415` so `import app.notifications` never
pulls streamlit or apscheduler — preserving the deferred-import wiring in app.pipeline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.notifications.digest import (
    build_subject,
    build_telegram_header,
    chunk_offers_with_indices,
    format_offer_block,
    resolve_channel,
)

logger = logging.getLogger(__name__)

QUALIFYING_RECOMMENDATIONS = ["strong_fit", "good_fit"]


@dataclass
class DigestResult:
    """Result of a single send_digest call."""

    channel: str | None = None
    delivered: int = 0
    errors: list[str] = field(default_factory=list)


def send_digest(storage, settings: dict[str, str]) -> DigestResult:
    """Query undelivered qualifying jobs, send to the resolved channel, mark seen on success.

    Sequence (D-10):
      1. min_score = int(settings.notification_min_score, default 70)
      2. jobs = storage.get_undelivered_qualifying(min_score, ["strong_fit","good_fit"])
      3. if not jobs → return DigestResult(delivered=0)
      4. channel = resolve_channel(settings); if None → log, return (NO mark_seen)
      5. send; on per-job success → storage.mark_seen(job_id); on failure → record error

    Never raises (callable from run_pipeline's try/except — D-13).
    """
    result = DigestResult()
    try:
        min_score = int(settings.get("notification_min_score", "70"))
    except (TypeError, ValueError):
        logger.warning("notification_min_score invalid — falling back to 70")
        min_score = 70

    jobs = storage.get_undelivered_qualifying(min_score, QUALIFYING_RECOMMENDATIONS)
    if not jobs:
        logger.info("send_digest: no undelivered qualifying jobs")
        return result

    channel = resolve_channel(settings)
    result.channel = channel
    if channel is None:
        # silent skip — backlog preserved (NOT marked seen) for when a channel is configured
        return result

    if channel == "telegram":
        _send_telegram(storage, jobs, result)
    elif channel == "email":
        _send_email(storage, jobs, result)

    logger.info(
        "send_digest: channel=%s delivered=%d errors=%d",
        channel,
        result.delivered,
        len(result.errors),
    )
    return result


def _send_telegram(storage, jobs, result: DigestResult) -> None:
    """Format + chunk + send jobs via Telegram. Mark seen per chunk after 200 (D-11)."""
    from app.notifications.telegram import send_telegram_digest  # noqa: PLC0415

    blocks = [format_offer_block(j) for j in jobs]
    header = build_telegram_header(len(jobs))

    # Pair each chunk text with the job_ids it contains BY BLOCK INDEX, captured at
    # chunk-construction time. Substring re-pairing (the old approach) misassigns
    # IDs when two blocks are byte-identical or one is a substring of another,
    # causing failed-chunk jobs to be marked seen (data loss) or delivered jobs to
    # never be marked (CR-01). Index pairing is sound because block i in offer_blocks
    # corresponds to jobs[i], and chunk_offers_with_indices records exactly which
    # indices each chunk holds. This guarantees D-11: a failed chunk's job_ids are
    # never added to delivered_ids → those jobs stay seen=0.
    paired = chunk_offers_with_indices(header, blocks)
    chunks: list[tuple[str, list[str]]] = [
        (text, [jobs[i].job.id for i in idxs]) for text, idxs in paired
    ]

    # Post-condition guard (WR-02): with the index pairing above every job must be
    # assigned to exactly one chunk; a mismatch would mean jobs silently never get
    # marked seen on a successful send. Should never trigger — guards regressions.
    assigned = sum(len(ids) for _text, ids in chunks)
    if assigned != len(jobs):
        logger.error(
            "telegram chunk pairing lost jobs: assigned=%d expected=%d",
            assigned,
            len(jobs),
        )

    delivered_ids, errors = send_telegram_digest(chunks)
    for jid in delivered_ids:
        storage.mark_seen(jid)
    result.delivered = len(delivered_ids)
    result.errors.extend(errors)


def _send_email(storage, jobs, result: DigestResult) -> None:
    """Format + send all jobs in one email. Mark all seen on success (D-10).

    Never raises (honors the D-13 contract): besides smtplib.SMTPException, SMTP
    delivery can fail at the transport layer with OSError (covers socket.gaierror
    DNS failures, connection refused, and TimeoutError) or ssl.SSLError during
    STARTTLS — none of which subclass SMTPException. All are caught here and
    reported via result.errors so a bad SMTP_HOST never escapes send_digest (WR-01).
    """
    import smtplib  # noqa: PLC0415
    import ssl  # noqa: PLC0415

    from app.notifications.email_smtp import send_email_digest  # noqa: PLC0415

    blocks = [format_offer_block(j) for j in jobs]
    body = (build_telegram_header(len(jobs)) + "\n\n" + "\n\n".join(blocks)).strip()
    subject = build_subject(len(jobs))
    try:
        send_email_digest(body, subject)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        logger.error("Email delivery failed: %s", exc)
        result.errors.append(f"email: {exc}")
        return
    for j in jobs:
        storage.mark_seen(j.job.id)
    result.delivered = len(jobs)
