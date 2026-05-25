# Phase 9: Notifications & Digest - Pattern Map

**Mapped:** 2026-05-25
**Files analyzed:** 9 (7 new, 2 modified)
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `app/notifications/__init__.py` | service orchestrator | request-response | `app/pipeline.py` | role-match (same deferred-import + try/except + result dataclass pattern) |
| `app/notifications/telegram.py` | service (HTTP client) | request-response | `app/sources/jsearch.py` | exact (same sync httpx.Client, per-call error isolation, env-key reading) |
| `app/notifications/email_smtp.py` | service (SMTP client) | request-response | `app/sources/jsearch.py` | role-match (same error-isolation contract; transport is stdlib SMTP not httpx) |
| `app/notifications/digest.py` | utility | transform | `app/pipeline.py` (helper functions) | partial (pure helpers + channel resolution logic is new; formatting is transform) |
| `app/storage/sqlite.py` | storage (modify) | CRUD | itself | self-referential (add `get_undelivered_qualifying` mirroring `get_history`) |
| `app/storage/protocol.py` | protocol (modify) | CRUD | itself | self-referential (add one method declaration mirroring existing stubs) |
| `app/pipeline.py` | orchestrator (modify) | request-response | itself | self-referential (add step 11 using deferred-import + try/except already in file) |
| `tests/notifications/__init__.py` | test package init | — | `tests/sources/__init__.py` | exact (empty init) |
| `tests/notifications/test_notifications.py` | test | — | `tests/sources/test_jsearch.py` + `tests/test_pipeline.py` | exact (same mock strategy: `patch("app.notifications.telegram.httpx.Client")` + import-cleanliness pattern) |

---

## Pattern Assignments

### `app/notifications/telegram.py` (service, request-response)

**Analog:** `app/sources/jsearch.py`

**Imports pattern** (`jsearch.py` lines 1–23):
```python
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

JSEARCH_BASE = "https://jsearch.p.rapidapi.com/search"
DEFAULT_TIMEOUT = 20.0
```
For `telegram.py` adapt to:
```python
TELEGRAM_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT = 10.0
```

**Env-reading pattern — read inside function, never at module level** (`jsearch.py` lines 52–56):
```python
# Read key inside the function — never at module level (T-08-02).
headers = {
    "X-RapidAPI-Key": os.environ.get("RAPIDAPI_KEY", ""),
    "X-RapidAPI-Host": JSEARCH_HOST,
}
```
For `telegram.py` adapt to (same discipline, D-04 "secrets from env only, never logged"):
```python
token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
```

**Client-as-context-manager pattern** (`jsearch.py` lines 65–73):
```python
try:
    if client is None:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as _client:
            return _do_get(_client, headers, params, query)
    else:
        return _do_get(client, headers, params, query)
except httpx.HTTPError as exc:
    logger.warning("JSearch HTTP error for query=%r: %s", query, exc)
    return []
```

**Per-call error isolation pattern — non-200 handled without raise** (`jsearch.py` lines 76–106):
```python
def _do_get(client, headers, params, query) -> list[dict]:
    resp = client.get(JSEARCH_BASE, headers=headers, params=params)
    if resp.status_code == 429:
        logger.warning("JSearch 429 for query=%r — skipping", query)
        return []
    if resp.status_code in (401, 403):
        logger.error(
            "JSearch auth failure (status=%d) for query=%r — check RAPIDAPI_KEY env var",
            resp.status_code, query,
        )
        return []
    resp.raise_for_status()
    try:
        return resp.json().get("data", [])
    except (ValueError, KeyError) as exc:
        logger.warning("JSearch non-JSON response for query=%r (status=%d): %s", query, resp.status_code, exc)
        return []
```
For `telegram.py`, adapt to POST (not GET), check `resp.status_code == 200` for success (D-06), and log `resp.json().get("description")` on non-200. Return `True`/`False` not a list.

---

### `app/notifications/email_smtp.py` (service, request-response)

**Analog:** `app/sources/jsearch.py` (error-isolation contract)

