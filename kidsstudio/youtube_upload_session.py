"""Private resumable upload session persistence for Raspberry Pi."""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from .owner_media_approval import sha256_video

def save_session(path: str | Path, *, session_url: str, video_path: str | Path, offset: int = 0) -> None:
    if not isinstance(session_url, str) or not session_url.startswith("https://www.googleapis.com/"):
        raise ValueError("invalid YouTube session URL")
    video = Path(video_path).resolve(strict=True)
    size = video.stat().st_size
    if size <= 0 or not 0 <= offset < size:
        raise ValueError("invalid video or offset")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        raise ValueError("session symlinks forbidden")
    payload = {
        "version": 1, "session_url": session_url,
        "video_path": str(video), "video_size": size,
        "media_sha256": sha256_video(video), "offset": offset,
    }
    fd, tmp = tempfile.mkstemp(prefix=".upload-", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def load_session(path: str | Path) -> dict:
    dest = Path(path)
    if dest.is_symlink():
        raise ValueError("session symlinks forbidden")
    info = dest.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("session file must be private (chmod 600)")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("session owner mismatch")
    if info.st_size > 16 * 1024:
        raise ValueError("session file too large")
    data = json.loads(dest.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("invalid session")
    url = data.get("session_url")
    if not isinstance(url, str) or not url.startswith("https://www.googleapis.com/"):
        raise ValueError("invalid session URL")
    video = Path(data["video_path"])
    if video.stat().st_size != data["video_size"] or sha256_video(video) != data["media_sha256"]:
        raise ValueError("video changed since upload session began")
    if not isinstance(data["offset"], int) or not 0 <= data["offset"] < data["video_size"]:
        raise ValueError("invalid stored offset")
    return data
