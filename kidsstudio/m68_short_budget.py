"""M68 shared private-upload budget precheck for derived Shorts.

Read-only: uses M26 jobs and M63 recovery ledgers. No upload is enqueued.
The final upload transaction must recheck these constraints atomically.
"""
from __future__ import annotations

import json

from .m68_short_owner_policy import assess_short_policy


def assess_short_budget(queue, *, short_id, source_episode_id, media_sha256,
                        series_id, channel_id, made_for_kids,
                        contains_synthetic_media):
    policy = assess_short_policy(
        queue, short_id=short_id, source_episode_id=source_episode_id,
        media_sha256=media_sha256, series_id=series_id,
        channel_id=channel_id, made_for_kids=made_for_kids,
        contains_synthetic_media=contains_synthetic_media)
    reasons = list(policy["reasons"])
    with queue._connection() as db:
        row = db.execute(
            "SELECT max_uploads_24h FROM studio_youtube_private_policies WHERE series_id=?",
            (series_id,)).fetchone()
        now = queue.clock()
        jobs = db.execute(
            """SELECT state,created_at FROM jobs WHERE kind='youtube_private_upload'
               AND json_extract(payload,'$.series_id')=?""",
            (series_id,)).fetchall()
        recent = sum(j["created_at"] >= now - 86400 for j in jobs)
        active = sum(j["state"] in ("QUEUED", "LEASED") for j in jobs)
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='studio_recovery_uploads'"
        ).fetchone()
        if exists:
            recovery = db.execute(
                """SELECT u.state,u.created_at FROM studio_recovery_uploads u
                   JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                   WHERE i.series_id=?""", (series_id,)).fetchall()
            recent += sum(r["created_at"] >= now - 86400 for r in recovery)
            active += sum(r["state"] in
                          ("M63_PRIVATE_UPLOAD_READY_ONE_SHOT",
                           "M63_PRIVATE_UPLOAD_LEASED") for r in recovery)
    if row is None:
        reasons.append("OWNER_BUDGET_NOT_CONFIGURED")
    elif recent >= row["max_uploads_24h"]:
        reasons.append("SHARED_24H_PRIVATE_UPLOAD_BUDGET_EXHAUSTED")
    if active:
        reasons.append("ANOTHER_PRIVATE_UPLOAD_IN_FLIGHT")
    return {
        "status": ("SHORT_BUDGET_PRECHECK_PASSED_UPLOAD_STILL_BLOCKED"
                   if not reasons else "SHORT_BUDGET_BLOCKED"),
        "short_id": short_id, "series_id": series_id,
        "recent_upload_jobs": recent, "active_upload_jobs": active,
        "reasons": reasons,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
