"""Fail-closed media-specific owner approval.

An episode approval applies only to the exact SHA-256 digest of the reviewed
video, not to later renders with the same episode identifier.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .owner_video_reviews import _validate_id

_SHA256 = re.compile(r"^[a-f0-9]{64}$")

def sha256_video(path: str | Path) -> str:
    path = Path(path)
    if not path.is_file():
        raise ValueError("video must be a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()

class MediaApprovalStore:
    def __init__(self, database: str | Path):
        self.database = str(database)

    def initialize(self) -> None:
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS media_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(decision IN ('approved','changes_requested')),
                recorded_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_media_approval_episode ON media_approvals(episode_id,id)")

    def record(self, episode_id: str, sha256: str, decision: str) -> None:
        _validate_id(episode_id)
        if not isinstance(sha256, str) or _SHA256.fullmatch(sha256) is None:
            raise ValueError("invalid SHA256")
        if decision not in ("approved", "changes_requested"):
            raise ValueError("invalid media decision")
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO media_approvals (episode_id,sha256,decision,recorded_at) VALUES (?,?,?,?)",
                (episode_id, sha256, decision, datetime.now(timezone.utc).isoformat()),
            )

    def approved_for(self, episode_id: str, sha256: str) -> bool:
        _validate_id(episode_id)
        if not isinstance(sha256, str) or _SHA256.fullmatch(sha256) is None:
            return False
        with sqlite3.connect(self.database, timeout=10) as db:
            row = db.execute(
                "SELECT sha256,decision FROM media_approvals WHERE episode_id=? ORDER BY id DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
        return bool(row and row[0] == sha256 and row[1] == "approved")
