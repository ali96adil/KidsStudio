"""Read-only private upload handoff preflight; never invokes YouTube.

A VERIFIED file is only eligible for a separate, explicitly approved PRIVATE
upload workflow. This report does not authorize or perform any upload.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .transfer_verify import verify_staged_file


def inspect_private_upload(*, inbox_root: str | Path, relative_path: str,
                           expected_sha256: str, visibility: str = "private",
                           owner_reviewed: bool = False) -> dict:
    if visibility != "private":
        raise ValueError("only private visibility is supported")
    if type(owner_reviewed) is not bool:
        raise ValueError("owner_reviewed must be boolean")
    if not isinstance(relative_path, str) or not relative_path.lower().endswith(".mp4"):
        raise ValueError("expected .mp4 file")
    verified = verify_staged_file(root=inbox_root, relative_path=relative_path,
                                  expected_sha256=expected_sha256)
    checks = {
        "sha256_matches": verified["status"] == "VERIFIED",
        "mp4_extension": True,
        "nonempty_file": verified["bytes"] > 0,
        "private_visibility": True,
        "owner_review_recorded": owner_reviewed,
    }
    return {
        "schema_version": 1,
        "status": "READY_FOR_MANUAL_PRIVATE_UPLOAD" if all(checks.values())
                  else "HOLD_PRIVATE",
        "checks": checks,
        "sha256": verified["sha256"],
        "bytes": verified["bytes"],
        "video_decoding_verified": False,
        "rights_verified": False,
        "youtube_request_performed": False,
        "upload_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline private-upload handoff preflight")
    parser.add_argument("--inbox-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--owner-reviewed", action="store_true",
                        help="Operator asserts review occurred; no verification of identity")
    args = parser.parse_args(argv)
    try:
        report = inspect_private_upload(
            inbox_root=args.inbox_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256,
            owner_reviewed=args.owner_reviewed,
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "PREFLIGHT_ERROR",
                          "youtube_request_performed": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "READY_FOR_MANUAL_PRIVATE_UPLOAD" else 1


if __name__ == "__main__":
    raise SystemExit(main())
