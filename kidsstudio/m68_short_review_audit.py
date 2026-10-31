"""M68 read-only eligibility audit for a derived Short on the Pi.

This is NOT M65 approval and never creates a YouTube upload job.
"""
from __future__ import annotations

import json

from .m68_short_content_review import CHECKS


def assess_short_review(queue, *, short_id, source_episode_id, media_sha256):
    with queue._connection() as db:
        short = db.execute(
            "SELECT * FROM studio_derived_shorts WHERE short_id=?",
            (short_id,)).fetchone()
        review = db.execute(
            "SELECT * FROM studio_short_reviews WHERE short_id=?",
            (short_id,)).fetchone()
    reasons = []
    if short is None:
        reasons.append("SHORT_NOT_REGISTERED")
    elif (short["source_episode_id"] != source_episode_id
          or short["media_sha256"] != media_sha256):
        reasons.append("SHORT_IDENTITY_MISMATCH")
    elif short["state"] != "PI_STAGED_NOT_APPROVED":
        reasons.append("SHORT_NOT_STAGED")
    if review is None:
        reasons.append("CONTENT_REVIEW_MISSING")
    elif (review["source_episode_id"] != source_episode_id
          or review["media_sha256"] != media_sha256):
        reasons.append("CONTENT_REVIEW_MEDIA_MISMATCH")
    elif review["decision"] != "PASS":
        reasons.append("CONTENT_REVIEW_REJECTED")
    else:
        try:
            checks = json.loads(review["checks_json"])
            if (not isinstance(checks, dict)
                    or set(checks) != set(CHECKS)
                    or any(checks[k] is not True for k in CHECKS)):
                reasons.append("CONTENT_REVIEW_INCOMPLETE")
        except (TypeError, ValueError):
            reasons.append("CONTENT_REVIEW_CORRUPT")
    return {
        "status": ("SHORT_REVIEW_READY_FOR_M65_POLICY"
                   if not reasons else "SHORT_REVIEW_BLOCKED"),
        "short_id": short_id,
        "reasons": reasons,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
