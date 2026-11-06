"""Read-only unified episode review overview, not an approval authority."""
from __future__ import annotations

import re

from .episode_notes import EpisodeNotes
from .review_freshness import project_review_freshness
from .video_review_history import VideoReviewHistory

_EPISODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def build_episode_review_overview(*, episode_id: str, current_video_sha256: str,
                                  notes_database: str, reviews_database: str) -> dict:
    if not isinstance(episode_id, str) or not _EPISODE.fullmatch(episode_id):
        raise ValueError("invalid episode id")
    notes = EpisodeNotes(notes_database).list_notes(episode_id=episode_id)
    reviews = VideoReviewHistory(reviews_database).list_reviews(episode_id=episode_id)
    freshness = project_review_freshness(
        reviews, current_video_sha256=current_video_sha256)
    unresolved = sum(not note["resolved"] for note in notes)
    return {
        "schema_version": 1,
        "status": "EPISODE_REVIEW_OVERVIEW_READ_ONLY",
        "episode_id": episode_id,
        "notes_total": len(notes),
        "notes_unresolved": unresolved,
        "notes_resolved": len(notes) - unresolved,
        "review_count": len(reviews),
        "latest_review_id": freshness["latest_review_id"],
        "latest_review_outcome": freshness["latest_review_outcome"],
        "review_freshness": freshness["status"],
        "current_video_sha256": freshness["current_video_sha256"],
        "current_sha_supplied_by_caller_not_verified": True,
        "reviewer_identity_authenticated": False,
        "owner_publication_approval": False,
        "publication_performed": False,
        "queue_mutated": False,
    }
