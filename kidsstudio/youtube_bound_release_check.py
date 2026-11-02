"""Read-only release eligibility check tied to exact upload and local media."""
from __future__ import annotations

from pathlib import Path

from .owner_media_approval import MediaApprovalStore, sha256_video
from .owner_release_gate import OwnerReleaseGate
from .owner_review_store import OwnerReviewStore
from .youtube_upload_binding import UploadBindingStore
from .youtube_release_inspection import inspect_release


def inspect_bound_release(
    reviews: OwnerReviewStore,
    releases: OwnerReleaseGate,
    media_approvals: MediaApprovalStore,
    upload_bindings: UploadBindingStore,
    episode_id: str,
    video_id: str,
    expected_channel_id: str,
    access_token: str,
    local_video: str | Path,
) -> dict:
    digest = sha256_video(local_video)
    plan = inspect_release(
        reviews, releases, episode_id, video_id, expected_channel_id, access_token
    )
    exact_approval = media_approvals.approved_for(episode_id, digest)
    exact_upload = upload_bindings.matches_latest(
        episode_id, digest, video_id, expected_channel_id
    )
    plan["local_video_sha256"] = digest
    plan["exact_media_approved"] = exact_approval
    plan["exact_upload_binding_verified"] = exact_upload
    plan["ready_for_manual_release"] = bool(
        plan["ready_for_manual_release"] and exact_approval and exact_upload
    )
    if not plan["ready_for_manual_release"]:
        plan["requested_privacy"] = None
    return plan
