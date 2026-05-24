---
phase: 6
slug: architecture-cleanup-storage-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-25
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/storage/ -q` |
| **Full suite command** | `uv run pytest -q` (tests/api/ deleted in this phase) |
| **Estimated runtime** | ~30 seconds (storage subset ~5s) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/storage/ -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 6-W0-01 | W0 | 0 | STORE-04/06 | — | N/A | unit | `uv run pytest tests/storage/test_sqlite.py -q` | ❌ W0 | ⬜ pending |
| 6-W0-02 | W0 | 0 | MIG-01 | — | no stray fastapi import | unit | `uv run pytest tests/test_import_cleanliness.py -q` | ❌ W0 | ⬜ pending |
| 6-W0-03 | W0 | 0 | MIG-03 | T-6-secret | secret not in tree | unit | `uv run pytest tests/test_no_secrets.py -q` | ❌ W0 | ⬜ pending |
| MIG-01 | — | 1 | MIG-01 | — | importing pkg loads no fastapi/uvicorn/python-multipart | unit | `uv run pytest tests/test_import_cleanliness.py::test_fastapi_not_importable_after_removal -x` | ❌ W0 | ⬜ pending |
| MIG-02 | — | 1 | MIG-02 | — | no n8n service in compose | smoke (manual) | `docker compose config \| grep -c n8n` → 0 | — manual | ⬜ pending |
| MIG-03 | — | 1 | MIG-03 | T-6-secret | no literal RAPIDAPI_KEY in any committed file | unit | `uv run pytest tests/test_no_secrets.py::test_docker_compose_no_literal_rapidapi_key -x` | ❌ W0 | ⬜ pending |
| MIG-04 | — | 1 | MIG-04 | — | ui + worker services, same image, shared volumes | smoke (manual) | `docker compose config` | — manual | ⬜ pending |
| STORE-04 | — | 1 | STORE-04 | — | get_settings() returns all default keys | unit | `uv run pytest tests/storage/test_sqlite.py::test_get_settings_defaults -x` | ❌ W0 | ⬜ pending |
| STORE-04 | — | 1 | STORE-04 | — | set_setting roundtrip | unit | `uv run pytest tests/storage/test_sqlite.py::test_set_setting_roundtrip -x` | ❌ W0 | ⬜ pending |
| STORE-06 | — | 1 | STORE-06 | — | concurrent write+read: no OperationalError | unit | `uv run pytest tests/storage/test_sqlite.py::test_wal_concurrent_write_read_no_lock -x` | ❌ W0 | ⬜ pending |
| STORE-06 | — | 1 | STORE-06 | — | journal_mode == wal after init | unit | `uv run pytest tests/storage/test_sqlite.py::test_wal_mode_active -x` | ❌ W0 | ⬜ pending |
| DOC-05 | — | 1 | DOC-05 | — | .env.example documents v2.0 vars, no API_KEY/FastAPI vars | grep/unit | `grep -q RAPIDAPI_KEY .env.example && ! grep -q '^API_KEY=' .env.example` | — manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/storage/test_sqlite.py` — add `test_get_settings_defaults`, `test_set_setting_roundtrip`, `test_wal_mode_active`, `test_wal_concurrent_write_read_no_lock`
- [ ] `tests/test_import_cleanliness.py` — `test_fastapi_not_importable_after_removal` (import app + assert `fastapi`/`uvicorn`/`python-multipart` not in `sys.modules`)
- [ ] `tests/test_no_secrets.py` — `test_docker_compose_no_literal_rapidapi_key` (grep committed files for the leaked key pattern)
- [ ] Delete `tests/api/` (8 files, ~969 lines — depend on `fastapi.testclient`, removed with the API layer)

*Existing `tests/storage/test_sqlite.py` has passing tests; new tests extend it.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docker compose up` starts only ui + worker | MIG-02, MIG-04 | Requires Docker daemon; not run in CI/unit context | `docker compose config` shows exactly `ui` + `worker`, no `n8n`, shared `data`/`hf_cache` volumes; `docker compose up` boots both |
| `.env.example` completeness | DOC-05 | Doc review judgment (all v2.0 vars present, none stale) | Confirm RAPIDAPI_KEY, TELEGRAM_*, SMTP_*, OPENAI(optional) present; no FastAPI/API_KEY vars |
| RAPIDAPI_KEY rotation | MIG-03 | External action on RapidAPI dashboard | User rotates the leaked key out-of-band (code change only removes it from the tree) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
