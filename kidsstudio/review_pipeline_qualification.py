"""Offline end-to-end qualification of the private episode review pipeline.

Uses synthetic local bytes only. Never invokes media generation or upload.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile

from .episode_notes import EpisodeNotes
from .video_review_history import VideoReviewHistory
from .verified_episode_review import build_verified_episode_review


def run_review_pipeline_qualification() -> dict:
    with tempfile.TemporaryDirectory(prefix="kidsstudio-review-") as temp:
        root = Path(temp) / "private"
        root.mkdir(mode=0o700)
        video = root / "synthetic.mp4"
        notes_db = root / "notes.sqlite"
        reviews_db = root / "reviews.sqlite"
        notes = EpisodeNotes(notes_db)
        notes.initialize()
        history = VideoReviewHistory(reviews_db)
        history.initialize()
        episode = "colors_ar_qualification"

        video.write_bytes(b"KidsStudio synthetic video version 1 - NOT A REAL MP4")
        first_sha = hashlib.sha256(video.read_bytes()).hexdigest()
        note = notes.add(episode_id=episode, text="Synthetic: check voice timing")
        history.record(
            episode_id=episode, video_root=str(root),
            relative_path=video.name, expected_sha256=first_sha,
            review_outcome="ACCEPTED_PRIVATE",
            reviewer_notes="Synthetic review only")
        first = build_verified_episode_review(
            episode_id=episode, video_root=str(root),
            relative_path=video.name, expected_sha256=first_sha,
            notes_database=str(notes_db), reviews_database=str(reviews_db))
        if first["review_freshness"] != "CURRENT_VERSION_ACCEPTED_PRIVATE_ONLY":
            raise AssertionError("initial review not matched")
        if first["notes_unresolved"] != 1:
            raise AssertionError("pending note missing")

        video.write_bytes(b"KidsStudio synthetic video version 2 - NOT A REAL MP4")
        second_sha = hashlib.sha256(video.read_bytes()).hexdigest()
        second = build_verified_episode_review(
            episode_id=episode, video_root=str(root),
            relative_path=video.name, expected_sha256=second_sha,
            notes_database=str(notes_db), reviews_database=str(reviews_db))
        if second["review_freshness"] != "LATEST_REVIEW_STALE":
            raise AssertionError("old review incorrectly accepted for new video")
        try:
            build_verified_episode_review(
                episode_id=episode, video_root=str(root),
                relative_path=video.name, expected_sha256=first_sha,
                notes_database=str(notes_db), reviews_database=str(reviews_db))
        except ValueError:
            pass
        else:
            raise AssertionError("tampered/changed video accepted with old SHA")

        history.record(
            episode_id=episode, video_root=str(root),
            relative_path=video.name, expected_sha256=second_sha,
            review_outcome="REVISION_REQUIRED",
            reviewer_notes="Synthetic revision requested")
        final = build_verified_episode_review(
            episode_id=episode, video_root=str(root),
            relative_path=video.name, expected_sha256=second_sha,
            notes_database=str(notes_db), reviews_database=str(reviews_db))
        if final["review_freshness"] != "CURRENT_VERSION_REVISION_REQUIRED":
            raise AssertionError("latest revision not projected")
        if final["review_count"] != 2 or first["owner_publication_approval"] or final["owner_publication_approval"]:
            raise AssertionError("review history or publication guard failed")
        if note is None:
            raise AssertionError("note creation failed")
        return {
            "status": "OFFLINE_REVIEW_PIPELINE_PASS",
            "synthetic_video_only": True,
            "checks": [
                "initial_private_acceptance_is_not_public_approval",
                "unresolved_note_visible",
                "new_video_invalidates_old_review",
                "old_video_sha_fails_verification",
                "new_revision_review_retained",
                "two_review_versions_preserved",
                "no_publication_authority",
            ],
            "real_mac_pi_qualification": "NOT_RUN",
            "owner_publication_approval": False,
        }


def main() -> int:
    import json
    print(json.dumps(run_review_pipeline_qualification(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
