"""Read-only latest-review freshness projection for one episode.

Review recency alone never authorizes publication.
"""
from __future__ import annotations

import re

_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")


def project_review_freshness(reviews: list[dict], *, current_video_sha256: str) -> dict:
    if not isinstance(current_video_sha256, str) or not _SHA.fullmatch(current_video_sha256):
        raise ValueError("invalid current video SHA")
    if not isinstance(reviews, list):
        raise ValueError("reviews must be a list")
    current = current_video_sha256.lower()
    latest = None
    seen_ids: set[int] = set()
    for record in reviews:
        if not isinstance(record, dict):
            raise ValueError("invalid review")
        rid = record.get("review_id")
        sha = record.get("video_sha256")
        outcome = record.get("review_outcome")
        if type(rid) is not int or rid <= 0 or rid in seen_ids:
            raise ValueError("invalid review id")
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise ValueError("invalid review SHA")
        if outcome not in {"NEEDS_REVIEW", "REVISION_REQUIRED", "ACCEPTED_PRIVATE"}:
            raise ValueError("invalid review outcome")
        seen_ids.add(rid)
        if latest is None or rid > latest["review_id"]:
            latest = {"review_id": rid, "video_sha256": sha.lower(),
                      "review_outcome": outcome}
    if latest is None:
        state = "NO_REVIEW"
    elif latest["video_sha256"] != current:
        state = "LATEST_REVIEW_STALE"
    elif latest["review_outcome"] == "REVISION_REQUIRED":
        state = "CURRENT_VERSION_REVISION_REQUIRED"
    elif latest["review_outcome"] == "NEEDS_REVIEW":
        state = "CURRENT_VERSION_NEEDS_REVIEW"
    else:
        state = "CURRENT_VERSION_ACCEPTED_PRIVATE_ONLY"
    return {
        "status": state,
        "current_video_sha256": current,
        "latest_review_id": latest["review_id"] if latest else None,
        "latest_review_sha256": latest["video_sha256"] if latest else None,
        "latest_review_outcome": latest["review_outcome"] if latest else None,
        "owner_publication_approval": False,
        "publication_performed": False,
        "queue_mutated": False,
    }
