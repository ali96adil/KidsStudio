"""Pi staging handoff: verified MP4 -> private YouTube session -> queue.

A successful handoff creates a resumable upload session but does not
upload bytes itself or change visibility to public.
"""
from __future__ import annotations

import json
from pathlib import Path

from .pi_media_inbox import ingest_media
from .pi_upload_queue import PiUploadQueue
from .youtube_resumable_upload import start_session
from .youtube_upload_session import save_session


def prepare_private_upload(
    *,
    staged_video: str | Path,
    manifest_path: str | Path,
    inbox_dir: str | Path,
    session_dir: str | Path,
    queue: PiUploadQueue,
    access_token: str,
    expected_channel_id: str,
    title: str,
    description: str = "",
) -> dict:
    manifest_file = Path(manifest_path)
    if manifest_file.is_symlink() or manifest_file.stat().st_size > 4096:
        raise ValueError("invalid manifest file")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("invalid manifest")
    video = ingest_media(staged_video, manifest, inbox_dir)
    episode_id = manifest["episode_id"]
    session_folder = Path(session_dir)
    session_folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    if session_folder.is_symlink() or session_folder.stat().st_mode & 0o077:
        raise ValueError("session directory must be private")
    session_file = session_folder / (episode_id + "-" + manifest["sha256"][:16] + ".json")
    # A previously created session may still be valid. Do not create
    # another YouTube session for the same media automatically.
    if session_file.exists() or session_file.is_symlink():
        raise ValueError("upload session already exists; resume existing job")
    session_url = start_session(access_token, video.stat().st_size, title, description)
    save_session(session_file, session_url=session_url, video_path=video)
    job_id = queue.enqueue(episode_id, session_file, expected_channel_id)
    return {
        "job_id": job_id, "episode_id": episode_id,
        "video_path": str(video), "session_path": str(session_file),
        "privacy": "private", "queued": True,
    }
