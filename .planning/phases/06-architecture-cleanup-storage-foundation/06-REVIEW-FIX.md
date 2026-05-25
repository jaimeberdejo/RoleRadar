---
phase: 06-architecture-cleanup-storage-foundation
fixed_at: 2026-05-25T01:50:00Z
review_path: .planning/phases/06-architecture-cleanup-storage-foundation/06-REVIEW.md
iteration: 1
findings_in_scope: 6
fixed: 4
skipped: 2
status: partial
---

# Phase 6: Code Review Fix Report

**Fixed at:** 2026-05-25T01:50:00Z
**Source review:** .planning/phases/06-architecture-cleanup-storage-foundation/06-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 6 (4 Warnings + 2 Info)
- Fixed: 4 (WR-01, IN-01, WR-02, WR-03)
- Skipped/Deferred: 2 (WR-04, IN-02)

**Test result:** 163 passed, 0 failed (uv run pytest -q)

---

## Fixed Issues

### WR-01: `docker compose up` crashes `ui` service — `ui/app.py` does not exist

**Files modified:** `ui/app.py` (new file), `docker-compose.yml`
**Commit:** 4d8ec41
**Applied fix:** Created `ui/app.py` as a minimal Streamlit stub that imports streamlit and displays a "BuscadorDeEmpleo — UI en construcción (Fase 10)" message. The container now starts cleanly instead of crash-looping. The `RUN mkdir -p ui` placeholder in the Dockerfile is left as-is (the COPY of app.py to `./` makes the directory creation redundant but harmless).

---

### IN-01: `worker` depends on `ui` but only shares the SQLite volume

**Files modified:** `docker-compose.yml`
**Commit:** 4d8ec41 (same commit as WR-01 — both changes affect compose stack)
**Applied fix:** Removed `depends_on: ui` from the `worker` service. Added an explanatory comment: worker and ui are independent SQLite consumers that must start independently. This unblocks Phase 8, which requires the worker to run without the ui container.

---

### WR-02: Worker hardcodes `hours=6` — diverges from `schedule_interval_hours` DB setting

**Files modified:** `worker.py`
**Commit:** 10cae67
**Applied fix:** Replaced the hardcoded `hours=6` with a DB read inside the `if __name__ == "__main__":` block. Uses `get_storage_backend().get_settings()` to fetch `schedule_interval_hours`, converts to int, and passes to the scheduler. Wraps the read in a try/except with a fallback to 6 and a `logger.warning` so the container starts cleanly even if the DB is not yet initialised. The `run_pipeline()` stub is unchanged.

---

### WR-03: `set_setting()` docstring first sentence contradicts the implementation

**Files modified:** `app/storage/sqlite.py`
**Commit:** b41f47d
**Applied fix:** Rewrote the misleading first sentence ("INSERT OR IGNORE semántica: INSERT OR IGNORE solo para defaults (init_db)") to accurately state: "Usa ON CONFLICT(key) DO UPDATE para sobreescribir el valor existente." Added a clarifying contrast with `init_db()` which uses INSERT OR IGNORE to preserve user-configured values.

---

## Skipped / Deferred Issues

### WR-04: `get_settings()` returns raw strings — no sum validation before use

**File:** `app/storage/sqlite.py:192-200`
**Reason:** Deferred to Phase 7 (Embeddings-First Scoring Refactor). The weights are not consumed in Phase 6 — the pipeline is a stub. The correct place to add `PesosScoring.check_sum` validation is the caller that assembles `PesosScoring` from DB settings, which is Phase 7 work. Fixing it here would be premature (the caller does not exist yet).
**Original issue:** `get_settings()` returns score weights as raw strings; no validation that they sum to 1.0 when loaded from DB, unlike the profile.yaml path which goes through `PesosScoring.check_sum`.

---

### IN-02: `score_json TEXT` column has no `NOT NULL` constraint

**File:** `app/storage/sqlite.py:77`
**Reason:** Deferred — info-level schema hardening. The invariant is currently enforced by the `upsert_scored_jobs` code path which always supplies a non-null `score_json`. Adding `NOT NULL` would require a schema migration (SQLite ALTER TABLE does not support adding a NOT-NULL column without a default directly). This is a safe deferral: no data loss risk today, and the migration is straightforward when taken up.
**Original issue:** `score_json TEXT` without NOT NULL could silently drop rows in `get_history()` if a NULL value somehow appeared in the DB.

---

_Fixed: 2026-05-25T01:50:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