**Per-call error isolation** — same discipline as jsearch: never raises, errors logged and returned as failure signal. The transport is `smtplib.SMTP` (stdlib context manager) instead of `httpx.Client`, but the outer contract is identical:
- function never raises
- on exception: log error, return False / signal failure
- on success: return True / signal success

**Context-manager usage** (mirrors `jsearch.py` `with httpx.Client(...) as _client`):
```python
# Mirrors jsearch.py's `with httpx.Client(timeout=DEFAULT_TIMEOUT) as _client:`
with smtplib.SMTP(smtp_host, smtp_port) as smtp:
    smtp.ehlo()
    smtp.starttls()
    smtp.login(smtp_user, smtp_password)
    smtp.send_message(msg)
```

**Exception hierarchy to catch** (equivalent of `httpx.HTTPError` in jsearch):
```python
except smtplib.SMTPException as exc:
    logger.error("Email delivery failed: %s", exc)
    # covers SMTPAuthenticationError, SMTPConnectError, SMTPRecipientsRefused,
    # SMTPSenderRefused, SMTPDataError, SMTPServerDisconnected
    return False
```

---

### `app/notifications/digest.py` (utility, transform)

**Analog:** `app/pipeline.py` helper functions (`_now_iso`, `_is_first_run`, `_get_cv_profile`)

**Pure-helper pattern** (no I/O, no storage, no HTTP). Functions in `digest.py` should all be stateless pure transforms — same as the `_get_cv_profile` / `_now_iso` private helpers in `pipeline.py`. The channel resolution function (`resolve_channel`) reads `os.environ` and the settings dict; no side effects.

**Settings-as-strings coercion** (`sqlite.py` comment at line 207–209, `pipeline.py` line 168):
```python
# sqlite.py comment: "Los valores numéricos se devuelven como strings — el caller hace la conversión."
# pipeline.py line 168 (same pattern):
umbral=float(settings.get("dedup_threshold", "0.85"))
# For digest.py:
min_score = int(settings.get("notification_min_score", "70"))
```

---

### `app/notifications/__init__.py` (service orchestrator, request-response)

**Analog:** `app/pipeline.py`

**Result dataclass pattern** (`pipeline.py` lines 41–49):
```python
@dataclass
class PipelineResult:
    """Counts and output from a single pipeline run."""
    fetched: int = 0
    deduped: int = 0
    scored: int = 0
    new_seen: int = 0
    errors: list[str] = field(default_factory=list)
    scored_jobs: list[ScoredJob] = field(default_factory=list)
```
For `DigestResult` in `notifications/__init__.py`, mirror this exact shape (dataclass, field(default_factory=list) for errors):
```python
@dataclass
class DigestResult:
    channel: str | None = None
    delivered: int = 0
    errors: list[str] = field(default_factory=list)
```

**Per-step error collection without re-raising** (`pipeline.py` lines 178–184):
```python
try:
    raw_jobs = _fetch_all(queries, settings)
    result.fetched = len(raw_jobs)
except Exception as exc:  # noqa: BLE001
    logger.error("_fetch_all failed: %s", exc)
    result.errors.append(f"fetch: {exc}")
    raw_jobs = []
```
`send_digest` uses the same `try/except Exception` around channel send, appending to `result.errors` (D-13).

**Deferred import pattern inside a function** (`pipeline.py` lines 80–81, 149–153, 158–162):
```python
from app.cv.cache import load_cached_profile  # noqa: PLC0415

# ...

if storage is None:
    from app.storage import get_storage_backend  # noqa: PLC0415
    storage = get_storage_backend()

if embedder is None:
    from app.dedup.embedder import BgeM3Embedder  # noqa: PLC0415
    embedder = BgeM3Embedder()

from app.config.loader import load_user_profile  # noqa: PLC0415
```
The `# noqa: PLC0415` comment is required on every deferred import. `send_digest` does NOT use deferred imports itself (it IS the deferred import target); but `telegram.py` and `email_smtp.py` are imported inside `send_digest` body with this same `# noqa: PLC0415` comment.

---

### `app/storage/sqlite.py` — add `get_undelivered_qualifying` (storage, CRUD)

**Analog:** `get_history` in same file (`sqlite.py` lines 172–203)

