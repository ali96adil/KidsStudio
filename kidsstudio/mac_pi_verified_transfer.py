"""Opt-in one-command Mac-to-Pi transfer followed by remote integrity verification.

Does not queue, upload to YouTube, or publish videos. Defaults to dry-run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mac_pi_media_transfer import transfer_to_pi
from .mac_pi_remote_verify import verify_remote


def transfer_and_verify(video_path: str | Path, *, episode_id: str,
                        ssh_target: str, remote_staging_dir: str,
                        execute: bool = False) -> dict:
    transfer = transfer_to_pi(video_path, episode_id=episode_id,
                              ssh_target=ssh_target,
                              remote_staging_dir=remote_staging_dir,
                              dry_run=not execute)
    if not execute:
        return {
            "status": "MAC_PI_TRANSFER_DRY_RUN",
            "episode_id": transfer["manifest"]["episode_id"],
            "size": transfer["manifest"]["size"],
            "sha256": transfer["manifest"]["sha256"],
            "transferred": False,
            "pi_verified": False,
            "youtube_uploaded": False,
            "public_release_authorized": False,
        }
    if transfer.get("transferred") is not True:
        raise RuntimeError("transfer did not complete")
    verification = verify_remote(video_path, episode_id=episode_id,
                                 ssh_target=ssh_target,
                                 remote_staging_dir=remote_staging_dir)
    if (verification["size"] != transfer["manifest"]["size"] or
            verification["sha256"] != transfer["manifest"]["sha256"]):
        raise ValueError("source media changed between transfer and remote verification")
    return {
        **verification,
        "status": "MAC_PI_TRANSFER_AND_REMOTE_VERIFY_PASSED",
        "transferred": True,
        "pi_verified": True,
        "youtube_uploaded": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--ssh-target", required=True)
    parser.add_argument("--remote-staging-dir", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="Actually transfer over SSH and verify on Pi")
    args = parser.parse_args(argv)
    print(json.dumps(transfer_and_verify(
        args.video, episode_id=args.episode_id,
        ssh_target=args.ssh_target, remote_staging_dir=args.remote_staging_dir,
        execute=args.execute), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
