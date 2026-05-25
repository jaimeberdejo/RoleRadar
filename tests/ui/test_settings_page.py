"""Tests for ui/settings_logic.py — pure weight-validation and channel-status helpers.

These tests run without a Streamlit runtime (settings_logic.py has no st.* imports).

Covers:
  - validate_and_pack_weights: ok path, blocked path, float-edge-case tolerance
  - pack_deal_breakers: roundtrip JSON
  - channel_status: booleans only, never secret values; works when vars absent
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# validate_and_pack_weights
# ---------------------------------------------------------------------------


def test_valid_weights_pack():
    """Default weights (0.35/0.30/0.20/0.15) → ok=True + packed mapping."""
    from ui.settings_logic import validate_and_pack_weights

    ok, payload = validate_and_pack_weights(0.35, 0.30, 0.20, 0.15)
    assert ok is True
    assert isinstance(payload, dict)
    # str(0.35) == "0.35", str(0.30) == "0.3", str(0.20) == "0.2", str(0.15) == "0.15"
    assert float(payload["score_weight_puesto"]) == pytest.approx(0.35)
    assert float(payload["score_weight_skills"]) == pytest.approx(0.30)
    assert float(payload["score_weight_ubicacion"]) == pytest.approx(0.20)
    assert float(payload["score_weight_seniority"]) == pytest.approx(0.15)
    # The mapping keys must be the score_weight_* settings keys
    assert set(payload.keys()) == {
        "score_weight_puesto",
        "score_weight_skills",
        "score_weight_ubicacion",
        "score_weight_seniority",
    }


def test_invalid_weights_blocked():
    """Weights that do not sum to 1.0 → ok=False + Spanish error message."""
    from ui.settings_logic import validate_and_pack_weights

    ok, msg = validate_and_pack_weights(0.5, 0.3, 0.2, 0.2)
    assert ok is False
    assert isinstance(msg, str)
    assert msg.startswith("Los pesos deben sumar 1.0")


def test_float_edge_sums_to_one():
    """Weights summing to 1.0 within 1e-6 tolerance → ok=True (no IEEE-754 false-positive)."""
    from ui.settings_logic import validate_and_pack_weights

    # 0.35 + 0.30 + 0.20 + 0.15 = 1.0 in PesosScoring validator (allow 1e-6 drift)
    ok, _payload = validate_and_pack_weights(0.35, 0.30, 0.20, 0.15)
    assert ok is True


def test_all_zero_weights_blocked():
    """All-zero weights → sum=0 → blocked."""
    from ui.settings_logic import validate_and_pack_weights

    ok, msg = validate_and_pack_weights(0.0, 0.0, 0.0, 0.0)
    assert ok is False
    assert "0" in msg  # message contains the bad sum


# ---------------------------------------------------------------------------
# pack_deal_breakers
# ---------------------------------------------------------------------------


def test_pack_deal_breakers_roundtrip():
    """pack_deal_breakers strips blanks and blank entries; roundtrips via json.loads."""
    from ui.settings_logic import pack_deal_breakers

    result = pack_deal_breakers(["a", " b ", "", "c"])
    loaded = json.loads(result)
    assert loaded == ["a", "b", "c"]


def test_pack_deal_breakers_empty_list():
    """Empty input → valid JSON empty list '[]'."""
    from ui.settings_logic import pack_deal_breakers

    result = pack_deal_breakers([])
    assert json.loads(result) == []


def test_pack_deal_breakers_only_blanks():
    """List of only whitespace/empty strings → '[]'."""
    from ui.settings_logic import pack_deal_breakers

    result = pack_deal_breakers(["", "  ", "\t"])
    assert json.loads(result) == []


# ---------------------------------------------------------------------------
# WR-02 / WR-03: settings page safe-coerce helpers (malformed persisted values)
# ---------------------------------------------------------------------------


def test_to_float_valid():
    """_to_float parses a valid numeric string."""
    from ui.pages.settings import _to_float

    assert _to_float("0.42", 0.35) == pytest.approx(0.42)


@pytest.mark.parametrize("bad", ["", "none", None, "0.3x", "  "])
def test_to_float_falls_back_on_malformed(bad):
    """WR-03: malformed persisted value falls back to default instead of raising."""
    from ui.pages.settings import _to_float

    assert _to_float(bad, 0.35) == pytest.approx(0.35)


def test_to_int_valid():
    """_to_int parses a valid integer string."""
    from ui.pages.settings import _to_int

    assert _to_int("70", 50) == 70


@pytest.mark.parametrize("bad", ["", "none", None, "7x", "  "])
def test_to_int_falls_back_on_malformed(bad):
    """WR-03: malformed persisted threshold falls back to default instead of raising."""
    from ui.pages.settings import _to_int

    assert _to_int(bad, 70) == 70


# ---------------------------------------------------------------------------
# channel_status — booleans only, NEVER secret values
# ---------------------------------------------------------------------------


def test_channel_status_never_returns_secret(monkeypatch):
    """When all secrets are set, channel_status returns True booleans — not the secret strings."""
    from ui.settings_logic import channel_status

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot123:secret")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123456")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "hunter2")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-supersecret")

    cs = channel_status()

    # All channels configured → all True
    assert cs["telegram"] is True
    assert cs["email"] is True
    assert cs["openai"] is True

    # Values MUST be booleans — never the secret string
    for key, val in cs.items():
        assert type(val) is bool, f"channel_status[{key!r}] is {type(val).__name__}, not bool"


def test_channel_status_unset(monkeypatch):
    """When no secrets are set, all channel_status values are False."""
    from ui.settings_logic import channel_status

    for var in [
        "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
        "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(var, raising=False)

    cs = channel_status()
    assert cs["telegram"] is False
    assert cs["email"] is False
    assert cs["openai"] is False


def test_channel_status_partial_telegram(monkeypatch):
    """Telegram requires BOTH token AND chat_id; having only one → False."""
    from ui.settings_logic import channel_status

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot123:secret")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    cs = channel_status()
    assert cs["telegram"] is False


def test_channel_status_partial_email(monkeypatch):
    """Email requires SMTP_HOST + SMTP_USER + SMTP_PASSWORD; missing one → False."""
    from ui.settings_logic import channel_status

    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    cs = channel_status()
    assert cs["email"] is False
