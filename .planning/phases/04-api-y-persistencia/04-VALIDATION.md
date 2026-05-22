---
phase: 4
slug: api-y-persistencia
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-22
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
| **Estimated runtime** | ~10 seconds (LLM + embedder mocked via dependency_overrides; temp SQLite; no network) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/api tests/storage -q`
- **After every plan wave:** `uv run pytest -q`
- **Before verify:** Full suite green
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

| Task ID | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|-------------|-----------|-------------------|--------|
| (planner fills) | 1 | deps + app skeleton + /health | infra | `uv run pytest tests/api -q` | ⬜ pending |
| (planner fills) | 1 | STORE-01..03 (SQLiteStorage) | unit | `uv run pytest tests/storage -q` | ⬜ pending |
| (planner fills) | 2 | API-01,02,03,05 (cv/profile/normalize/score) | integration | `uv run pytest tests/api -q` | ⬜ pending |
| (planner fills) | 3 | API-04,06,07 (process orchestration + history + ya_visto) | integration | `uv run pytest tests/api -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] deps: `fastapi`, `uvicorn[standard]`, `python-multipart`, `httpx` (httpx required for TestClient)
- [ ] `tests/api/` + `tests/storage/` directories + `__init__.py`
- [ ] conftest fixtures: TestClient with dependency_overrides (mock LLM client for cv+scoring, FakeEmbedder for dedup), temp SQLite Storage (tmp_path), sample PDF + sample raw offers

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Servicio real arrancable end-to-end con uvicorn | API-01..07 | Tests usan TestClient; arranque real con uvicorn es manual | `uv run uvicorn app.api.main:app --reload` y golpear /health, /docs |
| Persistencia real en Supabase (pgvector) | STORE-01 | Skeleton ahora; requiere proyecto Supabase real | Configurar SUPABASE_URL/KEY y verificar selección + escritura cuando se conecte |

*SQLite persistence + ya_visto + all endpoint contracts are FULLY automated via TestClient.*

---

## Validation Sign-Off

- [ ] Every endpoint has a happy-path + error test
- [ ] /jobs/process e2e tested with mocked LLM+embedder + temp SQLite (order, ya_visto on 2nd run, persistence, errors)
- [ ] SQLiteStorage unit-tested (upsert preserves first_seen, was_seen, history)
- [ ] App imports without torch; tests never hit network or download BGE-M3
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
