"""M68 AI reviewer adapter: fail closed on incomplete independent evidence.

The caller supplies the actual AI inference callback. This module does not
pretend that model inference happened or automatically grant upload permission.
"""
from __future__ import annotations

from .m68_short_content_review import CHECKS, review


class ShortAIReviewError(ValueError):
    pass


def run_ai_review(root, handoff, *, infer, reviewer_id="kidsstudio-ai-reviewer"):
    if not callable(infer):
        raise ShortAIReviewError("configured AI inference callback required")
    if not isinstance(reviewer_id, str) or not reviewer_id.startswith("kidsstudio-ai-"):
        raise ShortAIReviewError("independent AI reviewer identity required")
    # Verify the source inventory before invoking potentially expensive models.
    # A forged handoff must never be sent for inference.
    from .m67_master_handoff import verify_inventory
    if (not isinstance(handoff, dict)
            or handoff.get("status") != "SHORT_HASH_PINNED_CONTENT_QA_PENDING"
            or handoff.get("short_id") != handoff.get("episode_id")
            or handoff.get("youtube_upload_authorized") is not False
            or handoff.get("public_release_authorized") is not False):
        raise ShortAIReviewError("invalid short handoff")
    try:
        actual_sha = verify_inventory(root, handoff)["sha256"]
    except Exception as exc:
        raise ShortAIReviewError("source media inventory verification failed") from exc
    if handoff.get("sha256") != actual_sha:
        raise ShortAIReviewError("handoff SHA does not match verified inventory")
    observations = {}
    checks = {}
    for axis in CHECKS:
        result = infer(axis=axis, root=root, handoff=handoff)
        if (not isinstance(result, dict)
                or result.get("axis") != axis
                or type(result.get("passed")) is not bool
                or not isinstance(result.get("evidence"), str)
                or not 12 <= len(result["evidence"].strip()) <= 2000
                or result.get("short_id") != handoff.get("short_id")
                or result.get("source_episode_id") != handoff.get("source_episode_id")
                or result.get("video_sha256") != handoff.get("sha256")):
            raise ShortAIReviewError("AI evidence missing, unbound, or invalid: " + axis)
        checks[axis] = result["passed"]
        observations[axis] = result["evidence"].strip()
    # A second integrity check catches media replacement while AI inference
    # is running. Never record a PASS for bytes that were not evaluated.
    try:
        after_sha = verify_inventory(root, handoff)["sha256"]
    except Exception as exc:
        raise ShortAIReviewError("media changed during AI review") from exc
    if after_sha != actual_sha:
        raise ShortAIReviewError("media hash changed during AI review")
    receipt = review(root, handoff, checks, reviewer_id)
    receipt["ai_evidence"] = observations
    receipt["ai_review_completed"] = True
    return receipt
