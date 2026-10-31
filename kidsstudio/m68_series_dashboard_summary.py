"""Read-only series-level educational pipeline dashboard aggregation.

Rows are produced by the episode status projection, not arbitrary UI flags.
"""
from __future__ import annotations

from collections import Counter

STAGES = {
    "EDUCATIONAL_SCRIPT_MODEL_PASS",
    "EDUCATIONAL_REVIEW_NEEDS_TRIAGE",
    "EDUCATIONAL_REVIEW_TECHNICAL_FAILURE",
}


def summarize_series(series_id, episodes):
    if not isinstance(series_id, str) or not 1 <= len(series_id) <= 120:
        raise ValueError("series identifier required")
    if not isinstance(episodes, list) or len(episodes) > 1000:
        raise ValueError("bounded episode list required")
    seen = set()
    counts = Counter()
    rows = []
    for row in episodes:
        if not isinstance(row, dict) or row.get("stage") not in STAGES:
            raise ValueError("invalid episode status")
        if (row.get("youtube_upload_authorized") is not False
                or row.get("public_release_authorized") is not False
                or row.get("media_quality_verified") is not False):
            raise ValueError("dashboard row cannot claim media release")
        episode_id = row.get("source_episode_id")
        if not isinstance(episode_id, str) or not episode_id or episode_id in seen:
            raise ValueError("duplicate or invalid episode identifier")
        seen.add(episode_id)
        attempts = row.get("revision_attempts")
        if type(attempts) is not int or not 0 <= attempts <= 3:
            raise ValueError("invalid revision count")
        counts[row["stage"]] += 1
        rows.append({"source_episode_id": episode_id, "stage": row["stage"],
                     "revision_attempts": attempts,
                     "next_action": row.get("next_action", "")})
    return {
        "series_id": series_id,
        "total_episodes": len(rows),
        "educational_script_pass": counts["EDUCATIONAL_SCRIPT_MODEL_PASS"],
        "needs_triage": counts["EDUCATIONAL_REVIEW_NEEDS_TRIAGE"],
        "technical_failures": counts["EDUCATIONAL_REVIEW_TECHNICAL_FAILURE"],
        "episodes": rows,
        "video_qa_completed": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
