"""Exclusive, bounded, fail-closed educational dashboard record writer.

Keeps a JSON array consumable by --educational-records. Replaces an episode
only after validating its new evidence; atomic rename avoids partial reads.
No network, upload, or release side effects.
"""
from __future__ import annotations

import json
import fcntl
import os
from pathlib import Path
import tempfile

from .m68_educational_dashboard_bridge import build_educational_dashboard


def record_cycle(path, *, series_id, handoff, cycle):
    target = Path(path)
    if not target.is_absolute() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError("absolute dashboard file in existing directory required")
    entry = {"series_id": series_id, "handoff": handoff, "cycle": cycle}
    build_educational_dashboard([entry])
    # Serialize concurrent writers across processes to prevent lost updates.
    # A separate stable lock file survives os.replace of the JSON snapshot.
    lock_path = target.with_name(target.name + ".lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(lock_fd, "rb") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = []
        if target.exists():
            if not target.is_file() or not 1 <= target.stat().st_size <= 2_000_000:
                raise ValueError("invalid existing dashboard file")
            existing = json.loads(target.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                raise ValueError("existing dashboard file must contain list")
        key = (series_id, handoff["source_episode_id"])
        updated = [row for row in existing if
                   (row.get("series_id"), row.get("handoff", {}).get("source_episode_id")) != key]
        updated.append(entry)
        build_educational_dashboard(updated)
        payload = json.dumps(updated, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(payload) > 2_000_000:
            raise ValueError("dashboard file size limit exceeded")
        fd, temp_name = tempfile.mkstemp(prefix=".lesson-dashboard-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, target)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    return {"status": "EDUCATIONAL_DASHBOARD_RECORDED",
            "series_id": series_id, "source_episode_id": handoff["source_episode_id"],
            "total_episodes": len(updated),
            "youtube_upload_authorized": False,
            "public_release_authorized": False}
