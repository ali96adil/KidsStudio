"""Offline, immutable private-upload handoff contract for a Pi operator.

Produces JSON on stdout only. No file creation, network, or API access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .private_upload_gate import check_private_upload_candidate
from .transfer_verify import verify_staged_file


def prepare_private_handoff(*, private_root: str | Path, relative_path: str,
                            expected_sha256: str, episode_id: str,
                            owner_private_upload_authorized: bool = False) -> dict:
    if not isinstance(episode_id, str) or not episode_id.isascii() or not (
        1 <= len(episode_id) <= 80
    ) or not all(c.isalnum() or c in "_-" for c in episode_id):
        raise ValueError("invalid episode identifier")
    gate = check_private_upload_candidate(
        private_root=private_root, relative_path=relative_path,
        expected_sha256=expected_sha256,
        owner_private_upload_authorized=owner_private_upload_authorized,
    )
    verified = verify_staged_file(root=private_root, relative_path=relative_path,
                                  expected_sha256=expected_sha256)
    return {
        "schema_version": 1,
        "episode_id": episode_id,
        "artifact_sha256": verified["sha256"],
        "artifact_bytes": verified["bytes"],
        "status": "READY_FOR_SEPARATE_PRIVATE_UPLOAD" if (
            gate["status"] == "PRIVATE_UPLOAD_ELIGIBLE_NOT_SUBMITTED"
        ) else "BLOCKED",
        "visibility": "private",
        "requires_separate_uploader": True,
        "requires_owner_video_review": True,
        "upload_submitted": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline private-upload handoff contract")
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--authorize-private-upload", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = prepare_private_handoff(
            private_root=args.private_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256, episode_id=args.episode_id,
            owner_private_upload_authorized=args.authorize_private_upload,
        )
    except (OSError, ValueError):
        print(json.dumps({"status": "BLOCKED", "upload_submitted": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "READY_FOR_SEPARATE_PRIVATE_UPLOAD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
