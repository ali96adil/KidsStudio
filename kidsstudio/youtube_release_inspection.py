"""Check YouTube privacy and channel identity before making a release plan."""
from __future__ import annotations

from .youtube_video_inspector import inspect_video, YouTubeInspectError
from .youtube_release_plan import plan_visibility_change
from .owner_release_gate import OwnerReleaseGate
from .owner_review_store import OwnerReviewStore


def inspect_release(
    reviews: OwnerReviewStore,
    gate: OwnerReleaseGate,
    episode_id: str,
    video_id: str,
    expected_channel_id: str,
    access_token: str,
) -> dict:
    if not isinstance(expected_channel_id, str) or not expected_channel_id.strip():
        raise ValueError("expected channel ID required")
    observed = inspect_video(video_id, access_token)
    if observed["channel_id"] != expected_channel_id:
        raise YouTubeInspectError("video does not belong to expected channel")
    plan = plan_visibility_change(reviews, gate, episode_id, video_id, observed["privacy"])
    plan["channel_id_verified"] = True
    plan["youtube_privacy_observed_via_api"] = True
    plan["youtube_request_sent"] = False
    return plan
