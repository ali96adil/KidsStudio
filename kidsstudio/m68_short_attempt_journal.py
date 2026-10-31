"""M68 durable one-shot upload-attempt journal for derived Shorts.

A STARTED entry is written before any external API request. Uncertain
attempts are never retried automatically. No YouTube calls occur here.
"""
from __future__ import annotations

import re

from .youtube_private_upload import VIDEO, CHANNEL


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

    def record_upload_result(self, *, short_id, series_id, media_sha256, video_id):
        """Record video ID returned by this attempt's upload response only."""
        if not isinstance(video_id, str) or not VIDEO.fullmatch(video_id):
            raise ShortAttemptError("valid YouTube response video ID required")
        with self.queue._connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone()
            if (not row or row["series_id"] != series_id
                    or row["media_sha256"] != media_sha256
                    or row["state"] != "STARTED_UNCERTAIN"
                    or row["video_id"] is not None):
                raise ShortAttemptError("matching fresh unresolved attempt required")
            db.execute("""UPDATE studio_short_upload_attempts
                SET video_id=?,updated_at=? WHERE short_id=?""",
                (video_id, self.queue.clock(), short_id))
            return self._result(db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone())

    def verify_private(self, *, short_id, series_id, media_sha256,
                       video_id, channel_id, token, transport=None):
        """Authenticated YouTube GET only; never initiates or retries upload."""
        if (not isinstance(video_id, str) or not VIDEO.fullmatch(video_id)
                or not isinstance(channel_id, str) or not CHANNEL.fullmatch(channel_id)
                or not isinstance(token, str) or len(token) < 30
                or any(ch.isspace() for ch in token)):
            raise ShortAttemptError("exact YouTube identity and fresh token required")
        with self.queue._connection() as db:
            row = db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone()
            if (not row or row["series_id"] != series_id
                    or row["media_sha256"] != media_sha256
                    or row["state"] not in ("STARTED_UNCERTAIN",
                                           "MANUAL_RECONCILIATION")
                    or row["video_id"] != video_id):
                raise ShortAttemptError("matching unresolved attempt required")
            policy = db.execute(
                "SELECT channel_id,state FROM studio_youtube_private_policies WHERE series_id=?",
                (series_id,)).fetchone()
            if (not policy or policy["state"] != "ENABLED"
                    or policy["channel_id"] != channel_id):
                raise ShortAttemptError("current owner channel policy required")
        if transport is None:
            from .youtube_private_upload import GoogleYouTubeTransport
            transport = GoogleYouTubeTransport()
        proof = transport.verify(token, video_id, channel_id)
        if (not isinstance(proof, dict)
                or proof.get("video_id") != video_id
                or proof.get("channel_id") != channel_id
                or proof.get("privacy_status") != "private"
                or proof.get("verified_using_authenticated_youtube_api") is not True
                or proof.get("processing_status") != "succeeded"):
            raise ShortAttemptError("authenticated private processing proof required")
        with self.queue._connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone()
            policy = db.execute(
                "SELECT channel_id,state FROM studio_youtube_private_policies WHERE series_id=?",
                (series_id,)).fetchone()
            if (not row or row["series_id"] != series_id
                    or row["media_sha256"] != media_sha256
                    or row["state"] not in ("STARTED_UNCERTAIN",
                                           "MANUAL_RECONCILIATION")
                    or row["video_id"] != video_id
                    or not policy or policy["state"] != "ENABLED"
                    or policy["channel_id"] != channel_id):
                raise ShortAttemptError("attempt or owner policy changed during verification")
            db.execute("""UPDATE studio_short_upload_attempts
                SET state='PRIVATE_VERIFIED',video_id=?,updated_at=?
                WHERE short_id=?""", (video_id, self.queue.clock(), short_id))
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
            "video_id": row["video_id"],
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        }
