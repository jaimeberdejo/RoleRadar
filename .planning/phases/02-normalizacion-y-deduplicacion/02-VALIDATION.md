---
phase: 2
slug: normalizacion-y-deduplicacion
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-22
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already configured in Phase 1) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/dedup -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5 seconds (embeddings mocked via FakeEmbedder, no torch/model load) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/dedup -q`
- **After every plan wave:** `uv run pytest -q`
- **Before verify:** Full suite green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|-------------|-----------|-------------------|--------|
| (planner fills) | 1 | NORM-01..04 | unit | `uv run pytest tests/dedup -q` | ⬜ pending |
| (planner fills) | 1 | DEDUP-01..03 | unit | `uv run pytest tests/dedup -q` | ⬜ pending |
| (planner fills) | 2 | QA-02, QA-03 | unit/integration | `uv run pytest tests/dedup -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/dedup/` directory + `__init__.py`
- [ ] conftest fixtures: `FakeEmbedder` (deterministic vectors, no torch), example raw payloads per source (arbeitnow, generic, malformed)
- [ ] dep installed: `sentence-transformers` (core, lazy-imported), `numpy` (transitive)

*Phase 1 already created pytest config + tests/ tree, so Wave 0 here is light.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Calidad real del matching semántico BGE-M3 | DEDUP-02 | Requiere descargar el modelo (~2.3GB) + datos reales; tests usan FakeEmbedder | Tras la fase: instanciar `BgeM3Embedder` real y comprobar que duplicados reales agrupan bien |
| Mappers afinados contra respuestas reales de las APIs | NORM-03 | Formatos reales solo verificables con datos en vivo de n8n | El usuario ajusta los mappers contra payloads reales |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Tests NEVER download the BGE-M3 model (FakeEmbedder only)
- [ ] No watch-mode flags
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
