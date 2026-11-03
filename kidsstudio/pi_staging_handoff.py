"""Pi staging handoff: verified MP4 -> private YouTube session -> queue.

A successful handoff creates a resumable upload session but does not
upload bytes itself or change visibility to public.
"""
from __future__ import annotations

import json
import sqlite3
import fcntl
import os
import hashlib
from pathlib import Path

from .pi_media_inbox import ingest_media
from .pi_session_intent_names import intent_filenames
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
    with sqlite3.connect(queue.path, timeout=10) as db:
        existing = db.execute(
            "SELECT 1 FROM pi_upload_jobs WHERE episode_id=? AND channel_id=? LIMIT 1",
            (episode_id, expected_channel_id),
        ).fetchone()
    if existing:
        raise ValueError("episode already has an upload job; manual reconciliation required")
    # Reserve this episode across independent processes BEFORE calling YouTube.
    # Keep the lock file after exit: its inode must remain stable for flock.
    lock_folder = session_folder / ".episode-locks"
    lock_folder.mkdir(mode=0o700, exist_ok=True)
    if lock_folder.is_symlink() or lock_folder.stat().st_mode & 0o077:
        raise ValueError("invalid episode lock directory")
    lock_path = lock_folder / (episode_id + ".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        if session_file.exists() or session_file.is_symlink():
            raise ValueError("upload session already exists; resume existing job")
        with sqlite3.connect(queue.path, timeout=10) as db:
            existing = db.execute(
                "SELECT 1 FROM pi_upload_jobs WHERE episode_id=? AND channel_id=? LIMIT 1",
                (episode_id, expected_channel_id),
            ).fetchone()
        if existing:
            raise ValueError("episode already has an upload job; manual reconciliation required")
        # Durable intent is written BEFORE the external request. A crash or
        # timeout may leave a remote session we cannot safely rediscover.
        # Never automatically create another one without operator review.
        intent_folder = session_folder / ".session-intents"
        intent_folder.mkdir(mode=0o700, exist_ok=True)
        if intent_folder.is_symlink() or intent_folder.stat().st_mode & 0o077:
            raise ValueError("invalid intent directory")
        canonical_name, legacy_name = intent_filenames(episode_id, expected_channel_id)
        intent_file = intent_folder / canonical_name
        if any((intent_folder / name).exists() or (intent_folder / name).is_symlink()
               for name in (canonical_name, legacy_name)):
            raise ValueError("previous upload session attempt requires manual reconciliation")
        intent_fd = os.open(intent_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(intent_fd, "w", encoding="utf-8") as stream:
                json.dump({"version": 1, "episode_id": episode_id,
                           "channel_id": expected_channel_id,
                           "media_sha256": manifest["sha256"],
                           "state": "manual_reconcile_if_session_missing"}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            directory_fd = os.open(intent_folder, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except BaseException:
            # Keep the marker even on ambiguous write failures: fail closed.
            raise
        session_url = start_session(access_token, video.stat().st_size, title, description)
        save_session(session_file, session_url=session_url, video_path=video)
        job_id = queue.enqueue(episode_id, session_file, expected_channel_id)
    finally:
        os.close(fd)
    return {
        "job_id": job_id, "episode_id": episode_id,
        "video_path": str(video), "session_path": str(session_file),
        "privacy": "private", "queued": True,
    }
