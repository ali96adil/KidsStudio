"""Local owner review journal; never uploads, publishes or changes queue jobs."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from uuid import uuid4

STATES = frozenset({"needs_review", "changes_requested", "approved"})
SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
MAX_NOTES = 2000
MAX_FILE = 1_048_576

def _validate_id(value: str) -> None:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise ValueError("invalid episode id")

def _validate_note(note: str) -> None:
    if not isinstance(note, str) or len(note) > MAX_NOTES:
        raise ValueError("note must be at most 2000 characters")

def read_journal(path: str | Path) -> dict:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return {"schema_version": 1, "reviews": []}
    if target.stat().st_size > MAX_FILE:
        raise ValueError("review journal too large")
    with target.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("reviews"), list):
        raise ValueError("invalid review journal")
    return data

def latest_reviews(data: dict) -> dict[str, dict]:
    latest = {}
    for item in data["reviews"]:
        if not isinstance(item, dict):
            raise ValueError("invalid review entry")
        eid, state = item.get("episode_id"), item.get("state")
        _validate_id(eid)
        if state not in STATES:
            raise ValueError("invalid review state")
        latest[eid] = {
            "episode_id": eid,
            "state": state,
            "note": item.get("note", ""),
            "recorded_at": item.get("recorded_at", ""),
        }
    return latest

def append_review(path: str | Path, *, episode_id: str, state: str, note: str = "") -> dict:
    """Record owner decision; approval alone NEVER initiates publishing."""
    _validate_id(episode_id)
    if state not in STATES:
        raise ValueError("invalid review state")
    _validate_note(note)
    target = Path(path).expanduser().resolve()
    data = read_journal(target)
    latest_reviews(data)  # validate existing history before changing anything
    if len(data["reviews"]) >= 2000:
        raise ValueError("review journal reached maximum entries")
    entry = {
        "review_id": uuid4().hex,
        "episode_id": episode_id,
        "state": state,
        "note": note,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    data["reviews"].append(entry)
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    if len(serialized.encode("utf-8")) > MAX_FILE:
        raise ValueError("review journal reached size limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name("." + target.name + "." + uuid4().hex + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()
    return entry
