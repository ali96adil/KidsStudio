"""Plan-only YouTube visibility release check. Never calls YouTube APIs."""
from __future__ import annotations

import re
from .owner_release_cli import status
from .owner_review_store import OwnerReviewStore
from .owner_release_gate import OwnerReleaseGate

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

def plan_visibility_change(
    reviews: OwnerReviewStore,
    gate: OwnerReleaseGate,
    episode_id: str,
    video_id: str,
    current_privacy: str,
) -> dict:
    """Prepare a non-executable plan; caller must independently verify ownership and privacy."""
    if not isinstance(video_id, str) or VIDEO_ID_RE.fullmatch(video_id) is None:
        raise ValueError("invalid YouTube video ID")
    if current_privacy not in ("private", "unlisted", "public"):
        raise ValueError("invalid current privacy")
    current = status(reviews, gate, episode_id)
    ready = current["eligible"] and current_privacy == "private"
    return {
        "episode_id": episode_id,
        "video_id": video_id,
        "observed_privacy": current_privacy,
        "requested_privacy": "public" if ready else None,
        "review_state": current["review_state"],
        "release_decision": current["release_decision"],
        "ready_for_manual_release": ready,
        "youtube_request_sent": False,
        "youtube_visibility_changed": False,
        "requires_fresh_youtube_privacy_check": True,
        "requires_authenticated_owner_confirmation": True,
    }
