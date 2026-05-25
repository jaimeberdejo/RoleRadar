---
phase: 10
slug: streamlit-ui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-25
---

# Phase 10 — Validation Strategy

> Per-phase validation contract. Streamlit UI logic is pushed into testable core helpers
> (overlay, rescore, next-run calc, run-status state, weight validation) so pytest covers the
> behavior; AppTest provides page-render smoke tests only.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (+ streamlit.testing.v1.AppTest for smoke tests) |
| **Config file** | pyproject.toml ([tool.pytest.ini_options]) |
| **Quick run command** | `python -m pytest tests/ui/ tests/test_pipeline.py tests/storage/ -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** `python -m pytest tests/ui/ -q`
- **After every plan wave:** `python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green
- **Max feedback latency:** 12 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 10-01-T1a | 10-01 | 0 | UI-05, UI-06 (D-07) | unit | `python -m pytest tests/ui/test_profile_overlay.py -q` | ❌ red |
| 10-01-T1b | 10-01 | 0 | UI-09 (SC6) | unit | `python -m pytest tests/ui/test_status_helpers.py -q` | ❌ red |
| 10-01-T2a | 10-01 | 0 | UI-08 (D-09) | unit | `python -m pytest tests/ui/test_rescore.py -q` | ❌ red |
| 10-01-T2b | 10-01 | 0 | UI-08 (remote field) | unit | `python -m pytest tests/ui/test_storage_remote_field.py -q` | ❌ red |
| 10-01-T2c | 10-01 | 0 | UI-06 (deal_breakers default) | unit | `python -m pytest tests/ui/test_deal_breakers_setting.py -q` | ❌ red |

> Rows for Wave 1–4 plans will be appended by their respective plan executors.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/ui/` — package + RED guard stubs for the testable core helpers:
      build_effective_profile (settings→UserProfile overlay), rescore_stored(), next-run
      calculation, run-status state machine, weight-sum validation.
- [x] Guard for the `get_history` `remote`-field fix (RESEARCH finding #5) and the new
      `deal_breakers` settings default.
- [x] Existing pytest infra covers the rest (no framework install — streamlit already a dep).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CV upload renders extracted profile in-browser | UI-01 | Visual / file-upload widget | Run `streamlit run ui/app.py`, upload a real CV, confirm profile renders + reload doesn't re-parse |
| "Run now" stays responsive (no freeze) + live status | UI-07/SC4 | Background-thread timing not deterministic in AppTest | Click Run now, confirm spinner + UI stays interactive, results refresh on completion |
| BGE-M3 not reloaded on interaction | UI-10/SC7 | Requires observing model-load logs across interactions | Interact across pages, confirm no repeated model-load log lines |
| Scheduler status reflects real worker runs | UI-09 | Needs the worker process running | Start worker, confirm Status page shows last/next run + counts |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (or are listed Manual-Only)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 12s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
