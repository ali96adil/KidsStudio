"""Durable local-only coordination queue for KidsStudio agents.

SQLite transactions provide atomic leases, idempotent enqueue, worker fencing
and bounded retries. The queue itself executes NO tasks and contacts NO hosts.
A later allowlisted worker adapter will perform permitted task types.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Iterator, Sequence
from uuid import uuid4


KINDS = frozenset({
    "character_generate", "rig_review", "godot_render",
    "script_draft", "editorial_review", "archive_verify",
})
STATES = frozenset({
    "QUEUED", "LEASED", "COMPLETED", "FAILED", "CANCELLED"
})
MAX_RECORD_BYTES = 32_768
SAFE_KEY = re.compile(r"^[a-zA-Z0-9_./:-]{1,160}$")
SENSITIVE_KEY = re.compile(
    r"(?:password|secret|api.?key|access.?token|refresh.?token|private.?key)",
    re.IGNORECASE,
)


class QueueError(ValueError):
    """Invalid job, unsafe operation, stale worker or conflicting request."""


def _json_object(value: Any, label: str) -> str:
    if not isinstance(value, dict):
        raise QueueError(f"{label} must be a JSON object.")
    def inspect(node: Any, depth: int = 0) -> None:
        if depth > 15:
            raise QueueError(f"{label} JSON nesting exceeds safety limit.")
        if isinstance(node, dict):
            for key, item in node.items():
                if not isinstance(key, str) or SENSITIVE_KEY.search(key):
                    raise QueueError(f"{label} contains a disallowed/sensitive key.")
                inspect(item, depth + 1)
        elif isinstance(node, list):
            for item in node:
                inspect(item, depth + 1)
    inspect(value)
    try:
        packed = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise QueueError(f"{label} cannot be encoded as JSON: {exc}") from exc
    if len(packed.encode("utf-8")) > MAX_RECORD_BYTES:
        raise QueueError(f"{label} exceeds {MAX_RECORD_BYTES} UTF-8 bytes.")
    return packed


class StudioQueue:
    """One-writer-at-a-time SQLite coordination queue on local Pi storage."""

    def __init__(self, database: str | Path, *,
                 clock: Callable[[], float] | None = None):
        self.path = Path(database).expanduser().resolve()
        self.clock = clock or time.time
        if self.path.suffix not in (".sqlite", ".db"):
            raise QueueError("Use a dedicated .sqlite or .db database filename.")
        if any((p / ".git").exists() for p in (self.path.parent, *self.path.parents)):
            raise QueueError("Do not place SQLite operational data inside a Git checkout.")

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        if not self.path.is_file():
            raise QueueError("Queue database does not exist; run 'studioctl init'.")
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=FULL")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.execute("COMMIT")
        except Exception:
            if write and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        if self.path.exists():
            raise FileExistsError("Queue already exists; do not overwrite active jobs.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Restrict local coordinator DB permissions; this is NOT a network ACL.
        fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            # sqlite3.executescript commits implicitly; schema initialization
            # uses a new empty file, not a nested write transaction.
            with self._connection() as db:
                db.executescript("""
                    CREATE TABLE jobs (
                        job_id TEXT PRIMARY KEY,
                        request_key TEXT NOT NULL UNIQUE,
                        kind TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        state TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        max_attempts INTEGER NOT NULL,
                        generation INTEGER NOT NULL DEFAULT 0,
                        worker_id TEXT,
                        lease_expires REAL,
                        available_at REAL NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        result_json TEXT,
                        error_code TEXT
                    );
                    CREATE INDEX ready_jobs
                        ON jobs(state, available_at, created_at);
                    CREATE TABLE events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT,
                        event_type TEXT NOT NULL,
                        info_json TEXT NOT NULL,
                        happened_at REAL NOT NULL,
                        FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                    );
                    CREATE TABLE settings (
                        slot INTEGER PRIMARY KEY CHECK(slot=1),
                        paused INTEGER NOT NULL DEFAULT 0
                    );
                    INSERT INTO settings(slot,paused) VALUES(1,0);
                """)
        except Exception:
            self.path.unlink(missing_ok=True)
            raise
        # WAL enables reads while a short write transaction is active.
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")

    def _event(self, db: sqlite3.Connection, job_id: str | None,
               kind: str, info: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO events(job_id,event_type,info_json,happened_at) VALUES(?,?,?,?)",
            (job_id, kind, _json_object(info, "event"), self.clock())
        )

    def enqueue(self, *, kind: str, request_key: str,
                payload: dict[str, Any], max_attempts: int = 2) -> dict[str, Any]:
        if kind not in KINDS:
            raise QueueError("Unsupported job kind (requires approved worker capability).")
        if not isinstance(request_key, str) or not SAFE_KEY.fullmatch(request_key):
            raise QueueError("Invalid idempotency request_key.")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise QueueError("max_attempts must be 1..3.")
        packed = _json_object(payload, "payload")
        now = self.clock()
        with self._connection(write=True) as db:
            existing = db.execute(
                "SELECT * FROM jobs WHERE request_key=?", (request_key,)
            ).fetchone()
            if existing is not None:
                if (existing["kind"] != kind or existing["payload"] != packed
                        or existing["max_attempts"] != max_attempts):
                    raise QueueError("Idempotency key already used for a different request.")
                return dict(existing)
            identifier = uuid4().hex
            db.execute("""
                INSERT INTO jobs(
                    job_id,request_key,kind,payload,state,max_attempts,
                    available_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
            """, (identifier, request_key, kind, packed, "QUEUED",
                  max_attempts, now, now, now))
            self._event(db, identifier, "ENQUEUED", {"kind": kind})
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (identifier,)
            ).fetchone())

    def claim(self, *, worker_id: str, capabilities: Sequence[str],
              lease_seconds: int = 120) -> dict[str, Any] | None:
        if not isinstance(worker_id, str) or not SAFE_KEY.fullmatch(worker_id):
            raise QueueError("Invalid worker identity.")
        if type(lease_seconds) is not int or not 10 <= lease_seconds <= 3600:
            raise QueueError("Lease seconds must be 10..3600.")
        if not isinstance(capabilities, (list, tuple, frozenset, set)):
            raise QueueError("Worker capabilities must be a collection.")
        kinds = sorted(set(capabilities))
        if not kinds or any(k not in KINDS for k in kinds):
            raise QueueError("Worker capabilities contain unapproved kinds.")
        now = self.clock()
        with self._connection(write=True) as db:
            if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                return None
            expired = db.execute("""
                SELECT job_id,attempts,max_attempts FROM jobs
                WHERE state='LEASED' AND lease_expires <= ?
            """, (now,)).fetchall()
            for item in expired:
                if item["attempts"] >= item["max_attempts"]:
                    db.execute("""
                        UPDATE jobs SET state='FAILED',worker_id=NULL,
                        lease_expires=NULL,updated_at=?,error_code='LEASE_EXHAUSTED'
                        WHERE job_id=?
                    """, (now, item["job_id"]))
                    self._event(db, item["job_id"], "LEASE_EXHAUSTED", {})
                else:
                    db.execute("""
                        UPDATE jobs SET state='QUEUED',worker_id=NULL,
                        lease_expires=NULL,updated_at=?,available_at=?
                        WHERE job_id=?
                    """, (now, now, item["job_id"]))
                    self._event(db, item["job_id"], "LEASE_EXPIRED_REQUEUED", {})
            placeholders = ",".join("?" for _ in kinds)
            item = db.execute(f"""
                SELECT * FROM jobs
                WHERE state='QUEUED' AND available_at <= ?
                  AND kind IN ({placeholders})
                ORDER BY available_at,created_at,job_id LIMIT 1
            """, (now, *kinds)).fetchone()
            if item is None:
                return None
            db.execute("""
                UPDATE jobs SET state='LEASED', worker_id=?, attempts=attempts+1,
                generation=generation+1, lease_expires=?,updated_at=?
                WHERE job_id=? AND state='QUEUED'
            """, (worker_id, now + lease_seconds, now, item["job_id"]))
            self._event(db, item["job_id"], "CLAIMED",
                        {"worker": worker_id, "attempt": item["attempts"] + 1})
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (item["job_id"],)
            ).fetchone())

    @staticmethod
    def _guard_current(db: sqlite3.Connection, job_id: str, worker_id: str,
                       generation: int, now: float) -> sqlite3.Row:
        row = db.execute(
            "SELECT * FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if (row is None or row["state"] != "LEASED" or
            row["worker_id"] != worker_id or row["generation"] != generation or
            row["lease_expires"] is None or row["lease_expires"] <= now):
            raise QueueError("Stale, expired or revoked worker lease.")
        return row

    def heartbeat(self, *, job_id: str, worker_id: str,
                  generation: int, lease_seconds: int = 120) -> dict[str, Any]:
        if type(lease_seconds) is not int or not 10 <= lease_seconds <= 3600:
            raise QueueError("Lease seconds must be 10..3600.")
        now = self.clock()
        with self._connection(write=True) as db:
            self._guard_current(db, job_id, worker_id, generation, now)
            db.execute(
                "UPDATE jobs SET lease_expires=?,updated_at=? WHERE job_id=?",
                (now + lease_seconds, now, job_id)
            )
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone())

    def complete(self, *, job_id: str, worker_id: str,
                 generation: int, result: dict[str, Any]) -> dict[str, Any]:
        packed = _json_object(result, "result")
        now = self.clock()
        with self._connection(write=True) as db:
            self._guard_current(db, job_id, worker_id, generation, now)
            db.execute("""
                UPDATE jobs SET state='COMPLETED',result_json=?,
                worker_id=NULL,lease_expires=NULL,updated_at=?
                WHERE job_id=?
            """, (packed, now, job_id))
            self._event(db, job_id, "COMPLETED", {})
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone())

    def complete_draft_and_enqueue_review(
        self, *, job_id: str, worker_id: str, generation: int,
        result: dict[str, Any], language: str
    ) -> dict[str, Any]:
        """Atomically complete one draft and create one independent review job.

        Only a successfully leased script_draft can authorize this handoff.
        The child stores a source hash/reference, NEVER the text itself.
        """
        if language not in ("ar", "en"):
            raise QueueError("Invalid review language.")
        if (not isinstance(result, dict) or
            result.get("status") != "DRAFTED_UNREVIEWED" or
            result.get("publication_approved") is not False):
            raise QueueError("Cannot hand off an unverified/non-draft result.")
        provider = result.get("provider_id")
        sha = result.get("artifact_sha256")
        if (not isinstance(provider, str) or not SAFE_KEY.fullmatch(provider)
                or not isinstance(sha, str) or
                len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)):
            raise QueueError("Review handoff needs trusted provider and SHA256 provenance.")
        packed = _json_object(result, "draft result")
        now = self.clock()
        review_key = "review:" + hashlib.sha256(
            job_id.encode("utf-8")).hexdigest()
        with self._connection(write=True) as db:
            current = self._guard_current(db, job_id, worker_id, generation, now)
            if current["kind"] != "script_draft":
                raise QueueError("Only a script draft may launch editorial review.")
            parent_payload = json.loads(current["payload"])
            if parent_payload.get("language") != language:
                raise QueueError("Review and draft languages disagree.")
            if db.execute(
                "SELECT 1 FROM jobs WHERE request_key=?", (review_key,)
            ).fetchone():
                raise QueueError("This draft already has a review job.")
            child_id = uuid4().hex
            child_payload = _json_object({
                "language": language,
                "source_job_id": job_id,
                "source_answer_sha256": sha,
                "original_provider_id": provider,
            }, "review payload")
            db.execute("""
                INSERT INTO jobs (
                    job_id,request_key,kind,payload,state,max_attempts,
                    available_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?)
            """, (
                child_id, review_key, "editorial_review", child_payload,
                "QUEUED", 2, now, now, now,
            ))
            parent_result = dict(result)
            parent_result["next_review_job_id"] = child_id
            packed = _json_object(parent_result, "draft handoff result")
            db.execute("""
                UPDATE jobs SET state='COMPLETED',result_json=?,
                    worker_id=NULL,lease_expires=NULL,updated_at=?
                WHERE job_id=?
            """, (packed, now, job_id))
            self._event(db, job_id, "COMPLETED_AND_REVIEW_QUEUED",
                        {"next_review_job_id": child_id})
            self._event(db, child_id, "ENQUEUED_BY_DRAFT",
                        {"source_job_id": job_id})
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone())

    def fail(self, *, job_id: str, worker_id: str, generation: int,
             error_code: str, retryable: bool = False) -> dict[str, Any]:
        if not isinstance(error_code, str) or not SAFE_KEY.fullmatch(error_code):
            raise QueueError("Error code must be a safe symbolic identifier.")
        now = self.clock()
        with self._connection(write=True) as db:
            current = self._guard_current(db, job_id, worker_id, generation, now)
            can_retry = retryable and current["attempts"] < current["max_attempts"]
            next_state = "QUEUED" if can_retry else "FAILED"
            delay = min(10 * (2 ** current["attempts"]), 120) if can_retry else 0
            db.execute("""
                UPDATE jobs SET state=?,error_code=?,worker_id=NULL,
                lease_expires=NULL,updated_at=?,available_at=?
                WHERE job_id=?
            """, (next_state, error_code, now, now + delay, job_id))
            self._event(db, job_id, "RETRY_SCHEDULED" if can_retry else "FAILED",
                        {"error_code": error_code, "attempt": current["attempts"]})
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone())

    def cancel(self, job_id: str) -> dict[str, Any]:
        now = self.clock()
        with self._connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise QueueError("Unknown job.")
            if row["state"] not in ("QUEUED", "LEASED", "CANCELLED"):
                raise QueueError("Terminal jobs cannot be cancelled.")
            if row["state"] != "CANCELLED":
                db.execute("""
                    UPDATE jobs SET state='CANCELLED',worker_id=NULL,
                    lease_expires=NULL,generation=generation+1,updated_at=?
                    WHERE job_id=?
                """, (now, job_id))
                self._event(db, job_id, "CANCELLED", {})
            return dict(db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone())

    def set_paused(self, paused: bool) -> bool:
        if type(paused) is not bool:
            raise QueueError("paused must be a bool.")
        with self._connection(write=True) as db:
            db.execute("UPDATE settings SET paused=? WHERE slot=1", (int(paused),))
            self._event(db, None, "DISPATCH_PAUSED" if paused else "DISPATCH_RESUMED", {})
        return paused

    def status(self) -> dict[str, Any]:
        with self._connection() as db:
            counts = {
                row["state"]: row["n"]
                for row in db.execute("SELECT state,COUNT(*) AS n FROM jobs GROUP BY state")
            }
            paused = bool(db.execute(
                "SELECT paused FROM settings WHERE slot=1"
            ).fetchone()[0])
            return {"paused": paused, "counts": {state: counts.get(state, 0)
                                                for state in sorted(STATES)}}

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise QueueError("Unknown job.")
            return dict(row)

    def list_jobs(self, *, limit: int = 25) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise QueueError("List limit must be 1..100.")
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC,job_id DESC LIMIT ?",
                (limit,)
            )]

    def events(self, job_id: str | None = None, *, limit: int = 100
               ) -> list[dict[str, Any]]:
        if type(limit) is not int or not 1 <= limit <= 250:
            raise QueueError("Event limit must be 1..250.")
        with self._connection() as db:
            if job_id is None:
                results = db.execute(
                    "SELECT * FROM events ORDER BY event_id DESC LIMIT ?", (limit,)
                )
            else:
                results = db.execute(
                    "SELECT * FROM events WHERE job_id=? ORDER BY event_id DESC LIMIT ?",
                    (job_id, limit)
                )
            return [dict(row) for row in results]
