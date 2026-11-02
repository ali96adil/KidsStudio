"""Release authorization is distinct from creative approval.

This module only records authorization. It never calls YouTube or publishes.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from .owner_video_reviews import _validate_id

RELEASE_STATES = frozenset({"hold", "release_authorized"})

class OwnerReleaseGate:
    def __init__(self, database: str | Path):
        self.database = str(database)

    def initialize(self) -> None:
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS owner_release_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                episode_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('hold','release_authorized')),
                actor TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_release_episode ON owner_release_decisions(episode_id, id)")

    def record(self, episode_id: str, decision: str, actor: str) -> None:
        _validate_id(episode_id)
        if decision not in RELEASE_STATES:
            raise ValueError("invalid release decision")
        if not isinstance(actor, str) or not 1 <= len(actor.strip()) <= 80:
            raise ValueError("actor is required")
        with sqlite3.connect(self.database, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO owner_release_decisions (episode_id,decision,actor,recorded_at) VALUES (?,?,?,?)",
                (episode_id, decision, actor.strip(), datetime.now(timezone.utc).isoformat()),
            )

    def latest(self, episode_id: str) -> str:
        _validate_id(episode_id)
        with sqlite3.connect(self.database, timeout=10) as db:
            row = db.execute(
                "SELECT decision FROM owner_release_decisions WHERE episode_id=? ORDER BY id DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
        return row[0] if row else "hold"

    def eligible(self, episode_id: str, review_state: str) -> bool:
        """Authorization and review approval must both be current."""
        return review_state == "approved" and self.latest(episode_id) == "release_authorized"
