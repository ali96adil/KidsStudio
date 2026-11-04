"""Private append-only local agent handoff ledger, with checkpoint validation.

No network, rendering, upload or public release. Local cooperating writers only.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .episode_stage_checkpoints import _path, status

AGENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
EVENTS = {"assigned", "started", "completed", "failed"}
MAX_LINE = 16384


def _ledger_path(root: str | Path, episode_id: str) -> Path:
    return _path(root, episode_id).with_suffix(".handoffs.jsonl")


def read_handoffs(root: str | Path, episode_id: str) -> dict:
    checkpoint = status(root, episode_id)
    path = _ledger_path(root, episode_id)
    events = []
    if path.is_symlink():
        raise ValueError("symlink ledger rejected")
    if path.exists():
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            for line in handle:
                if len(line) > MAX_LINE:
                    raise ValueError("oversized handoff record")
                event = json.loads(line)
                if (not isinstance(event, dict) or
                        event.get("episode_id") != episode_id or
                        event.get("stage") not in checkpoint["stages"] or
                        event.get("event") not in EVENTS or
                        not AGENT_RE.fullmatch(str(event.get("agent_id", "")))):
                    raise ValueError("invalid handoff record")
                events.append(event)
    return {"episode_id": episode_id, "events": events,
            "event_count": len(events), "next_stage": checkpoint["next_stage"],
            "read_only": True, "youtube_uploaded": False,
            "public_release_authorized": False}


def record_handoff(root: str | Path, episode_id: str, stage: str,
                   agent_id: str, event: str, note: str = "") -> dict:
    checkpoint = status(root, episode_id)
    if stage not in checkpoint["stages"]:
        raise ValueError("unknown stage")
    if not isinstance(agent_id, str) or not AGENT_RE.fullmatch(agent_id):
        raise ValueError("invalid agent_id")
    if event not in EVENTS:
        raise ValueError("invalid handoff event")
    if not isinstance(note, str) or len(note) > 2000:
        raise ValueError("invalid note")
    path = _ledger_path(root, episode_id)
    if path.is_symlink():
        raise ValueError("symlink ledger rejected")
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        payload = {"episode_id": episode_id, "stage": stage,
                   "agent_id": agent_id, "event": event, "note": note,
                   "timestamp_utc": datetime.now(timezone.utc).isoformat()}
        line = (json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode()
        if len(line) > MAX_LINE:
            raise ValueError("oversized handoff record")
        os.write(fd, line)
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    return payload
