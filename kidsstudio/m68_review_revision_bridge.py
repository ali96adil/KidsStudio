"""Single bounded M68 script review -> revision -> review orchestration.

The revision proposal is not silently treated as a new episode: the lesson
plan's script hash must be updated and revalidated before any production.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .m68_lesson_revision_queue import plan_revision
from .m68_lesson_revision_lifecycle import start_revision
from .m68_local_script_rewriter import propose_revision


def review_and_revise(handoff, *, review_receipt, script_path, lesson_path,
                      proposed_script_path, rewriter, previous=None):
    task = plan_revision(handoff, review_receipt)
    if task["status"] == "LESSON_MODEL_PASS_NO_REVISION":
        return {"status": "LESSON_REVIEW_PASS_NO_REVISION",
                "review": review_receipt,
                "youtube_upload_authorized": False,
                "public_release_authorized": False}
    state = start_revision(task, previous=previous)
    if state["status"] == "REVISION_LIMIT_REACHED":
        return state
    if hashlib.sha256(Path(script_path).read_bytes()).hexdigest() != task["script_sha256"]:
        raise ValueError("reviewed script changed before revision")
    proposal = propose_revision(
        state, script_path=script_path, lesson_path=lesson_path,
        output_path=proposed_script_path, rewriter=rewriter)
    return {"status": "REVISION_CREATED_REVIEW_PENDING",
            "review": review_receipt,
            "proposal": proposal,
            "next_action": "update lesson-plan script_sha256 and rerun full lesson review",
            "youtube_upload_authorized": False,
            "public_release_authorized": False}
