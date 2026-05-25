"""Pure, testable helpers for the Settings page — no Streamlit imports.

Extracted from ui/pages/settings.py so the weight-validation logic and
channel-status checks are unit-testable without a running Streamlit runtime.

Security (T-10-06-01 / T-10-06-02):
  - channel_status() returns booleans derived from env-var presence only.
    It NEVER returns the secret values themselves (TELEGRAM_BOT_TOKEN,
    SMTP_PASSWORD, OPENAI_API_KEY are never read beyond bool(os.getenv(...))).
  - validate_and_pack_weights() constructs PesosScoring to run the
    sum-to-1.0 validator BEFORE any set_setting() call (T-10-06-02).

Public API:
  validate_and_pack_weights(puesto, skills, ubicacion, seniority)
      -> (True, mapping)  on success (mapping keys: score_weight_*)
      -> (False, error_msg)  if weights do not sum to 1.0

  pack_deal_breakers(items: list[str]) -> str
      JSON-encodes a list of deal-breaker strings (strips whitespace, drops blanks).

  channel_status() -> dict[str, bool]
      Returns {"telegram": bool, "email": bool, "openai": bool} from env presence.
"""
from __future__ import annotations

import json
import os

from pydantic import ValidationError

from app.models.schemas import PesosScoring


def validate_and_pack_weights(
    puesto: float,
    skills: float,
    ubicacion: float,
    seniority: float,
) -> tuple[bool, dict[str, str] | str]:
    """Validate that the four scoring weights sum to 1.0 via PesosScoring.

    Uses PesosScoring's @model_validator (check_sum) to enforce the 1e-6
    tolerance — the same validator used by the worker and profile overlay
    (D-08 / T-10-06-02).

    Returns:
        (True, mapping)   if weights are valid.
            mapping keys are score_weight_puesto/skills/ubicacion/seniority.
        (False, error_msg)  if the validator raises ValidationError.
            error_msg starts with "Los pesos deben sumar 1.0 (suman X)."
    """
    try:
        PesosScoring(puesto=puesto, skills=skills, ubicacion=ubicacion, seniority=seniority)
    except ValidationError:
        total = round(puesto + skills + ubicacion + seniority, 4)
        return False, f"Los pesos deben sumar 1.0 (suman {total})."
    return True, {
        "score_weight_puesto": str(puesto),
        "score_weight_skills": str(skills),
        "score_weight_ubicacion": str(ubicacion),
        "score_weight_seniority": str(seniority),
    }


def pack_deal_breakers(items: list[str]) -> str:
    """Encode a list of deal-breaker strings as a JSON string.

    Strips leading/trailing whitespace from each item and drops blank entries.
    The result is always a valid JSON array — parseable by json.loads() back to
    the same list.

    Args:
        items: List of deal-breaker strings (may include empty strings / whitespace).

    Returns:
        JSON string, e.g. '["exige 5+ años", "presencial fuera de Barcelona"]'.
    """
    return json.dumps([s.strip() for s in items if s.strip()])


def channel_status() -> dict[str, bool]:
    """Return presence booleans for notification channel secrets.

    Reads TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SMTP_HOST, SMTP_USER,
    SMTP_PASSWORD, and OPENAI_API_KEY from the environment — but returns ONLY
    booleans (never the secret values themselves). This satisfies T-10-06-01.

    Returns:
        dict with keys "telegram", "email", "openai" — each is a bool.
        True  → all required env vars for that channel are non-empty.
        False → at least one required var is missing or empty.
    """
    return {
        "telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID")),
        "email": (
            bool(os.getenv("SMTP_HOST"))
            and bool(os.getenv("SMTP_USER"))
            and bool(os.getenv("SMTP_PASSWORD"))
        ),
        "openai": bool(os.getenv("OPENAI_API_KEY")),
    }
