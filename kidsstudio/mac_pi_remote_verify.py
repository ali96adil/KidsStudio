"""Read-only verification over SSH after Mac-to-Pi transfer.

Requires KidsStudio Python package on Pi. Does not upload or queue media.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .mac_pi_media_transfer import REMOTE_RE, TARGET_RE
from .pi_media_inbox import build_manifest


def verify_remote(video_path: str | Path, *, episode_id: str,
                  ssh_target: str, remote_staging_dir: str) -> dict:
    if not TARGET_RE.fullmatch(ssh_target):
        raise ValueError("expected user@host SSH target")
    if not REMOTE_RE.fullmatch(remote_staging_dir) or ".." in Path(remote_staging_dir).parts:
        raise ValueError("unsafe remote staging path")
    local = build_manifest(video_path, episode_id)
    manifest_name = episode_id + "-" + local["sha256"][:16] + ".json"
    # Inputs are restricted to shell-safe characters by the validators above.
    remote_command = (
        "python3 -m kidsstudio.pi_received_media_precheck"
        " --staging-dir " + remote_staging_dir +
        " --manifest " + manifest_name
    )
    completed = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "--", ssh_target, remote_command],
        check=True, capture_output=True, text=True, timeout=3600,
    )
    try:
        pi = json.loads(completed.stdout)
    except (ValueError, TypeError) as exc:
        raise ValueError("Pi did not return a valid JSON verification report") from exc
    if not isinstance(pi, dict) or pi.get("status") != "PI_MEDIA_VERIFIED_NOT_QUEUED":
        raise ValueError("unexpected Pi verification status")
    if (pi.get("episode_id"), pi.get("size"), pi.get("sha256")) != (
            local["episode_id"], local["size"], local["sha256"]):
        raise ValueError("Mac and Pi media digest/size mismatch")
    if pi.get("youtube_uploaded") is not False or pi.get("public_release_authorized") is not False:
        raise ValueError("unsafe Pi verification flags")
    return {
        "status": "REMOTE_MAC_PI_INTEGRITY_VERIFIED",
        "episode_id": episode_id,
        "size": local["size"],
        "sha256": local["sha256"],
        "ssh_verification_performed": True,
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
    args = parser.parse_args(argv)
    result = verify_remote(args.video, episode_id=args.episode_id,
                           ssh_target=args.ssh_target,
                           remote_staging_dir=args.remote_staging_dir)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
