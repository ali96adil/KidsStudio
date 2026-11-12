"""Verified-file episode review report, read-only and offline."""
from __future__ import annotations

from .episode_review_overview import build_episode_review_overview
from .transfer_verify import verify_staged_file


def build_verified_episode_review(*, episode_id: str, video_root: str,
                                  relative_path: str, expected_sha256: str,
                                  notes_database: str, reviews_database: str) -> dict:
    verification = verify_staged_file(
        root=video_root, relative_path=relative_path,
        expected_sha256=expected_sha256)
    if verification["status"] != "VERIFIED":
        raise ValueError("video hash mismatch")
    report = build_episode_review_overview(
        episode_id=episode_id,
        current_video_sha256=verification["sha256"],
        notes_database=notes_database,
        reviews_database=reviews_database)
    report["status"] = "EPISODE_REVIEW_LOCAL_VIDEO_VERIFIED"
    report["video_bytes_verified"] = verification["bytes"]
    report["current_sha_supplied_by_caller_not_verified"] = False
    report["local_file_verified_at_report_time"] = True
    report["reviewer_identity_authenticated"] = False
    report["owner_publication_approval"] = False
    report["publication_performed"] = False
    return report
