"""Transactional local owner reviews, independent of publishing and job execution."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

from .owner_video_reviews import STATES, _validate_id, _validate_note

class OwnerReviewStore:
    def __init__(self, database: str | Path):
        self.path = Path(database).expanduser().resolve()
        if self.path.suffix not in (".db", ".sqlite"):
            raise ValueError("review database must end with .db or .sqlite")

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("""CREATE TABLE IF NOT EXISTS owner_reviews (
                review_id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('needs_review','changes_requested','approved')),
                note TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_owner_reviews_episode ON owner_reviews(episode_id)")

    def record(self, *, episode_id: str, state: str, note: str = "") -> dict:
        _validate_id(episode_id)
        if state not in STATES:
            raise ValueError("invalid review state")
        _validate_note(note)
        entry = {
            "review_id": uuid4().hex,
            "episode_id": episode_id,
            "state": state,
            "note": note,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with sqlite3.connect(self.path, timeout=10, isolation_level=None) as db:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""INSERT INTO owner_reviews
                    (review_id, episode_id, state, note, recorded_at)
                    VALUES (:review_id, :episode_id, :state, :note, :recorded_at)""", entry)
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        return entry

    def latest(self) -> dict[str, dict]:
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("""SELECT review_id,episode_id,state,note,recorded_at
                FROM owner_reviews ORDER BY rowid ASC""")
            result = {}
            for row in rows:
                item = dict(row)
                result[item["episode_id"]] = item
            return result

    def history(self, episode_id: str, *, limit: int = 100) -> list[dict]:
        _validate_id(episode_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be 1..100")
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(
                """SELECT review_id,episode_id,state,note,recorded_at
                FROM owner_reviews WHERE episode_id=? ORDER BY rowid DESC LIMIT ?""",
                (episode_id, limit)
            )]