**Full `get_history` pattern** (`sqlite.py` lines 172–203):
```python
def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]:
    with closing(self._connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY last_seen DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    result: list[dict] = []
    for row in rows:
        try:
            score = JobScore.model_validate_json(row["score_json"])
            result.append({
                "id": row["id"],
                "title": row["title"],
                "company": row["company"],
                "score_total": row["score_total"],
                "recommendation": row["recommendation"],
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "score": score.model_dump(),
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Error deserializando oferta %s del historial: %s",
                row["id"],
                exc,
            )
    return result
```
`get_undelivered_qualifying` uses the same `with closing(self._connect())` + `fetchall()` + `JobScore.model_validate_json(row["score_json"])` + per-row try/except with `logger.warning` + skip on error. The difference: it returns `list[ScoredJob]` (not `list[dict]`) by reconstructing full objects; the SQL adds `WHERE seen=0 AND recommendation IN (?,?) AND score_total >= ?`.

**Parameterized IN clause pattern** — the codebase always uses `?` placeholders; for dynamic `IN` lists use:
```python
placeholders = ",".join("?" * len(recommendations))
# ...
f"WHERE seen=0 AND recommendation IN ({placeholders}) AND score_total >= ?"
```

**`mark_seen` pattern** (`sqlite.py` lines 285–294) — already exists, Phase 9 is its first caller:
```python
def mark_seen(self, job_id: str) -> None:
    with closing(self._connect()) as conn:
        with conn:
            conn.execute("UPDATE jobs SET seen = 1 WHERE id = ?", (job_id,))
    logger.debug("mark_seen: job_id=%s", job_id)
```

**`record_run` pattern to extend** (`sqlite.py` lines 231–261) — add `channel: str | None = None` and `notified: int = 0` optional keyword args; update the INSERT column list to include them:
```python
def record_run(
    self,
    *,
    started_at: str,
    finished_at: str,
    fetched: int,
    deduped: int,
    scored: int,
    new_seen: int,
    errors: list[str] | None = None,
) -> None:
    errors_json = json.dumps(errors) if errors else None
    with closing(self._connect()) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO runs
                    (started_at, finished_at, fetched, deduped, scored, new_seen, errors)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (started_at, finished_at, fetched, deduped, scored, new_seen, errors_json),
            )
```

**`init_db` migration pattern for new columns** — SQLite does not support `ADD COLUMN IF NOT EXISTS`; use PRAGMA check (also matches the idempotent `CREATE TABLE IF NOT EXISTS` philosophy at lines 67–116):
```python
# In init_db(), inside the 'with conn:' block, after table creation:
cursor = conn.execute("PRAGMA table_info(runs)")
col_names = [row[1] for row in cursor.fetchall()]
if "channel" not in col_names:
    conn.execute("ALTER TABLE runs ADD COLUMN channel TEXT")
if "notified" not in col_names:
    conn.execute("ALTER TABLE runs ADD COLUMN notified INTEGER DEFAULT 0")
```

---

### `app/storage/protocol.py` — add `get_undelivered_qualifying` (protocol, CRUD)

**Analog:** existing method stubs in same file (`protocol.py` lines 39–65)

**Full existing stub pattern** (`protocol.py` lines 39–65):
```python
@runtime_checkable
class Storage(Protocol):
    def init_db(self) -> None: ...

    def upsert_scored_jobs(self, scored: list[ScoredJob]) -> None: ...

    def was_seen(self, job_id: str) -> bool: ...

    def get_history(self, limit: int = 50, offset: int = 0) -> list[dict]: ...

    def get_settings(self) -> dict[str, str]: ...

    def set_setting(self, key: str, value: str) -> None: ...

    def record_run(
        self,
        *,
        started_at: str,
        finished_at: str,
        fetched: int,
        deduped: int,
        scored: int,
        new_seen: int,
        errors: list[str] | None = None,
    ) -> None: ...

    def get_recent_runs(self, limit: int = 10) -> list[dict]: ...

    def mark_seen(self, job_id: str) -> None: ...
```
Add `get_undelivered_qualifying` with the same single-line `...` body and matching type signature. Also update `record_run` stub to add the new `channel` and `notified` keyword args.

