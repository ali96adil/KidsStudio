"""Read-only inspection of durable session creation intents.

Never exposes resumable URLs, OAuth credentials or filesystem paths.
"""
from __future__ import annotations

import json
import stat
import sqlite3
import hashlib
from pathlib import Path


def audit_session_intents(session_dir: str | Path, queue_path: str | Path | None = None) -> dict:
    folder = Path(session_dir) / ".session-intents"
    result = {"read_only": True, "pending_reconciliation": 0,
              "invalid_intents": 0, "items": [], "network_checked": False}
    if not folder.exists() and not folder.is_symlink():
        return result
    if folder.is_symlink() or not folder.is_dir():
        result["invalid_intents"] += 1
        return result
    known_jobs = set()
    if queue_path is not None:
        with sqlite3.connect(queue_path, timeout=10) as db:
            known_jobs = set(db.execute(
                "SELECT episode_id,channel_id FROM pi_upload_jobs"
            ).fetchall())
    for path in sorted(folder.iterdir()):
        if path.suffix != ".intent":
            continue
        try:
            if path.is_symlink():
                raise ValueError("symlink intent")
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode) or mode & 0o077 or path.stat().st_size > 4096:
                raise ValueError("invalid intent permissions or size")
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("invalid intent")
            episode = data.get("episode_id")
            channel = data.get("channel_id")
            digest = data.get("media_sha256")
            if not isinstance(episode, str) or not isinstance(channel, str) or not isinstance(digest, str):
                raise ValueError("invalid intent fields")
            from .pi_media_inbox import EPISODE_RE
            if not EPISODE_RE.fullmatch(episode) or not channel or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("invalid intent values")
            expected_name = hashlib.sha256((episode + "\\0" + channel).encode()).hexdigest() + ".intent"
            if path.name != expected_name:
                raise ValueError("unexpected intent filename")
            if (episode, channel) in known_jobs:
                continue
            result["pending_reconciliation"] += 1
            result["items"].append({
                "episode_id": episode,
                "action": "manual_reconcile_youtube_before_retry",
                "automatic_retry_allowed": False,
            })
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            result["invalid_intents"] += 1
    return result
