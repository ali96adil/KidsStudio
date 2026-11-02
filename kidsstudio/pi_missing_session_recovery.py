"""Safe guidance for missing private upload sessions.

A missing resumable session must never be replaced by a new upload
automatically: the previous YouTube upload may already have completed.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .pi_upload_queue import PiUploadQueue


def missing_session_actions(queue: PiUploadQueue) -> list[dict]:
    """Return non-sensitive operator actions; never mutate the upload queue."""
    with sqlite3.connect(queue.path, timeout=10) as db:
        rows = db.execute(
            "SELECT id,episode_id,state,session_path FROM pi_upload_jobs "
            "ORDER BY id"
        ).fetchall()
    actions = []
    for job_id, episode_id, state, session_path in rows:
        path = Path(session_path)
        if path.is_symlink() or not path.is_file():
            actions.append({
                "job_id": job_id,
                "episode_id": episode_id,
                "state": state,
                "action": "manual_reconcile_youtube_before_retry",
                "automatic_retry_allowed": False,
                "new_upload_allowed": False,
                "reason": "resumable_session_missing",
            })
    return actions
