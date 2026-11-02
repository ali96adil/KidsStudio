"""Read-only per-episode progress with sanitized Pi upload states."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .owner_video_reviews import _validate_id

UPLOAD_STATES = frozenset({"pending", "running", "completed", "failed"})


def episode_statuses(series_data: dict, reviews: dict,
                     pi_queue_db: str | Path) -> list[dict]:
    """One row per episode; never expose session URLs, paths or credentials.

    The newest upload job for each episode determines the displayed state.
    """
    with sqlite3.connect(pi_queue_db, timeout=10) as db:
        jobs = db.execute(
            "SELECT episode_id,state FROM pi_upload_jobs ORDER BY id DESC"
        ).fetchall()
    latest_uploads = {}
    for episode_id, state in jobs:
        if episode_id not in latest_uploads and state in UPLOAD_STATES:
            latest_uploads[episode_id] = state
    result = []
    for series in series_data["series"]:
        for episode in series["episodes"]:
            episode_id = episode["id"]
            _validate_id(episode_id)
            review = reviews.get(episode_id, {})
            review_state = review.get("state", "needs_review")
            if review_state not in ("needs_review", "changes_requested", "approved"):
                review_state = "needs_review"
            upload = latest_uploads.get(episode_id, "not_started")
            if review_state == "changes_requested":
                next_step = "revise_video"
            elif upload == "failed":
                next_step = "check_upload"
            elif upload == "completed":
                next_step = "owner_review" if review_state != "approved" else "private_upload_complete"
            elif upload in ("pending", "running"):
                next_step = "wait_for_private_upload"
            elif review_state == "approved":
                next_step = "prepare_private_upload"
            else:
                next_step = "continue_production_or_review"
            result.append({
                "episode_id": episode_id,
                "series": series["title"],
                "title": episode["title"],
                "production_stage": episode["stage"],
                "review_state": review_state,
                "upload_state": upload,
                "next_step": next_step,
            })
    return result
