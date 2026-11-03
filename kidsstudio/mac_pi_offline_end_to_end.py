"""Local Mac -> Pi staging simulation. No SSH, network, queue, or YouTube."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from .mac_pi_transfer_precheck import precheck
from .mac_pi_integrity_compare import compare_reports
from .pi_received_media_precheck import verify_received


def run_offline_trial(video: str | Path, episode_id: str) -> dict:
    mac = precheck(video, episode_id, "pi@offline.local", "/home/pi/staging")
    with tempfile.TemporaryDirectory(prefix="kidsstudio-offline-pi-") as folder:
        staging = Path(folder)
        received = staging / mac["remote_video_filename"]
        shutil.copyfile(video, received)
        manifest = {
            "version": 1,
            "episode_id": mac["episode_id"],
            "size": mac["size"],
            "sha256": mac["sha256"],
            "filename": received.name,
        }
        metadata = staging / mac["remote_manifest_filename"]
        metadata.write_text(json.dumps(manifest), encoding="utf-8")
        pi = verify_received(staging, metadata.name)
        comparison = compare_reports(mac, pi)
    if not comparison["matching"]:
        raise ValueError("Mac and simulated Pi files do not match")
    return {
        "status": "OFFLINE_MAC_PI_TRIAL_PASSED",
        "episode_id": mac["episode_id"],
        "sha256": mac["sha256"],
        "size": mac["size"],
        "simulated_pi_only": True,
        "real_ssh_transfer_tested": False,
        "real_pi_tested": False,
        "youtube_uploaded": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--episode-id", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_offline_trial(args.video, args.episode_id), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
