# Phase 4 — Plan-checker blocker resolutions

The plan-checker (sonnet) raised 3 blockers, all in test specifications (not architecture).
Resolved at execution time via explicit executor instructions:

1. **FakeStorage no-op** (B1+B3): conftest `FakeStorage` is implemented as a FUNCTIONAL
   in-memory store — `upsert_scored_jobs` populates an internal `_seen` set + `_jobs` list;
   `was_seen` reads `_seen`; `get_history` returns `_jobs`. This lets `ya_visto` and history
   tests pass with FakeStorage (no SQLiteStorage override required), while remaining zero-network.

2. **test_process_persiste** (B1): works with the functional FakeStorage above (or a
   `SQLiteStorage(tmp_path)` override). Executors ensure history is non-empty after a process call.

3. **test_profile.py traceability** (B2): the GET /profile test lives in
   `tests/api/test_profile.py` (matching RESEARCH/VALIDATION), not `test_health.py`.

4. **dependency_overrides cleanup** (warning): tests reset `app.dependency_overrides` via a
   fixture `yield`/teardown or try/finally — no cross-test contamination.
