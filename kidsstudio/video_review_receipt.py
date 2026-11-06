"""Offline immutable review receipt bound to one verified video SHA-256.

No credentials, video uploads, approval, or network operations.
"""
from __future__ import annotations

import argparse
import json
import re

from .transfer_verify import verify_staged_file

_EPISODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def build_video_review_receipt(*, episode_id: str, video_root: str,
                               relative_path: str, expected_sha256: str,
                               reviewer_notes: str = "",
                               review_outcome: str = "NEEDS_REVIEW") -> dict:
    if not isinstance(episode_id, str) or not _EPISODE.fullmatch(episode_id):
        raise ValueError("invalid episode id")
    if review_outcome not in {"NEEDS_REVIEW", "REVISION_REQUIRED", "ACCEPTED_PRIVATE"}:
        raise ValueError("invalid review outcome")
    if not isinstance(reviewer_notes, str) or len(reviewer_notes) > 2000:
        raise ValueError("invalid reviewer notes")
    verification = verify_staged_file(
        root=video_root, relative_path=relative_path,
        expected_sha256=expected_sha256)
    if verification.get("status") != "MATCH":
        raise ValueError("video SHA-256 mismatch or unsafe source")
    return {
        "schema_version": 1,
        "episode_id": episode_id,
        "video_sha256": expected_sha256.lower(),
        "video_bytes": verification["size_bytes"],
        "review_outcome": review_outcome,
        "reviewer_notes": reviewer_notes,
        "reviewer_identity_authenticated": False,
        "owner_publication_approval": False,
        "publication_performed": False,
        "queue_mutated": False,
        "receipt_persisted": False,
        "status": "VIDEO_REVIEW_RECEIPT_DRAFT",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only SHA-bound video review draft")
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--video-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--review-outcome", default="NEEDS_REVIEW",
                        choices=["NEEDS_REVIEW", "REVISION_REQUIRED", "ACCEPTED_PRIVATE"])
    parser.add_argument("--reviewer-notes", default="")
    args = parser.parse_args(argv)
    try:
        result = build_video_review_receipt(**vars(args))
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"status": "REVIEW_RECEIPT_BLOCKED",
                          "owner_publication_approval": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
