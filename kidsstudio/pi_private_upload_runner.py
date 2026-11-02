"""Pi upload runner: private upload, read-only verification, trusted receipt.

Caller provides a valid OAuth token and a locally controlled video file.
Session persistence is handled before transfer so recovery can be invoked
separately. This module never makes a video public.
"""
from __future__ import annotations

from pathlib import Path

from .owner_media_approval import sha256_video
from .pi_private_upload_receipt import record_private_upload
from .youtube_resumable_upload import UploadError, start_session, upload_video
from .youtube_upload_recovery import resume_saved_upload
from .youtube_upload_session import save_session
from .youtube_upload_binding import UploadBindingStore
from .youtube_video_inspector import inspect_video
from .youtube_release_plan import VIDEO_ID_RE


def _verify_and_record(
    bindings: UploadBindingStore,
    *,
    episode_id: str,
    video_path: Path,
    upload_result: dict,
    expected_channel_id: str,
    access_token: str,
) -> dict:
    video_id = upload_result.get("id") if isinstance(upload_result, dict) else None
    if not isinstance(video_id, str) or VIDEO_ID_RE.fullmatch(video_id) is None:
        raise UploadError("YouTube upload did not return a valid video ID")
    status = upload_result.get("status")
    if not isinstance(status, dict) or status.get("privacyStatus") != "private":
        raise UploadError("YouTube upload result was not private")
    observed = inspect_video(video_id, access_token)
    if observed["video_id"] != video_id or observed["channel_id"] != expected_channel_id or observed["privacy"] != "private":
        raise UploadError("independent YouTube verification failed")
    digest = sha256_video(video_path)
    receipt = {
        "privacy": "private",
        "upload_succeeded": True,
        "video_id": video_id,
        "channel_id": observed["channel_id"],
        "media_sha256": digest,
    }
    return record_private_upload(
        bindings, episode_id=episode_id, local_video=video_path,
        receipt=receipt, expected_channel_id=expected_channel_id,
    )


def start_private_upload(
    bindings: UploadBindingStore,
    *,
    episode_id: str,
    video_path: str | Path,
    title: str,
    description: str,
    expected_channel_id: str,
    access_token: str,
    session_path: str | Path,
) -> dict:
    video = Path(video_path).resolve(strict=True)
    session_url = start_session(access_token, video.stat().st_size, title, description)
    save_session(session_path, session_url=session_url, video_path=video)
    result = upload_video(session_url, access_token, video)
    return _verify_and_record(
        bindings, episode_id=episode_id, video_path=video,
        upload_result=result, expected_channel_id=expected_channel_id,
        access_token=access_token,
    )


def resume_private_upload(
    bindings: UploadBindingStore,
    *,
    episode_id: str,
    session_path: str | Path,
    expected_channel_id: str,
    access_token: str,
) -> dict:
    from .youtube_upload_session import load_session
    session = load_session(session_path)
    result = resume_saved_upload(session_path, access_token)
    return _verify_and_record(
        bindings, episode_id=episode_id, video_path=Path(session["video_path"]),
        upload_result=result, expected_channel_id=expected_channel_id,
        access_token=access_token,
    )
