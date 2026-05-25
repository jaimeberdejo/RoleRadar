"""Guard tests: the entry points load .env so local runs honor secrets.

The app reads secrets (RAPIDAPI_KEY, OPENAI_API_KEY, TELEGRAM_*, SMTP_*) from os.environ
at call time. In Docker `env_file: .env` injects them, but a local `streamlit run ui/app.py`
or `python worker.py` only sees them if an entry point calls load_dotenv(). These guards
prevent a regression where .env is silently ignored locally (the documented DOC-04 flow).

load_dotenv lives in the entry points (ui/app.py, worker.py), NOT in app/ core — core stays
import-clean (no dotenv/streamlit dependency).
"""
from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def test_ui_app_calls_load_dotenv():
    src = (_ROOT / "ui" / "app.py").read_text(encoding="utf-8")
    assert "load_dotenv()" in src, "ui/app.py must call load_dotenv() so local .env is honored"
    assert "from dotenv import load_dotenv" in src


def test_worker_calls_load_dotenv():
    src = (_ROOT / "worker.py").read_text(encoding="utf-8")
    assert "load_dotenv()" in src, "worker.py must call load_dotenv() so local .env is honored"
    assert "from dotenv import load_dotenv" in src


def test_core_does_not_import_dotenv():
    """app/ core must stay import-clean — dotenv belongs to the entry points only."""
    for py in (_ROOT / "app").rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "import dotenv" not in src and "from dotenv" not in src, (
            f"{py.relative_to(_ROOT)} imports dotenv — keep it in entry points (ui/app.py, worker.py)"
        )


def test_load_dotenv_mechanism_reads_env_file(tmp_path, monkeypatch):
    """The mechanism works: load_dotenv populates os.environ from a .env file."""
    from dotenv import load_dotenv

    env = tmp_path / ".env"
    env.write_text("RAPIDAPI_KEY=test-key-12345\n", encoding="utf-8")
    monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
    load_dotenv(dotenv_path=env)
    assert os.environ.get("RAPIDAPI_KEY") == "test-key-12345"
