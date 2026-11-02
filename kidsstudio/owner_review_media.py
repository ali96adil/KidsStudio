"""Private local episode video registry; paths stay server-side, never exposed in HTML."""
from __future__ import annotations

import json
from pathlib import Path
from .owner_video_reviews import _validate_id

MAX_REGISTRY = 262144
ALLOWED_EXT = frozenset({".mp4", ".webm"})

def load_registry(path: str | Path, media_root: str | Path) -> dict[str, Path]:
    registry = Path(path).expanduser().resolve()
    root = Path(media_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("media root must be a directory")
    if registry.stat().st_size > MAX_REGISTRY:
        raise ValueError("media registry too large")
    with registry.open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("episodes"), dict):
        raise ValueError("invalid media registry")
    result = {}
    if len(data["episodes"]) > 500:
        raise ValueError("too many video attachments")
    for episode_id, relative in data["episodes"].items():
        _validate_id(episode_id)
        if not isinstance(relative, str) or not relative or len(relative) > 512:
            raise ValueError("invalid media path")
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() not in ALLOWED_EXT:
            raise ValueError("unsafe media path")
        target = (root / rel).resolve(strict=True)
        if not target.is_relative_to(root) or not target.is_file():
            raise ValueError("video must be a file within media root")
        result[episode_id] = target
    return result

def video_mime(path: Path) -> str:
    return "video/mp4" if path.suffix.lower() == ".mp4" else "video/webm"
