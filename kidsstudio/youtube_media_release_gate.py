"""Media-bound release gate; denies legacy episode-only approval by default."""
from __future__ import annotations

from pathlib import Path

from .owner_media_approval import MediaApprovalStore, sha256_video
from .owner_release_gate import OwnerReleaseGate
from .owner_review_store import OwnerReviewStore
from .youtube_release_plan import plan_visibility_change


def media_bound_release_plan(
    reviews: OwnerReviewStore,
    releases: OwnerReleaseGate,
    media_approvals: MediaApprovalStore,
    episode_id: str,
    video_id: str,
    current_privacy: str,
    local_video: str | Path,
) -> dict:
    digest = sha256_video(local_video)
    plan = plan_visibility_change(reviews, releases, episode_id, video_id, current_privacy)
    exact_approval = media_approvals.approved_for(episode_id, digest)
    plan["local_video_sha256"] = digest
    plan["exact_media_approved"] = exact_approval
    plan["ready_for_manual_release"] = bool(plan["ready_for_manual_release"] and exact_approval)
    if not plan["ready_for_manual_release"]:
        plan["requested_privacy"] = None
    return plan
