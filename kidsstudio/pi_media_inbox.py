"""Integrity-checked, local filesystem media ingestion for Raspberry Pi.

Use with a trusted LAN transfer mechanism (e.g. rsync over SSH).
This module does not expose an unauthenticated upload endpoint.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

EPISODE_RE = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
DIGEST_RE = re.compile(r"[a-f0-9]{64}")
MAX_VIDEO_SIZE = 20 * 1024 ** 3


def file_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(video_path: str | Path, episode_id: str) -> dict:
    if not EPISODE_RE.fullmatch(episode_id):
        raise ValueError("invalid episode ID")
    video = Path(video_path)
    if not video.is_file() or video.is_symlink() or video.suffix.lower() != ".mp4":
        raise ValueError("expected regular MP4")
    size = video.stat().st_size
    if not 0 < size <= MAX_VIDEO_SIZE:
        raise ValueError("invalid media size")
    return {"version": 1, "episode_id": episode_id, "size": size,
            "sha256": file_digest(video), "filename": video.name}


def ingest_media(source: str | Path, manifest: dict, inbox: str | Path) -> Path:
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("invalid manifest")
    episode_id = manifest.get("episode_id")
    digest = manifest.get("sha256")
    size = manifest.get("size")
    if not isinstance(episode_id, str) or not EPISODE_RE.fullmatch(episode_id):
        raise ValueError("invalid episode ID")
    if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid digest")
    if type(size) is not int or not 0 < size <= MAX_VIDEO_SIZE:
        raise ValueError("invalid media size")
    src = Path(source)
    if src.is_symlink() or not src.is_file() or src.suffix.lower() != ".mp4":
        raise ValueError("invalid source video")
    dest_dir = Path(inbox)
    dest_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if dest_dir.is_symlink():
        raise ValueError("inbox symlink forbidden")
    final = dest_dir / (episode_id + "-" + digest[:16] + ".mp4")
    if final.exists():
        if final.is_symlink() or final.stat().st_size != size or file_digest(final) != digest:
            raise ValueError("existing media integrity mismatch")
        return final
    fd, tmp = tempfile.mkstemp(prefix=".incoming-", suffix=".mp4", dir=dest_dir)
    try:
        with os.fdopen(fd, "wb") as output, src.open("rb") as stream:
            shutil.copyfileobj(stream, output, 4 * 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        if Path(tmp).stat().st_size != size or file_digest(tmp) != digest:
            raise ValueError("transferred media failed SHA-256 verification")
        os.replace(tmp, final)
        return final
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
