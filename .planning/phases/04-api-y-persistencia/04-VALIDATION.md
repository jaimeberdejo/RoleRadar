---
phase: 4
slug: api-y-persistencia
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
completed: 2026-05-23
---

# Phase 4 — Validation Strategy

> Per-phase validation contract. API + persistence wiring; everything tested with FastAPI TestClient and dependency_overrides (zero network).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + FastAPI TestClient (httpx) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/api tests/storage -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~1 second (LLM + embedder mocked via dependency_overrides; temp SQLite; no network) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/api tests/storage -q`
- **After every plan wave:** `uv run pytest -q`
- **Before verify:** Full suite green
- **Max feedback latency:** ~1 second

---

## Per-Task Verification Map

| Task ID | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|-------------|-----------|-------------------|--------|
| 04-01-T1 | 1 | API skeleton + /health + deps | infra | `uv run pytest tests/api -q` | ✅ green |
| 04-02-T1 | 1 | STORE-01..03 (SQLiteStorage) | unit | `uv run pytest tests/storage -q` | ✅ green |
| 04-03-T1..T4 | 2 | API-01,02,03,05 (cv/profile/normalize/score) | integration | `uv run pytest tests/api -q` | ✅ green |
| 04-04-T1..T3 | 3 | API-04,06,07 (process + history + ya_visto) | integration | `uv run pytest tests/api/test_process.py -q` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] deps: `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx` (httpx required for TestClient)
- [x] `tests/api/` + `tests/storage/` directories + `__init__.py`
- [x] conftest fixtures: TestClient with dependency_overrides (mock LLM client for cv+scoring, FakeEmbedder for dedup), FakeStorage functional (populates _seen+_jobs), sample PDF + sample raw offers

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Servicio real arrancable end-to-end con uvicorn | API-01..07 | Tests usan TestClient; arranque real con uvicorn es manual | `uv run uvicorn app.api.main:app --reload` y golpear /health, /docs |

*SQLite persistence + ya_visto + all endpoint contracts are FULLY automated via TestClient.*

---

## Validation Sign-Off

- [x] Every endpoint has a happy-path + error test
- [x] /jobs/process e2e tested with mocked LLM+embedder + FakeStorage functional (order, ya_visto on 2nd run, persistence, errors)
- [x] SQLiteStorage unit-tested (upsert preserves first_seen, was_seen, history)
- [x] App imports without torch; tests never hit network or download BGE-M3
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** 2026-05-23 — 161 tests passing, 0 failures

---

## Full Suite Result (2026-05-23)

```
uv run pytest -q
161 passed, 5 warnings in 0.81s
```

All Phases 1–4 green. Zero network. Zero torch at collection time.
