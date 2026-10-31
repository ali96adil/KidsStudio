"""M68 durable one-shot upload-attempt journal for derived Shorts.

A STARTED entry is written before any external API request. Uncertain
attempts are never retried automatically. No YouTube calls occur here.
"""
from __future__ import annotations

import re


class ShortAttemptError(ValueError):
    pass


IDENT = re.compile(r"^[A-Za-z0-9_-]{2,120}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


class ShortAttemptJournal:
    def __init__(self, queue):
        self.queue = queue

    def initialize(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_short_upload_attempts(
                short_id TEXT PRIMARY KEY,
                series_id TEXT NOT NULL,
                media_sha256 TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL CHECK(state IN
                    ('STARTED_UNCERTAIN','PRIVATE_VERIFIED','MANUAL_RECONCILIATION')),
                video_id TEXT,
                started_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(short_id) REFERENCES studio_short_quota_reservations(short_id)
            )""")

    def begin(self, *, short_id, series_id, media_sha256):
        if (not isinstance(short_id, str) or not IDENT.fullmatch(short_id)
                or not isinstance(series_id, str) or not IDENT.fullmatch(series_id)
                or not isinstance(media_sha256, str) or not SHA.fullmatch(media_sha256)):
            raise ShortAttemptError("exact short identity required")
        with self.queue._connection(write=True) as db:
            prior = db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone()
            if prior:
                raise ShortAttemptError("upload attempt exists; never retry automatically")
            reservation = db.execute(
                "SELECT * FROM studio_short_quota_reservations WHERE short_id=?",
                (short_id,)).fetchone()
            if (not reservation or reservation["series_id"] != series_id
                    or reservation["media_sha256"] != media_sha256
                    or reservation["state"] != "RESERVED_NO_UPLOAD"):
                raise ShortAttemptError("matching quota reservation required")
            now = self.queue.clock()
            db.execute("""INSERT INTO studio_short_upload_attempts VALUES
                (?,?,?,'STARTED_UNCERTAIN',NULL,?,?)""",
                (short_id, series_id, media_sha256, now, now))
            return self._result(db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone())

    def mark_manual(self, *, short_id):
        with self.queue._connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone()
            if not row or row["state"] not in ("STARTED_UNCERTAIN", "MANUAL_RECONCILIATION"):
                raise ShortAttemptError("uncertain upload attempt required")
            db.execute("""UPDATE studio_short_upload_attempts
                SET state='MANUAL_RECONCILIATION',updated_at=?
                WHERE short_id=?""", (self.queue.clock(), short_id))
            return self._result(db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone())

    def status(self, *, short_id):
        with self.queue._connection() as db:
            row = db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone()
        return self._result(row) if row else None

    @staticmethod
    def _result(row):
        return {
            "short_id": row["short_id"],
            "series_id": row["series_id"],
            "media_sha256": row["media_sha256"],
            "status": row["state"],
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
