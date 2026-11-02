"""Mac-side local media transfer over SSH/rsync with manifest verification."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .pi_media_inbox import build_manifest


def transfer_to_pi(
    video_path: str | Path,
    *,
    episode_id: str,
    ssh_target: str,
    remote_staging_dir: str,
    dry_run: bool = True,
) -> dict:
    """Transfer to a Pi-owned staging directory, never directly to YouTube.

    SSH target and remote directory are administrator-controlled settings,
    not user-submitted episode metadata.
    """
    manifest = build_manifest(video_path, episode_id)
    if not ssh_target or ssh_target.startswith("-") or any(c.isspace() for c in ssh_target):
        raise ValueError("invalid SSH target")
    if not remote_staging_dir.startswith("/") or any(c in remote_staging_dir for c in "\r\n\x00'\""):
        raise ValueError("invalid remote staging directory")
    remote_name = episode_id + "-" + manifest["sha256"][:16]
    if dry_run:
        return {"manifest": manifest, "remote_prefix": remote_name, "transferred": False}
    with tempfile.TemporaryDirectory() as folder:
        metadata = Path(folder) / (remote_name + ".json")
        metadata.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        # Avoid invoking a shell on the Mac. SSH/rsync still interpret the
        # remote destination; caller must use a trusted, fixed remote path.
        subprocess.run([
            "rsync", "-av", "--protect-args", "--",
            str(Path(video_path).resolve()),
            str(metadata),
            f"{ssh_target}:{remote_staging_dir.rstrip('/')}/",
        ], check=True, timeout=3600)
    return {"manifest": manifest, "remote_prefix": remote_name, "transferred": True}
