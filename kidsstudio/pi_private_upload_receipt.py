"""Validate a private upload receipt and bind it to an exact local video.

This module does not upload, publish or trust a receipt as a YouTube API
verification. Call only after an authenticated uploader reports success.
"""
from __future__ import annotations

from pathlib import Path

from .owner_media_approval import sha256_video
from .youtube_upload_binding import UploadBindingStore
from .youtube_release_plan import VIDEO_ID_RE


def record_private_upload(
    bindings: UploadBindingStore,
    *,
    episode_id: str,
    local_video: str | Path,
    receipt: dict,
    expected_channel_id: str,
) -> dict:
    if not isinstance(receipt, dict):
        raise ValueError("invalid upload receipt")
    if receipt.get("privacy") != "private":
        raise ValueError("only private uploads may be recorded")
    if receipt.get("upload_succeeded") is not True:
        raise ValueError("upload must be confirmed successful")
    video_id = receipt.get("video_id")
    if not isinstance(video_id, str) or VIDEO_ID_RE.fullmatch(video_id) is None:
        raise ValueError("invalid YouTube video ID")
    if not isinstance(expected_channel_id, str) or not expected_channel_id:
        raise ValueError("expected channel required")
    if receipt.get("channel_id") != expected_channel_id:
        raise ValueError("uploaded channel does not match expected channel")
    digest = sha256_video(local_video)
    if receipt.get("media_sha256") != digest:
        raise ValueError("upload receipt digest differs from current file")
    bindings.record(episode_id, digest, video_id, expected_channel_id)
    return {
        "episode_id": episode_id,
        "video_id": video_id,
        "media_sha256": digest,
        "channel_id": expected_channel_id,
        "recorded_private_upload": True,
        "youtube_visibility_changed": False,
    }