---

### `app/pipeline.py` — add step 11 (orchestrator, modify)

**Analog:** itself — the existing deferred-import + try/except pattern already used for storage, embedder, config (lines 148–162).

**Exact deferred-import + try/except wrapper pattern to replicate** (`pipeline.py` lines 148–153):
```python
if storage is None:
    from app.storage import get_storage_backend  # noqa: PLC0415
    storage = get_storage_backend()
```

**How step 11 fits after the existing step 10** (`pipeline.py` lines 244–254 — the `record_run` call and log summary):
```python
# ------------------------------------------------------------------
# 10. Record run metrics
# ------------------------------------------------------------------
finished_at = _now_iso()
storage.record_run(
    started_at=started_at,
    finished_at=finished_at,
    fetched=result.fetched,
    deduped=result.deduped,
    scored=result.scored,
    new_seen=result.new_seen,
    errors=result.errors if result.errors else None,
)
```
Step 11 goes immediately after the `record_run` call and before the structured log summary (lines 258–266). The pattern (from RESEARCH.md, mirroring existing deferred imports):
```python
# ------------------------------------------------------------------
# 11. Send digest notification (deferred import — keeps pipeline import-clean)
# ------------------------------------------------------------------
try:
    from app.notifications import send_digest  # noqa: PLC0415
    digest_result = send_digest(storage, settings)
    if digest_result.errors:
        result.errors.extend(digest_result.errors)
except Exception as exc:  # noqa: BLE001
    logger.error("send_digest failed: %s", exc)
    result.errors.append(f"notify: {exc}")
```
Note: `record_run` must also receive `channel` and `notified` from `digest_result`. Planner decision (per RESEARCH.md Open Question 3): either pass them to the existing `record_run` call or call a new `update_run_notification` helper after step 11. The simpler path is to defer `record_run` until after step 11, capturing `digest_result` first.

---

### `tests/notifications/test_notifications.py` (test)

**Analogs:** `tests/sources/test_jsearch.py` (httpx mock pattern) + `tests/test_pipeline.py` (import-cleanliness + SQLiteStorage on tmp_path)

**httpx.Client mock pattern** (`test_jsearch.py` lines 75–86):
```python
with patch("app.sources.jsearch.httpx.Client") as MockClient:
    instance = MockClient.return_value.__enter__.return_value
    instance.get.return_value = ok_resp

    result = fetch_jsearch_query(
        "AI Engineer", date_posted="3days", num_pages=1, country="es"
    )
```
For `telegram.py`, mirror exactly but patch `"app.notifications.telegram.httpx.Client"` and use `instance.post` (not `instance.get`):
```python
with patch("app.notifications.telegram.httpx.Client") as MockClient:
    instance = MockClient.return_value.__enter__.return_value
    instance.post.return_value = _make_200_response()
    # ...
```

**smtplib.SMTP mock pattern** (mirrors jsearch context manager; `smtplib.SMTP` also supports `__enter__`/`__exit__`):
```python
with patch("app.notifications.email_smtp.smtplib.SMTP") as MockSMTP:
    mock_smtp = MockSMTP.return_value.__enter__.return_value
    mock_smtp.send_message.return_value = None
    # assert mock_smtp.starttls.called, mock_smtp.login.called, mock_smtp.send_message.called
```

**Helper factories pattern** (`test_jsearch.py` lines 30–60):
```python
def _make_ok_response(jobs: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"data": jobs}
    return resp

def _make_429_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 429
    return resp
```
For `test_notifications.py`, add `_make_200_response` (Telegram success: `{"ok": True}`) and `_make_error_response` (Telegram non-200).

**Real SQLiteStorage on tmp_path pattern** (`test_pipeline.py` lines 105–110):
```python
storage = SQLiteStorage(str(tmp_path / "test.db"))
storage.init_db()
```
Notification tests that cover SC3/SC4 (seen=0 preserved on failure; seen=1 after success; absent from next digest after restart) must use this pattern — `tmp_path` isolates each test, no shared state.

