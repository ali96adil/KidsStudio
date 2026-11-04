"""M66 standalone offline upload journal safety model.

Demonstrates fail-closed restart handling. NOT integrated with the Pi uploader.
No Google API calls, credentials or network operations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

INITIAL = "READY"
UNCERTAIN = "RECONCILIATION_REQUIRED"
VERIFIED = "PRIVATE_VERIFIED"
ALLOWED = {INITIAL, UNCERTAIN, VERIFIED}


class JournalError(ValueError):
    pass


def read(path: Path) -> dict:
    if path.is_symlink():
        raise JournalError("symlink journal denied")
    if not path.exists():
        return {"state": INITIAL, "video_id": None}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise JournalError("unreadable journal") from exc
    if not isinstance(obj, dict) or set(obj) != {"state", "video_id"}:
        raise JournalError("invalid journal")
    if obj["state"] not in ALLOWED:
        raise JournalError("unknown state")
    if obj["state"] == VERIFIED:
        if not isinstance(obj["video_id"], str) or not obj["video_id"]:
            raise JournalError("verified record missing video id")
    elif obj["video_id"] is not None:
        raise JournalError("unexpected video id")
    return obj


def _write(path: Path, record: dict) -> None:
    if path.is_symlink() or not path.parent.is_dir() or path.parent.is_symlink():
        raise JournalError("unsafe journal path")
    # Exclusive temporary file prevents overwriting a concurrent temporary.
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink()


def begin_insert(path: Path) -> None:
    """Persist uncertain state BEFORE any hypothetical videos.insert call."""
    current = read(path)
    if current["state"] != INITIAL:
        raise JournalError("insert denied: already started or verified")
    _write(path, {"state": UNCERTAIN, "video_id": None})


def verified_private(path: Path, video_id: str, *, remote_private: bool, processed: bool) -> None:
    """Only a caller's independently verified remote result may advance state."""
    if read(path)["state"] != UNCERTAIN:
        raise JournalError("no pending reconciliation")
    if not isinstance(video_id, str) or not video_id or not remote_private or not processed:
        raise JournalError("remote PRIVATE processing evidence required")
    _write(path, {"state": VERIFIED, "video_id": video_id})


def may_insert(path: Path) -> bool:
    return read(path)["state"] == INITIAL
