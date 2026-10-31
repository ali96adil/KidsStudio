"""Safe file-based bridge from lesson cycle results to dashboard snapshots.

Only explicit, validated results enter the read-only dashboard data. Does not
read directories recursively, inspect arbitrary paths or grant release rights.
"""
from __future__ import annotations

import json
from pathlib import Path

from .m68_lesson_dashboard_status import project_episode_status
from .m68_series_dashboard_summary import summarize_series


def build_educational_dashboard(entries):
    if not isinstance(entries, list) or len(entries) > 1000:
        raise ValueError("bounded educational entries required")
    grouped = {}
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"series_id", "handoff", "cycle"}:
            raise ValueError("invalid educational dashboard entry")
        series = item["series_id"]
        if not isinstance(series, str) or not 1 <= len(series) <= 120:
            raise ValueError("invalid series identifier")
        status = project_episode_status(item["handoff"], item["cycle"])
        key = (series, status["source_episode_id"])
        if key in seen:
            raise ValueError("duplicate educational episode")
        seen.add(key)
        grouped.setdefault(series, []).append(status)
    summaries = [summarize_series(series, rows)
                 for series, rows in sorted(grouped.items())]
    return {"schema_version": 1,
            "status": "EDUCATIONAL_MODEL_EVIDENCE_ONLY",
            "series": summaries,
            "total_series": len(summaries),
            "total_episodes": sum(x["total_episodes"] for x in summaries),
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def load_educational_dashboard(path):
    source = Path(path)
    if (not source.is_absolute() or source.is_symlink()
            or not source.is_file() or not 1 <= source.stat().st_size <= 2_000_000):
        raise ValueError("bounded absolute dashboard input required")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("dashboard input must be a list")
    return build_educational_dashboard(data)
