"""Poll a trusted Pi staging directory for completed Mac transfers.

The transfer is treated as complete only when the MP4 matches the
manifest's declared size and SHA-256. Never publishes a video.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .pi_media_inbox import EPISODE_RE
from .pi_staging_handoff import prepare_private_upload


def scan_once(
    *,
    staging_dir: str | Path,
    inbox_dir: str | Path,
    session_dir: str | Path,
    queue,
    token_provider: Callable[[], str],
    expected_channel_id: str,
    title_for_episode: Callable[[str], str],
) -> list[dict]:
    staging = Path(staging_dir)
    if staging.is_symlink() or not staging.is_dir():
        raise ValueError("invalid staging directory")
    results = []
    for manifest_path in sorted(staging.glob("*.json")):
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 4096:
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict) or manifest.get("version") != 1:
                continue
            episode_id = manifest.get("episode_id")
            filename = manifest.get("filename")
            if not isinstance(episode_id, str) or not EPISODE_RE.fullmatch(episode_id):
                continue
            if not isinstance(filename, str) or Path(filename).name != filename or filename in (".", "..") or not filename.lower().endswith(".mp4"):
                continue
            expected_filename = episode_id + "-" + str(manifest.get("sha256", ""))[:16] + ".mp4"
            if filename != expected_filename or manifest_path.name != expected_filename[:-4] + ".json":
                continue
            source = staging / filename
            if source.is_symlink() or not source.is_file():
                continue
            # A temporary or partially copied file is not a completed
            # handoff; the SHA-256 is verified inside prepare_private_upload.
            if source.stat().st_size != manifest.get("size"):
                continue
            title = title_for_episode(episode_id)
            if not isinstance(title, str) or not title.strip():
                continue
            # A saved session already has a resumable URL; do not refresh
            # OAuth merely to rediscover a previously queued transfer.
            session_file = Path(session_dir) / (episode_id + "-" + manifest["sha256"][:16] + ".json")
            if session_file.exists():
                continue
            result = prepare_private_upload(
                staged_video=source,
                manifest_path=manifest_path,
                inbox_dir=inbox_dir,
                session_dir=session_dir,
                queue=queue,
                access_token=token_provider(),
                expected_channel_id=expected_channel_id,
                title=title,
            )
            results.append(result)
        except (OSError, ValueError, json.JSONDecodeError):
            # Incomplete or duplicate transfers are left for inspection.
            continue
    return results
