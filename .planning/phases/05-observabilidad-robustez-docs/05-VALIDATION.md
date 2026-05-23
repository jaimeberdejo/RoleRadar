---
phase: 5
slug: observabilidad-robustez-docs
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-23
---

# Phase 5 — Validation Strategy

> Final phase: observability (logging + Langfuse stub), error handling by layer, and docs.
> Everything testable stays zero-network; docs verified by example-JSON acceptance tests.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + FastAPI TestClient |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/obs tests/api -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~1-2 seconds (LLM/embedder mocked; langfuse absent → no-op path; no network) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/obs tests/api -q`
- **After every plan wave:** `uv run pytest -q`
- **Before verify:** Full suite green
- **Max feedback latency:** ~2 seconds

---

## Per-Task Verification Map

| Task ID | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|-------------|-----------|-------------------|--------|
| 05-01-T2 | 1 | OBS-01 (configure_logging idempotente, formato key=value) | unit | `uv run pytest tests/obs/test_logging.py -q` | ⬜ pending |
| 05-01-T3 | 1 | OBS-02 (tracing stub no-op por defecto, langfuse-free import) | unit | `uv run pytest tests/obs/test_tracing.py -q` | ⬜ pending |
| 05-02-T1 | 2 | OBS-01/OBS-02 (llm_calls counter + envolver call sites con trace_llm) | integration | `uv run pytest tests/scoring tests/cv tests/api/test_process.py -q` | ⬜ pending |
| 05-02-T2 | 2 | OBS-03 (excepciones por capa + handlers, sin stack-trace leak) | integration | `uv run pytest tests/api/test_exception_handlers.py -q` | ⬜ pending |
| 05-03-T1 | 3 | DOC-03 (examples/*.json válidos + aceptados por /jobs/process) | integration | `uv run pytest tests/api/test_examples.py -q` | ⬜ pending |
| 05-03-T2 | 3 | DOC-01, DOC-02 (README portfolio + sección n8n con JSON exacto) | doc | `uv run pytest -q` (sin regresiones) + grep secciones README | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/obs/` directory + `__init__.py`
- [ ] no new REQUIRED deps (langfuse is OPTIONAL — never imported unless installed+configured)
- [ ] tests verify the langfuse-absent no-op path is the default (the CI/dev case)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Trazas reales en Langfuse | OBS-02 | Requiere cuenta Langfuse + claves + `pip install langfuse`; aquí solo el stub no-op | (v2/OBS-04) configurar LANGFUSE_* y ver spans en el dashboard |
| README/n8n: seguir la guía end-to-end con n8n real | DOC-01/02 | Requiere instancia n8n + APIs de empleo reales | Seguir la sección "Integración con n8n" del README con un n8n real |

*Logging counters, exception-handler JSON, tracing no-op, and example-JSON acceptance are FULLY automated.*

---

## Validation Sign-Off

- [ ] trace_llm is a transparent no-op when langfuse absent/unconfigured (tested) and never breaks scoring
- [ ] /jobs/process emits structured counters incl. llm_calls (tested via caplog)
- [ ] per-layer exceptions map to clean JSON envelopes with correct HTTP codes (tested); no stack-trace leakage
- [ ] examples/*.json validate and are accepted by /jobs/process (mocked LLM/embedder)
- [ ] README has install/.env/profile/CV/run/tests + a dedicated n8n section with exact /jobs/process JSON
- [ ] app still imports torch-free; tests zero-network; full suite green
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