**Import-cleanliness pattern** (`test_pipeline.py` lines 76–94):
```python
def test_pipeline_no_streamlit_apscheduler():
    for mod in list(sys.modules.keys()):
        if "streamlit" in mod or "apscheduler" in mod:
            del sys.modules[mod]

    import app.pipeline  # noqa: F401

    assert "streamlit" not in sys.modules, (
        "pipeline.py must not import streamlit at module level"
    )
    assert "apscheduler" not in sys.modules, (
        "pipeline.py must not import apscheduler at module level"
    )
```
For notifications, mirror exactly, replacing `app.pipeline` with `app.notifications`.

**monkeypatch.setenv for env secrets** (`test_jsearch.py` lines 165–167):
```python
monkeypatch.setenv("RAPIDAPI_KEY", "test-key-from-env")
```
For notification tests: `monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")`, `monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")`, etc. Never hardcode real tokens.

**Deferred import inside test** (project convention — `test_jsearch.py` lines 69, 130, etc.):
```python
from app.sources.jsearch import fetch_jsearch_query  # noqa: PLC0415
```
All imports of `app.notifications.*` inside test functions, not at module level, with `# noqa: PLC0415`.

---

## Shared Patterns

### Deferred imports to keep modules import-clean
**Source:** `app/pipeline.py` lines 80–81, 149–162
**Apply to:** `app/notifications/__init__.py` (imports `telegram.py`/`email_smtp.py` inside `send_digest`), `app/pipeline.py` step 11 (imports `send_digest`)
```python
from app.notifications import send_digest  # noqa: PLC0415
```

### Parameterized SQL — never interpolate
**Source:** `app/storage/sqlite.py` throughout (every `conn.execute(...)`)
**Apply to:** `app/storage/sqlite.py` `get_undelivered_qualifying`
```python
placeholders = ",".join("?" * len(recommendations))
conn.execute(
    f"SELECT * FROM jobs WHERE seen=0 AND recommendation IN ({placeholders})"
    " AND score_total >= ? ORDER BY score_total DESC",
    (*recommendations, min_score),
)
```

### `with closing(self._connect()) as conn:` + `with conn:` for writes
**Source:** `app/storage/sqlite.py` lines 65, 131, 223, 248, 291
**Apply to:** `app/storage/sqlite.py` `get_undelivered_qualifying` (read: `closing` only, no `with conn:`; same as `get_history` line 179)

### Per-item error isolation (log + skip, never abort batch)
**Source:** `app/storage/sqlite.py` lines 197–202 (`get_history` per-row try/except); `app/sources/jsearch.py` lines 65–73 (per-query isolation)
**Apply to:** `app/storage/sqlite.py` `get_undelivered_qualifying` per-row reconstruction; `app/notifications/__init__.py` per-chunk mark_seen loop

### `errors: list[str]` accumulation, never re-raise
**Source:** `app/pipeline.py` lines 178–184 (fetch error), 228–229 (score_job error)
**Apply to:** `app/notifications/__init__.py` `send_digest` — errors from channel send appended to `DigestResult.errors`, never re-raised; `app/pipeline.py` step 11

### Settings-as-strings coercion
**Source:** `app/storage/sqlite.py` line 207 comment; `app/pipeline.py` line 168 (`float(settings.get(...))`)
**Apply to:** `app/notifications/digest.py` `resolve_channel` / `send_digest` call site
```python
min_score = int(settings.get("notification_min_score", "70"))
```

### `# noqa: PLC0415` on every deferred import
**Source:** `app/pipeline.py` lines 80, 150, 154, 159
**Apply to:** every `from app.notifications import ...` and every import-inside-function in `app/notifications/__init__.py`

---

## No Analog Found

All files in Phase 9 have direct analogs in the codebase. No gaps.

---

## Metadata

**Analog search scope:** `app/sources/`, `app/storage/`, `app/pipeline.py`, `tests/sources/`, `tests/test_pipeline.py`
**Files scanned:** 6 source files fully read (jsearch.py, sqlite.py, protocol.py, pipeline.py, test_jsearch.py, test_pipeline.py) + schema class excerpt
**Pattern extraction date:** 2026-05-25
