"""M68 owner-policy bridge for derived Shorts; read-only, no upload job.

Original M65 episode approval remains untouched. A Short needs its own
provenance and review, then the existing owner's series/channel policy.
"""
from __future__ import annotations

import re

from .m68_short_review_audit import assess_short_review
from .youtube_private_upload import CHANNEL


class ShortPolicyError(ValueError):
    pass


def assess_short_policy(queue, *, short_id, source_episode_id, media_sha256,
                        series_id, channel_id, made_for_kids,
                        contains_synthetic_media):
    if (not isinstance(series_id, str) or not series_id
            or not isinstance(channel_id, str)
            or not CHANNEL.fullmatch(channel_id)
            or type(made_for_kids) is not bool
            or type(contains_synthetic_media) is not bool):
        raise ShortPolicyError("exact channel and audience flags required")
    qa = assess_short_review(queue, short_id=short_id,
                             source_episode_id=source_episode_id,
                             media_sha256=media_sha256)
    reasons = list(qa["reasons"])
    with queue._connection() as db:
        series = db.execute(
            "SELECT state FROM studio_series WHERE series_id=?",
            (series_id,)).fetchone()
        policy = db.execute(
            "SELECT * FROM studio_youtube_private_policies WHERE series_id=?",
            (series_id,)).fetchone()
        paused = db.execute(
            "SELECT paused FROM settings WHERE slot=1").fetchone()
    if not series or series["state"] != "ACTIVE":
        reasons.append("SOURCE_SERIES_NOT_ACTIVE")
    if not policy or policy["state"] != "ENABLED":
        reasons.append("OWNER_PRIVATE_POLICY_NOT_ENABLED")
    elif (policy["channel_id"] != channel_id
          or bool(policy["allowed_made_for_kids"]) != made_for_kids
          or bool(policy["allowed_synthetic_media"]) != contains_synthetic_media):
        reasons.append("OWNER_PRIVATE_POLICY_FLAGS_MISMATCH")
    if not paused or paused["paused"]:
        reasons.append("PI_COORDINATOR_PAUSED")
    return {
        "status": ("SHORT_POLICY_PRECHECK_PASSED_UPLOAD_STILL_BLOCKED"
                   if not reasons else "SHORT_POLICY_BLOCKED"),
        "short_id": short_id,
        "series_id": series_id,
        "reasons": reasons,
        "policy_revision": policy["revision"] if policy and not reasons else None,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
