"""Pure offline YouTube PRIVATE upload request builder.

This module deliberately does not import Google SDKs, open files, or make HTTP calls.
"""
from __future__ import annotations

import argparse
import json

from .private_handoff import prepare_private_handoff


def build_private_upload_dry_run(*, private_root: str, relative_path: str,
                                 expected_sha256: str, episode_id: str,
                                 title: str, description: str = "",
                                 language: str = "ar",
                                 owner_private_upload_authorized: bool = False) -> dict:
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
        raise ValueError("invalid title")
    if not isinstance(description, str) or len(description) > 5000:
        raise ValueError("invalid description")
    if language not in ("ar", "en"):
        raise ValueError("unsupported language")
    handoff = prepare_private_handoff(
        private_root=private_root, relative_path=relative_path,
        expected_sha256=expected_sha256, episode_id=episode_id,
        owner_private_upload_authorized=owner_private_upload_authorized,
    )
    eligible = handoff["status"] == "READY_FOR_SEPARATE_PRIVATE_UPLOAD"
    return {
        "schema_version": 1,
        "status": "DRY_RUN_READY" if eligible else "BLOCKED",
        "episode_id": episode_id,
        "artifact_sha256": handoff["artifact_sha256"],
        "artifact_bytes": handoff["artifact_bytes"],
        "youtube_request_preview": {
            "snippet": {
                "title": title.strip(),
                "description": description,
                "defaultLanguage": language,
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": True,
            },
        },
        "made_for_kids_requires_owner_confirmation": True,
        "network_called": False,
        "credentials_loaded": False,
        "upload_submitted": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline YouTube private upload preview")
    parser.add_argument("--private-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument("--language", choices=["ar", "en"], default="ar")
    parser.add_argument("--authorize-private-upload", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_private_upload_dry_run(
            private_root=args.private_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256, episode_id=args.episode_id,
            title=args.title, description=args.description,
            language=args.language,
            owner_private_upload_authorized=args.authorize_private_upload,
        )
    except (ValueError, OSError):
        print(json.dumps({"status": "BLOCKED", "network_called": False,
                          "upload_submitted": False, "publication_approved": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "DRY_RUN_READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
