"""Offline precheck of a Mac render before transfer to Raspberry Pi.

Never opens SSH, YouTube, or a network connection. Does not modify the video.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mac_pi_media_transfer import REMOTE_RE, TARGET_RE
from .pi_media_inbox import build_manifest


def precheck(video: str | Path, episode_id: str, ssh_target: str,
             remote_staging_dir: str) -> dict:
    if not TARGET_RE.fullmatch(ssh_target):
        raise ValueError("invalid SSH target; expected user@host")
    if (not REMOTE_RE.fullmatch(remote_staging_dir) or
            ".." in Path(remote_staging_dir).parts):
        raise ValueError("unsafe remote staging directory")
    manifest = build_manifest(video, episode_id)
    prefix = episode_id + "-" + manifest["sha256"][:16]
    manifest["filename"] = prefix + ".mp4"
    return {
        "status": "READY_FOR_TRANSFER_NOT_TRANSFERRED",
        "episode_id": episode_id,
        "size": manifest["size"],
        "sha256": manifest["sha256"],
        "remote_video_filename": manifest["filename"],
        "remote_manifest_filename": prefix + ".json",
        "offline_only": True,
        "network_checked": False,
        "pi_verified": False,
        "youtube_uploaded": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--remote-staging-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(precheck(args.video, args.episode_id,
                              args.ssh_target, args.remote_staging_dir),
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
