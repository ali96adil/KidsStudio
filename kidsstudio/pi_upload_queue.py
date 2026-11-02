"""Durable single-worker upload recovery queue for Raspberry Pi."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class PiUploadQueue:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def initialize(self) -> None:
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pi_upload_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL,
                session_path TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','running','completed','failed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_pi_jobs_state ON pi_upload_jobs(state,id)")
            # Fail closed on pre-existing duplicates; never silently delete jobs.
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pi_jobs_session_unique "
                       "ON pi_upload_jobs(session_path)")

    def enqueue(self, episode_id: str, session_path: str | Path, channel_id: str) -> int:
        from .owner_video_reviews import _validate_id
        _validate_id(episode_id)
        if not channel_id or not str(session_path):
            raise ValueError("channel and session path required")
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id,episode_id,channel_id FROM pi_upload_jobs WHERE session_path=?",
                (str(session_path),),
            ).fetchone()
            if existing is not None:
                if existing[1:] != (episode_id, channel_id):
                    raise ValueError("session already assigned to different episode or channel")
                return int(existing[0])
            cur = db.execute(
                "INSERT INTO pi_upload_jobs (episode_id,session_path,channel_id,state,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                (episode_id, str(session_path), channel_id, "pending", _now(), _now()),
            )
            return int(cur.lastrowid)

    def claim(self) -> dict | None:
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id,episode_id,session_path,channel_id,attempts FROM pi_upload_jobs WHERE state='pending' ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE pi_upload_jobs SET state='running',attempts=attempts+1,updated_at=? WHERE id=?",
                (_now(), row[0]),
            )
            return dict(zip(("id", "episode_id", "session_path", "channel_id", "attempts"), row))

    def finish(self, job_id: int, *, success: bool, error: str | None = None) -> None:
        # Do not persist exception text: upstream URLs may contain secrets.
        state = "completed" if success else "failed"
        with sqlite3.connect(self.path, timeout=10) as db:
            cur = db.execute(
                "UPDATE pi_upload_jobs SET state=?,last_error=?,updated_at=? WHERE id=? AND state='running'",
                (state, None if success else (error or "upload failed")[:80], _now(), job_id),
            )
            if cur.rowcount != 1:
                raise ValueError("job not running")

    def recover_interrupted(self) -> int:
        """Call once at worker startup; running jobs are safely requeued."""
        with sqlite3.connect(self.path, timeout=10) as db:
            cur = db.execute(
                "UPDATE pi_upload_jobs SET state='pending',updated_at=? WHERE state='running'",
                (_now(),),
            )
            return cur.rowcount
