"""M68 deployment preflight: read-only, no network and no credentials.

Check a staged Short against its immutable source, current owner policy,
review, quota reservation, journal, and exact local MP4 SHA.
"""
from __future__ import annotations

import json
from pathlib import Path

from .m68_short_source_binding import verify_current
from .youtube_private_upload import file_sha256


def assess(queue, *, short_id, series_id, media_path):
    reasons = []
    path = Path(media_path)
    with queue._connection() as db:
        def row(sql, args):
            try:
                return db.execute(sql, args).fetchone()
            except Exception:
                return None
        short = row("SELECT * FROM studio_derived_shorts WHERE short_id=?",
                    (short_id,))
        review = row("SELECT * FROM studio_short_reviews WHERE short_id=?",
                     (short_id,))
        reservation = row(
            "SELECT * FROM studio_short_quota_reservations WHERE short_id=?",
            (short_id,))
        attempt = row("SELECT * FROM studio_short_upload_attempts WHERE short_id=?",
                      (short_id,))
        policy = row(
            "SELECT * FROM studio_youtube_private_policies WHERE series_id=?",
            (series_id,))
        series = row("SELECT state FROM studio_series WHERE series_id=?",
                     (series_id,))
        paused = row("SELECT paused FROM settings WHERE slot=1", ())
        if not short or short["state"] != "PI_STAGED_NOT_APPROVED":
            reasons.append("SHORT_NOT_STAGED")
        if not policy or policy["state"] != "ENABLED":
            reasons.append("OWNER_POLICY_NOT_ENABLED")
        if not series or series["state"] != "ACTIVE":
            reasons.append("SERIES_NOT_ACTIVE")
        if not paused or paused["paused"]:
            reasons.append("COORDINATOR_PAUSED")
        if not short or not review or (
                review["source_episode_id"] != short["source_episode_id"]
                or review["media_sha256"] != short["media_sha256"]
                or review["decision"] != "PASS"):
            reasons.append("CONTENT_REVIEW_NOT_APPROVED")
        else:
            from .m68_short_content_review import CHECKS
            try:
                checks = json.loads(review["checks_json"])
            except (TypeError, ValueError):
                checks = None
            if not isinstance(checks, dict) or set(checks) != set(CHECKS) or any(
                    checks[k] is not True for k in CHECKS):
                reasons.append("CONTENT_REVIEW_CHECKS_INVALID")
        if not short or not reservation or (
                reservation["series_id"] != series_id
                or reservation["media_sha256"] != short["media_sha256"]
                or reservation["state"] != "RESERVED_NO_UPLOAD"):
            reasons.append("QUOTA_RESERVATION_MISSING")
        if attempt:
            reasons.append("UPLOAD_ATTEMPT_ALREADY_EXISTS")
        try:
            verify_current(db, short_id=short_id, series_id=series_id)
        except Exception:
            reasons.append("SOURCE_MASTER_NOT_APPROVED")
        sha = short["media_sha256"] if short else None
    if (not path.is_absolute() or path.is_symlink()
            or path.suffix.lower() != ".mp4" or not path.is_file()
            or not 1000 <= path.stat().st_size <= 10 * 1024**3):
        reasons.append("STAGED_MEDIA_INVALID")
    elif sha is None or file_sha256(path) != sha:
        reasons.append("STAGED_MEDIA_SHA_MISMATCH")
    return {
        "status": "READY_FOR_EXPLICIT_PRIVATE_UPLOAD" if not reasons else "BLOCKED",
        "short_id": short_id, "series_id": series_id,
        "reasons": sorted(set(reasons)),
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
