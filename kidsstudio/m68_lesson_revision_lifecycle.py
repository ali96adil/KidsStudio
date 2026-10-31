"""Bounded, hash-pinned educational script revision lifecycle.

Pure state transitions only. Does not invent rewritten scripts or execute models.
"""
from __future__ import annotations

import re

SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_ATTEMPTS = 3


def start_revision(task, *, previous=None):
    if not isinstance(task, dict) or task.get("status") != "LESSON_REVISION_REQUIRED":
        raise ValueError("validated revision task required")
    if (not isinstance(task.get("script_sha256"), str)
            or not SHA.fullmatch(task["script_sha256"])
            or not isinstance(task.get("issues"), list)
            or not task["issues"]
            or task.get("assigned_role") != "script_revision_agent"
            or task.get("youtube_upload_authorized") is not False):
        raise ValueError("invalid revision task")
    if previous is None:
        history = []
        base = task["script_sha256"]
    else:
        if (not isinstance(previous, dict)
                or previous.get("short_id") != task.get("short_id")
                or previous.get("source_episode_id") != task.get("source_episode_id")
                or previous.get("video_sha256") != task.get("video_sha256")
                or previous.get("status") != "REVISION_AWAITING_REVIEW"
                or previous.get("current_script_sha256") != task["script_sha256"]):
            raise ValueError("previous revision must be reviewed before retry")
        history = previous.get("attempts")
        if not isinstance(history, list):
            raise ValueError("invalid revision history")
        base = previous.get("original_script_sha256")
        if not isinstance(base, str) or not SHA.fullmatch(base):
            raise ValueError("invalid original script hash")
    if len(history) >= MAX_ATTEMPTS:
        return {"status": "REVISION_LIMIT_REACHED", "short_id": task["short_id"],
                "source_episode_id": task["source_episode_id"],
                "video_sha256": task["video_sha256"],
                "original_script_sha256": base,
                "current_script_sha256": task["script_sha256"],
                "attempts": history,
                "requires_manual_triage": True,
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    return {"status": "REVISION_TASK_READY", "short_id": task["short_id"],
            "source_episode_id": task["source_episode_id"],
            "video_sha256": task["video_sha256"],
            "original_script_sha256": base,
            "current_script_sha256": task["script_sha256"],
            "attempts": history,
            "attempt_number": len(history) + 1,
            "issues": task["issues"],
            "assigned_role": "script_revision_agent",
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def record_revision(state, *, revised_script_sha256):
    if (not isinstance(state, dict) or state.get("status") != "REVISION_TASK_READY"
            or not isinstance(revised_script_sha256, str)
            or not SHA.fullmatch(revised_script_sha256)
            or revised_script_sha256 == state.get("current_script_sha256")):
        raise ValueError("new distinct pinned script hash required")
    attempts = list(state["attempts"])
    attempts.append({"attempt": state["attempt_number"],
                     "from_script_sha256": state["current_script_sha256"],
                     "to_script_sha256": revised_script_sha256,
                     "issues_addressed": state["issues"]})
    return {"status": "REVISION_AWAITING_REVIEW",
            "short_id": state["short_id"],
            "source_episode_id": state["source_episode_id"],
            "video_sha256": state["video_sha256"],
            "original_script_sha256": state["original_script_sha256"],
            "current_script_sha256": revised_script_sha256,
            "attempts": attempts, "requires_new_full_review": True,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}
