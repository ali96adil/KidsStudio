"""M68 derived-short identity registry in the existing Pi SQLite database.

This does not manufacture an M65-approved episode or queue an upload.
A short must remain separate from its parent episode and from other shorts.
"""
from __future__ import annotations

import re

from .studio_queue import StudioQueue


class ShortRegistryError(ValueError):
    pass


ID = re.compile(r"^[a-zA-Z0-9_-]{2,120}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


class ShortRegistry:
    def __init__(self, queue: StudioQueue):
        self.queue = queue

    def initialize(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_derived_shorts (
                short_id TEXT PRIMARY KEY,
                source_episode_id TEXT NOT NULL,
                media_sha256 TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL CHECK(state IN
                    ('REGISTERED_NOT_APPROVED','PI_STAGED_NOT_APPROVED')),
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                CHECK(short_id <> source_episode_id)
            )""")

    def register(self, *, short_id, source_episode_id, media_sha256):
        if (not isinstance(short_id, str) or not ID.fullmatch(short_id)
                or not isinstance(source_episode_id, str)
                or not ID.fullmatch(source_episode_id)
                or short_id == source_episode_id
                or not isinstance(media_sha256, str)
                or not SHA.fullmatch(media_sha256)):
            raise ShortRegistryError("invalid derived-short identity or media hash")
        with self.queue._connection(write=True) as db:
            prior = db.execute(
                "SELECT * FROM studio_derived_shorts WHERE short_id=?",
                (short_id,)).fetchone()
            if prior:
                if (prior["source_episode_id"] != source_episode_id
                        or prior["media_sha256"] != media_sha256):
                    raise ShortRegistryError("short identity cannot be reused")
                return self._report(dict(prior))
            if db.execute(
                    "SELECT 1 FROM studio_derived_shorts WHERE media_sha256=?",
                    (media_sha256,)).fetchone():
                raise ShortRegistryError("same MP4 cannot be registered as another short")
            now = self.queue.clock()
            db.execute("""INSERT INTO studio_derived_shorts VALUES
                (?,?,?,?,?,?)""", (short_id, source_episode_id, media_sha256,
                                    "REGISTERED_NOT_APPROVED", now, now))
            return self._report(dict(db.execute(
                "SELECT * FROM studio_derived_shorts WHERE short_id=?",
                (short_id,)).fetchone()))

    def mark_staged(self, *, short_id, media_sha256, transfer_receipt):
        if (not isinstance(transfer_receipt, dict)
                or transfer_receipt.get("status") != "SHORT_PI_STAGED_REQUIRES_M65_INBOX"
                or transfer_receipt.get("short_id") != short_id
                or transfer_receipt.get("sha256") != media_sha256
                or transfer_receipt.get("youtube_upload_authorized") is not False
                or transfer_receipt.get("public_release_authorized") is not False):
            raise ShortRegistryError("verified private staging receipt required")
        with self.queue._connection(write=True) as db:
            row = db.execute("SELECT * FROM studio_derived_shorts WHERE short_id=?",
                             (short_id,)).fetchone()
            if (not row or row["media_sha256"] != media_sha256
                    or row["source_episode_id"] != transfer_receipt.get("source_episode_id")):
                raise ShortRegistryError("registered short does not match transfer")
            if row["state"] != "PI_STAGED_NOT_APPROVED":
                db.execute("""UPDATE studio_derived_shorts
                    SET state='PI_STAGED_NOT_APPROVED',updated_at=?
                    WHERE short_id=?""", (self.queue.clock(), short_id))
            return self._report(dict(db.execute(
                "SELECT * FROM studio_derived_shorts WHERE short_id=?",
                (short_id,)).fetchone()))

    @staticmethod
    def _report(row):
        return {"short_id": row["short_id"],
                "source_episode_id": row["source_episode_id"],
                "media_sha256": row["media_sha256"],
                "status": row["state"],
                "m65_render_job_id": None,
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
