---
phase: 1
slug: parseo-de-cv
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-22
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none — Wave 0 creates `pytest.ini` (or `[tool.pytest.ini_options]` in pyproject) |
| **Quick run command** | `uv run pytest tests/cv -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5 seconds (LLM mocked, no network) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/cv -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| (planner fills) | 01 | 0 | QA-01 | infra | `uv run pytest --collect-only` | ❌ W0 | ⬜ pending |
| (planner fills) | — | 1 | CV-01 | unit | `uv run pytest tests/cv -q` | ❌ W0 | ⬜ pending |
| (planner fills) | — | 1 | CV-02 | unit | `uv run pytest tests/cv -q` | ❌ W0 | ⬜ pending |
| (planner fills) | — | 1 | CV-03 | unit | `uv run pytest tests/cv -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pytest.ini` (or pyproject pytest config) — pytest discovery
- [ ] `tests/conftest.py` — shared fixtures (incl. PDF fixture builder via pymupdf, mocked instructor client)
- [ ] `tests/cv/` — directory for CV parsing tests
- [ ] `tests/fixtures/` — sample CV PDF
- [ ] deps installed: `pymupdf`, `instructor`, `anthropic`, `python-dotenv`, `pytest`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Calidad real de extracción contra el CV verdadero de Jaime | CV-01 | Requiere el PDF real + clave Anthropic; los tests mockean el LLM | Tras la fase: `ANTHROPIC_API_KEY` en .env, ejecutar el parser contra el CV real y revisar el CVProfile resultante |

*Automated tests cover wiring (extracción + parseo + caché); LLM output quality is manual.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
