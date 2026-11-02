"""Append-only ledger binding uploaded YouTube IDs to exact local video digests."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .owner_video_reviews import _validate_id
from .youtube_release_plan import VIDEO_ID_RE

HASH_RE = re.compile(r"^[a-f0-9]{64}$")

class UploadBindingStore:
    def __init__(self, database: str | Path):
        self.database = str(database)

    def initialize(self) -> None:
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS youtube_upload_bindings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL,
                media_sha256 TEXT NOT NULL,
                video_id TEXT NOT NULL UNIQUE,
                channel_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_upload_episode ON youtube_upload_bindings(episode_id,id)")

    def record(self, episode_id: str, media_sha256: str, video_id: str, channel_id: str) -> None:
        _validate_id(episode_id)
        if not isinstance(media_sha256, str) or HASH_RE.fullmatch(media_sha256) is None:
            raise ValueError("invalid media digest")
        if not isinstance(video_id, str) or VIDEO_ID_RE.fullmatch(video_id) is None:
            raise ValueError("invalid YouTube video ID")
        if not isinstance(channel_id, str) or not 1 <= len(channel_id) <= 128:
            raise ValueError("invalid channel ID")
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO youtube_upload_bindings (episode_id,media_sha256,video_id,channel_id,created_at) VALUES (?,?,?,?,?)",
                (episode_id, media_sha256, video_id, channel_id, datetime.now(timezone.utc).isoformat()),
            )

    def matches_latest(self, episode_id: str, media_sha256: str, video_id: str, channel_id: str) -> bool:
        _validate_id(episode_id)
        with sqlite3.connect(self.database, timeout=10) as db:
            row = db.execute(
                "SELECT media_sha256,video_id,channel_id FROM youtube_upload_bindings WHERE episode_id=? ORDER BY id DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
        return bool(row and row == (media_sha256, video_id, channel_id))
