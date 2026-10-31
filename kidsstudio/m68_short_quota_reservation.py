"""Atomic, non-upload M68 short quota reservations on the Pi.

Reservations share the SQLite writer lock with M26 enqueue. M26 must count
these reservations too; otherwise a reservation cannot prevent M26 races.
No reservation creates an upload or grants publication rights.
"""
from __future__ import annotations

import json
import re


class ShortQuotaError(ValueError):
    pass


IDENT = re.compile(r"^[A-Za-z0-9_-]{2,120}$")
SHA = re.compile(r"^[0-9a-f]{64}$")


class ShortQuotaReservations:
    def __init__(self, queue):
        self.queue = queue

    def initialize(self):
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_short_quota_reservations(
                short_id TEXT PRIMARY KEY,
                series_id TEXT NOT NULL,
                media_sha256 TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                state TEXT NOT NULL CHECK(state='RESERVED_NO_UPLOAD')
            )""")

    def release_unused(self, *, short_id, series_id, media_sha256):
        """Release an unused slot only; an upload attempt must use a separate journal."""
        if (not isinstance(short_id, str) or not IDENT.fullmatch(short_id)
                or not isinstance(series_id, str) or not IDENT.fullmatch(series_id)
                or not isinstance(media_sha256, str) or not SHA.fullmatch(media_sha256)):
            raise ShortQuotaError("exact reservation identity required")
        with self.queue._connection(write=True) as db:
            row = db.execute(
                "SELECT * FROM studio_short_quota_reservations WHERE short_id=?",
                (short_id,)).fetchone()
            if (not row or row["series_id"] != series_id
                    or row["media_sha256"] != media_sha256):
                raise ShortQuotaError("reservation not found or identity mismatch")
            if row["state"] != "RESERVED_NO_UPLOAD":
                raise ShortQuotaError("only unused reservations can be released")
            # An attempt is permanent evidence even if the external API timed out.
            has_journal = db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='studio_short_upload_attempts'""").fetchone()
            if has_journal and db.execute(
                "SELECT 1 FROM studio_short_upload_attempts WHERE short_id=?",
                (short_id,)).fetchone():
                raise ShortQuotaError("upload attempt exists; reservation cannot be released")
            db.execute("DELETE FROM studio_short_quota_reservations WHERE short_id=?",
                       (short_id,))
        return {"status": "SHORT_UNUSED_RESERVATION_RELEASED_NO_UPLOAD",
                "short_id": short_id, "youtube_upload_authorized": False,
                "public_release_authorized": False}

    def reserve(self, *, short_id, series_id, media_sha256):
        if (not isinstance(short_id, str) or not IDENT.fullmatch(short_id)
                or not isinstance(series_id, str) or not IDENT.fullmatch(series_id)
                or not isinstance(media_sha256, str)
                or not SHA.fullmatch(media_sha256)):
            raise ShortQuotaError("valid exact short identity required")
        with self.queue._connection(write=True) as db:
            now = self.queue.clock()
            prior = db.execute(
                "SELECT * FROM studio_short_quota_reservations WHERE short_id=?",
                (short_id,)).fetchone()
            if prior:
                if (prior["series_id"] != series_id
                        or prior["media_sha256"] != media_sha256):
                    raise ShortQuotaError("reservation identity cannot change")
                return self._result(prior)
            policy = db.execute(
                "SELECT state,max_uploads_24h FROM studio_youtube_private_policies WHERE series_id=?",
                (series_id,)).fetchone()
            series = db.execute(
                "SELECT state FROM studio_series WHERE series_id=?",
                (series_id,)).fetchone()
            if not policy or policy["state"] != "ENABLED" or not series or series["state"] != "ACTIVE":
                raise ShortQuotaError("active series and owner policy required")
            if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                raise ShortQuotaError("Pi coordinator paused")
            short = db.execute(
                "SELECT * FROM studio_derived_shorts WHERE short_id=?",
                (short_id,)).fetchone()
            review = db.execute(
                "SELECT * FROM studio_short_reviews WHERE short_id=?",
                (short_id,)).fetchone()
            if (not short or short["state"] != "PI_STAGED_NOT_APPROVED"
                    or short["media_sha256"] != media_sha256
                    or not review or review["media_sha256"] != media_sha256
                    or review["source_episode_id"] != short["source_episode_id"]
                    or review["decision"] != "PASS"):
                raise ShortQuotaError("staged, reviewed short required")
            from .m68_short_content_review import CHECKS
            try:
                checks = json.loads(review["checks_json"])
            except (TypeError, ValueError) as exc:
                raise ShortQuotaError("invalid review checks") from exc
            if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(checks[k] is not True for k in CHECKS):
                raise ShortQuotaError("six checks must pass")
            jobs = db.execute(
                """SELECT state,created_at FROM jobs WHERE kind='youtube_private_upload'
                   AND json_extract(payload,'$.series_id')=?""",
                (series_id,)).fetchall()
            recent = sum(j["created_at"] >= now-86400 for j in jobs)
            active = any(j["state"] in ("QUEUED", "LEASED") for j in jobs)
            if db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                              AND name='studio_recovery_uploads'""").fetchone():
                recovery = db.execute(
                    """SELECT u.state,u.created_at FROM studio_recovery_uploads u
                       JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                       WHERE i.series_id=?""", (series_id,)).fetchall()
                recent += sum(r["created_at"] >= now-86400 for r in recovery)
                active |= any(r["state"] in
                              ("M63_PRIVATE_UPLOAD_READY_ONE_SHOT",
                               "M63_PRIVATE_UPLOAD_LEASED") for r in recovery)
            reserved = db.execute(
                """SELECT COUNT(*) FROM studio_short_quota_reservations
                   WHERE series_id=? AND created_at>=?""",
                (series_id, now-86400)).fetchone()[0]
            if active or recent + reserved >= policy["max_uploads_24h"]:
                raise ShortQuotaError("shared upload quota exhausted or upload in flight")
            db.execute(
                """INSERT INTO studio_short_quota_reservations VALUES(?,?,?,?,'RESERVED_NO_UPLOAD')""",
                (short_id, series_id, media_sha256, now))
            return self._result(db.execute(
                "SELECT * FROM studio_short_quota_reservations WHERE short_id=?",
                (short_id,)).fetchone())

    @staticmethod
    def _result(row):
        return {"short_id": row["short_id"], "series_id": row["series_id"],
                "media_sha256": row["media_sha256"],
                "status": "SHORT_QUOTA_RESERVED_NO_UPLOAD",
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
