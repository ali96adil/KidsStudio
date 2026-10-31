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
    receipt = review(root, handoff, checks, reviewer_id)
    receipt["ai_evidence"] = observations
    receipt["ai_review_completed"] = True
    return receipt
