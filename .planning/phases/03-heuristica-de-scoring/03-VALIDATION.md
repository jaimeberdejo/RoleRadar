---
phase: 3
slug: heuristica-de-scoring
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-22
---

# Phase 3 — Validation Strategy

> Per-phase validation contract. This is the NÚCLEO — the heuristic deserves exhaustive deterministic tests.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (configured in Phase 1) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/scoring -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5 seconds (LLM mocked; deterministic layer needs no LLM at all) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/scoring -q`
- **After every plan wave:** `uv run pytest -q`
- **Before verify:** Full suite green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|-------------|-----------|-------------------|--------|
| (planner fills) | 1 | profile loader | unit | `uv run pytest tests/scoring -q` | ⬜ pending |
| (planner fills) | 1 | SCORE-02 (decay) | unit | `uv run pytest tests/scoring -q` | ⬜ pending |
| (planner fills) | 1 | SCORE-03 (location) | unit | `uv run pytest tests/scoring -q` | ⬜ pending |
| (planner fills) | 2 | SCORE-01,04,06,07,08 (LLM assess + assemble) | unit | `uv run pytest tests/scoring -q` | ⬜ pending |
| (planner fills) | 2/3 | SCORE-05 + QA-04 (deal-breaker skip, weighted total, bands) | unit | `uv run pytest tests/scoring -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/scoring/` directory + `__init__.py`
- [ ] conftest fixtures: mocked scoring LLM client returning a controlled `LLMJobAssessment`; sample `UserProfile` (or load real profile.yaml); sample `CVProfile`; sample `Job`s (remote / onsite-Barcelona / onsite-Madrid / out-of-ranking)
- [ ] No new deps (instructor/anthropic/pyyaml already installed)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Calidad real del juicio del LLM (sub-scores skills/seniority, reasons honestos) contra ofertas reales | SCORE-01,04,07 | Requiere clave Anthropic + ofertas reales; tests mockean el LLM | Tras la fase: con ANTHROPIC_API_KEY, puntuar ofertas reales y revisar que reasons_against/missing_requirements son honestos y útiles |

*Deterministic layer (decay, location, weighted total, recommendation bands, deal-breaker override) is FULLY automated — that is the core of QA-04.*

---

## Validation Sign-Off

- [ ] All deterministic heuristic behaviors have automated tests (decay monotonic, location rules, weighted total exact, bands, deal-breaker→skip)
- [ ] LLM always mocked; zero network in tests
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
