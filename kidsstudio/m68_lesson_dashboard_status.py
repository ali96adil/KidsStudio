"""Dashboard-safe educational review cycle status projection.

Read-only; model PASS is never interpreted as media upload approval.
"""
from __future__ import annotations


def project_episode_status(handoff, cycle):
    if not isinstance(handoff, dict) or not isinstance(cycle, dict):
        raise ValueError("handoff and cycle result required")
    short_id = handoff.get("short_id")
    episode_id = handoff.get("source_episode_id")
    video_sha = handoff.get("sha256")
    if (not isinstance(short_id, str) or not short_id
            or not isinstance(episode_id, str) or not episode_id
            or not isinstance(video_sha, str) or len(video_sha) != 64):
        raise ValueError("valid episode identity required")
    status = cycle.get("status")
    allowed = {"LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL",
               "LESSON_REVISION_LIMIT_REACHED",
               "LESSON_AUTO_CYCLE_FAILED"}
    if status not in allowed:
        raise ValueError("unsupported educational cycle status")
    attempts = cycle.get("attempts", [])
    if not isinstance(attempts, list) or len(attempts) > 3:
        raise ValueError("invalid revision attempt history")
    review = cycle.get("review")
    if status != "LESSON_AUTO_CYCLE_FAILED":
        if (not isinstance(review, dict)
                or review.get("short_id") != short_id
                or review.get("source_episode_id") != episode_id
                or review.get("video_sha256") != video_sha
                or review.get("youtube_upload_authorized") is not False
                or review.get("public_release_authorized") is not False):
            raise ValueError("review does not match episode identity")
    if status == "LESSON_MODEL_PASS_NOT_VIDEO_APPROVAL":
        checks = review.get("checks")
        if (not isinstance(checks, dict)
                or set(checks) != {"pedagogy", "source_consistency"}
                or any(value is not True for value in checks.values())):
            raise ValueError("unverified educational pass")
        stage = "EDUCATIONAL_SCRIPT_MODEL_PASS"
        next_action = "Continue independent audio, video, rights and source QA"
    elif status == "LESSON_REVISION_LIMIT_REACHED":
        stage = "EDUCATIONAL_REVIEW_NEEDS_TRIAGE"
        next_action = "Inspect unresolved model findings and revise lesson manually"
    else:
        stage = "EDUCATIONAL_REVIEW_TECHNICAL_FAILURE"
        next_action = "Inspect model service, inputs and error logs; retry safely"
    return {"short_id": short_id, "source_episode_id": episode_id,
            "video_sha256": video_sha, "stage": stage,
            "revision_attempts": len(attempts),
            "max_revision_attempts": 3,
            "remaining_revision_attempts": max(0, 3 - len(attempts)),
            "next_action": next_action,
            "media_quality_verified": False,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}
