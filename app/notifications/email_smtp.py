"""Email digest sender via stdlib smtplib + email.message (STARTTLS).

Credentials read from env, never logged (D-04/T-09-06). One plain-text email per run (D-07).

SECURITY NOTE (T-09-08 email header injection guard):
- job title/company/url are placed in the body via `msg.set_content(body)` ONLY.
  They are NEVER assigned to msg["Subject"], msg["To"], or any other header.
- Subject is built by build_subject(n) which contains only a count + date — no attacker data.
- To/From are env-derived addresses (SMTP_USER, SMTP_TO) — not job data.
- EmailMessage.set_content also rejects embedded newlines in the body-to-header path
  (defense in depth via stdlib).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

DEFAULT_SMTP_PORT = 587


def send_email_digest(body: str, subject: str) -> None:
    """Send one plain-text digest email. Raises smtplib.SMTPException on failure.

    Reads SMTP_HOST/PORT/USER/PASSWORD (+ optional SMTP_TO) from env at call time,
    never at module level (D-04). To defaults to SMTP_USER (self-send) when SMTP_TO
    is unset.

    The caller (send_digest in __init__.py) marks jobs seen ONLY after this function
    returns without exception (D-10/D-11).

    Args:
        body:    Plain-text email body (formatted offer blocks — never used in headers).
        subject: Email subject from build_subject(n) — count + date only, no attacker data.
    """
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT") or DEFAULT_SMTP_PORT)
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    # SMTP_TO is an optional self-send override (documented in .env.example)
    to_addr = os.environ.get("SMTP_TO") or user

    msg = EmailMessage()
    msg["Subject"] = subject          # count+date only — no attacker data (T-09-08)
    msg["From"] = user                # env-derived address
    msg["To"] = to_addr               # env-derived address (SMTP_TO or SMTP_USER)
    msg.set_content(body)             # body only — job data never in headers (T-09-08)

    with smtplib.SMTP(host, port) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, password)    # password read from env; never logged (D-04)
        smtp.send_message(msg)
    # Log To address (not a secret) but never the password (T-09-06)
    logger.info("Email digest sent to %s", to_addr)
