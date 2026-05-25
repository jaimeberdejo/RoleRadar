---
phase: 9
slug: notifications-digest
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-25
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml ([tool.pytest.ini_options]) |
| **Quick run command** | `python -m pytest tests/notifications/ tests/storage/ -q` |
| **Full suite command** | `python -m pytest -q` |
| **Estimated runtime** | ~5 seconds (259 tests baseline) |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/notifications/ tests/storage/ -q`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _to be filled by planner_ | | | NOTIF-01/02/03 | | | unit | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/notifications/` — package + RED guard stubs for NOTIF-01/02/03 (digest filter, channel resolution, mark-seen-after-delivery)
- [ ] `tests/storage/test_undelivered.py` — guard for `get_undelivered_qualifying`
- [ ] Existing pytest infrastructure covers the rest (no framework install needed)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Telegram message renders correctly in the Telegram app | NOTIF-01 | Requires a live bot token + chat; auto-tests mock the HTTP layer | Set TELEGRAM_BOT_TOKEN/CHAT_ID, trigger a run with ≥1 qualifying job, confirm the message arrives with title/company/score/reasons/URL |
| Real SMTP email arrives + renders | NOTIF-02 | Requires live SMTP creds; auto-tests mock smtplib | Set SMTP_* (no Telegram), trigger a run, confirm the digest email arrives |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
