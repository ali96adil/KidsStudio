"""Read-only PRIVATE upload eligibility check for a locally promoted artifact.

No network calls, no YouTube client, no queue mutation, no publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .transfer_verify import verify_staged_file

_INTERNAL_CANDIDATE = "verified-candidate.mp4"


def check_private_upload_candidate(*, private_root: str | Path,
                                   relative_path: str, expected_sha256: str,
                                   owner_private_upload_authorized: bool = False) -> dict:
    if type(owner_private_upload_authorized) is not bool:
        raise ValueError("authorization must be explicit boolean")
    root = Path(private_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("private root required")
    if root.stat().st_mode & 0o077:
        raise ValueError("private root permissions required")
    if (isinstance(relative_path, str)
            and _INTERNAL_CANDIDATE in relative_path.replace("\\", "/").split("/")):
        return {
            "schema_version": 1,
            "status": "PRIVATE_UPLOAD_BLOCKED",
            "integrity_verified": False,
            "owner_private_upload_authorized": owner_private_upload_authorized,
            "required_youtube_visibility": "private",
            "upload_submitted": False,
            "public_release_approved": False,
            "publication_approved": False,
        }
    verification = verify_staged_file(
        root=root, relative_path=relative_path, expected_sha256=expected_sha256
    )
    eligible = (verification["status"] == "VERIFIED" and
                owner_private_upload_authorized)
    return {
        "schema_version": 1,
        "status": "PRIVATE_UPLOAD_ELIGIBLE_NOT_SUBMITTED" if eligible
                  else "PRIVATE_UPLOAD_BLOCKED",
        "integrity_verified": verification["status"] == "VERIFIED",
        "owner_private_upload_authorized": owner_private_upload_authorized,
        "required_youtube_visibility": "private",
        "upload_submitted": False,
        "public_release_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline private upload eligibility check")
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--authorize-private-upload", action="store_true",
                        help="Owner permission for a later separate PRIVATE upload only")
    args = parser.parse_args(argv)
    try:
        result = check_private_upload_candidate(
            private_root=args.private_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256,
            owner_private_upload_authorized=args.authorize_private_upload,
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "PRIVATE_UPLOAD_BLOCKED",
                          "upload_submitted": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PRIVATE_UPLOAD_ELIGIBLE_NOT_SUBMITTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
