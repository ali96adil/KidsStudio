"""Offline series planning board, independent from worker queue and publishing."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STAGES = ("idea", "script", "review", "assets", "audio", "render", "quality", "private_upload", "owner_review", "approved")
MAX_BYTES = 262144
MAX_EPISODES = 200

def summarize(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("series manifest requires schema_version=1")
    series = manifest.get("series")
    if not isinstance(series, list) or len(series) > 50:
        raise ValueError("series must be a list with at most 50 entries")
    result = []
    seen_series = set()
    for item in series:
        if not isinstance(item, dict):
            raise ValueError("series entry must be an object")
        sid, title, episodes = item.get("id"), item.get("title"), item.get("episodes")
        if not isinstance(sid, str) or not 1 <= len(sid) <= 80 or sid in seen_series:
            raise ValueError("series ids must be unique nonempty strings")
        seen_series.add(sid)
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            raise ValueError("invalid series title")
        if not isinstance(episodes, list) or len(episodes) > MAX_EPISODES:
            raise ValueError("episodes must be a bounded list")
        seen_episodes = set()
        stages = {stage: 0 for stage in STAGES}
        recent = []
        for episode in episodes:
            if not isinstance(episode, dict):
                raise ValueError("episode must be an object")
            eid, name, stage = episode.get("id"), episode.get("title"), episode.get("stage")
            if not isinstance(eid, str) or not 1 <= len(eid) <= 80 or eid in seen_episodes:
                raise ValueError("episode ids must be unique within a series")
            seen_episodes.add(eid)
            if not isinstance(name, str) or not 1 <= len(name) <= 120 or stage not in STAGES:
                raise ValueError("invalid episode title or stage")
            stages[stage] += 1
            recent.append({"id": eid, "title": name, "stage": stage})
        result.append({
            "id": sid, "title": title, "episode_count": len(episodes),
            "stage_counts": stages, "episodes": recent,
        })
    return {"schema_version": 1, "series": result, "series_count": len(result),
            "episode_count": sum(x["episode_count"] for x in result),
            "read_only": True}

def load(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("series manifest too large")
    with source.open("r", encoding="utf-8") as stream:
        return summarize(json.load(stream))
