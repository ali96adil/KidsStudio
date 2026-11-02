"""Conservative recovery of durable private YouTube upload sessions.

Never creates a new YouTube session or starts a public release.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .pi_upload_queue import PiUploadQueue
from .youtube_upload_session import load_session


def recover_orphaned_sessions(queue: PiUploadQueue, session_dir: str | Path,
                              expected_channel_id: str) -> dict:
    """Restore sessions saved before a crash interrupted queue insertion.

    Existing completed, pending, running or failed jobs are not duplicated.
    The episode ID and SHA-256 suffix must match the session's media.
    """
    root = Path(session_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid session directory")
    restored = 0
    skipped = 0
    for path in sorted(root.glob("*.json")):
        if path.is_symlink():
            skipped += 1
            continue
        try:
            session = load_session(path)
            if not isinstance(session, dict):
                skipped += 1
                continue
            video = Path(session["video_path"])
            if not video.is_file() or video.is_symlink():
                skipped += 1
                continue
            name = path.stem
            suffix = "-" + session["media_sha256"][:16]
            if not name.endswith(suffix):
                skipped += 1
                continue
            episode_id = name[:-len(suffix)]
            from .owner_video_reviews import _validate_id
            _validate_id(episode_id)
            with sqlite3.connect(queue.path, timeout=10) as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute(
                    "SELECT id FROM pi_upload_jobs WHERE session_path=? OR "
                    "(episode_id=? AND channel_id=?)",
                    (str(path), episode_id, expected_channel_id),
                ).fetchone()
                if existing:
                    skipped += 1
                    continue
                now = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "INSERT INTO pi_upload_jobs "
                    "(episode_id,session_path,channel_id,state,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (episode_id, str(path), expected_channel_id, "pending", now, now),
                )
                restored += 1
        except (OSError, ValueError, KeyError, TypeError):
            skipped += 1
    return {"restored": restored, "skipped": skipped}


def requeue_failed_job(queue: PiUploadQueue, job_id: int) -> bool:
    """Explicit operator retry, preserving the same resumable session."""
    with sqlite3.connect(queue.path, timeout=10) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT session_path FROM pi_upload_jobs WHERE id=? AND state='failed'",
            (job_id,),
        ).fetchone()
        if row is None:
            return False
        session_file = Path(row[0])
        if session_file.is_symlink() or not session_file.is_file():
            return False
        load_session(session_file)
        cur = db.execute(
            "UPDATE pi_upload_jobs SET state='pending',last_error=NULL,"
            "updated_at=? WHERE id=? AND state='failed'",
            (datetime.now(timezone.utc).isoformat(), job_id),
        )
        return cur.rowcount == 1
