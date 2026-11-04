"""Record explicit, hash-pinned M68 short content review decisions."""
from __future__ import annotations

from .m67_master_handoff import verify_inventory

CHECKS = ("pedagogy", "visual", "audio", "age_appropriate",
          "copyright", "source_consistency")


def review(root, handoff, checks, reviewer):
    if (handoff.get("status") != "SHORT_HASH_PINNED_CONTENT_QA_PENDING"
            or handoff.get("short_id") != handoff.get("episode_id")
            or handoff.get("youtube_upload_authorized") is not False
            or handoff.get("public_release_authorized") is not False):
        raise ValueError("short handoff invalid")
    if (not isinstance(checks, dict) or set(checks) != set(CHECKS)
            or any(type(checks[k]) is not bool for k in CHECKS)):
        raise ValueError("six explicit content checks required")
    if not isinstance(reviewer, str) or not 3 <= len(reviewer.strip()) <= 100:
        raise ValueError("reviewer required")
    sha = verify_inventory(root, handoff)["sha256"]
    return {
        "status": "SHORT_CONTENT_QA_RECORDED",
        "decision": "PASS" if all(checks.values()) else "REJECT",
        "short_id": handoff["short_id"],
        "source_episode_id": handoff["source_episode_id"],
        "video_sha256": sha,
        "reviewer": reviewer.strip(),
        "checks": checks,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
