"""Raspberry Pi YouTube release preflight: inspect only, never publish."""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from .owner_release_gate import OwnerReleaseGate
from .owner_review_store import OwnerReviewStore
from .youtube_oauth_token import refresh_access_token
from .youtube_release_inspection import inspect_release

REQUIRED = ("client_id", "client_secret", "refresh_token", "channel_id")

def load_credentials(path: Path) -> dict:
    """Reject shared files, symlinks and unexpected credential structure."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("credential symlinks not allowed")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("credential file must be regular and private (chmod 600)")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("credential file must be owned by current user")
    if info.st_size > 16 * 1024:
        raise ValueError("credential file too large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != set(REQUIRED):
        raise ValueError("invalid credential fields")
    if any(not isinstance(data[k], str) or not data[k].strip() for k in REQUIRED):
        raise ValueError("credential fields must be nonempty strings")
    return data

def run_check(review_db: Path, release_db: Path, credentials: dict, episode: str, video_id: str) -> dict:
    reviews = OwnerReviewStore(review_db)
    gate = OwnerReleaseGate(release_db)
    reviews.initialize()
    gate.initialize()
    token = refresh_access_token(credentials["client_id"], credentials["client_secret"], credentials["refresh_token"])
    return inspect_release(reviews, gate, episode, video_id, credentials["channel_id"], token)

def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only YouTube preflight (no publishing)")
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--review-db", type=Path, required=True)
    parser.add_argument("--release-db", type=Path, required=True)
    parser.add_argument("--episode", required=True)
    parser.add_argument("--video-id", required=True)
    args = parser.parse_args()
    credentials = load_credentials(args.credentials)
    result = run_check(args.review_db, args.release_db, credentials, args.episode, args.video_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
