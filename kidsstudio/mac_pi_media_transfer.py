"""Mac-side SSH transfer with matching manifest and media filenames.

The manifest is transferred last, after rsync has completed the MP4.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .pi_media_inbox import build_manifest

TARGET_RE = re.compile(r"[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+")
REMOTE_RE = re.compile(r"/[A-Za-z0-9_./-]+")


def transfer_to_pi(
    video_path: str | Path,
    *,
    episode_id: str,
    ssh_target: str,
    remote_staging_dir: str,
    dry_run: bool = True,
) -> dict:
    """Transfer MP4 first, then publish its matching manifest via SSH."""
    manifest = build_manifest(video_path, episode_id)
    if not TARGET_RE.fullmatch(ssh_target):
        raise ValueError("expected user@host SSH target")
    if not REMOTE_RE.fullmatch(remote_staging_dir) or ".." in Path(remote_staging_dir).parts:
        raise ValueError("unsafe remote staging path")
    prefix = episode_id + "-" + manifest["sha256"][:16]
    remote_video = prefix + ".mp4"
    manifest["filename"] = remote_video
    if dry_run:
        return {"manifest": manifest, "remote_prefix": prefix, "transferred": False}
    with tempfile.TemporaryDirectory() as folder:
        staged = Path(folder)
        video_copy = staged / remote_video
        metadata = staged / (prefix + ".json")
        # Copy into a stable local snapshot, so both files describe exactly
        # the bytes rsync transfers even if the original render changes.
        shutil.copyfile(video_path, video_copy)
        from .pi_media_inbox import file_digest
        if video_copy.stat().st_size != manifest["size"] or file_digest(video_copy) != manifest["sha256"]:
            raise ValueError("source video changed during transfer preparation")
        metadata.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        destination = f"{ssh_target}:{remote_staging_dir.rstrip('/')}/"
        subprocess.run(["rsync", "-av", "--protect-args", "--",
                        str(video_copy), destination], check=True, timeout=3600)
        # Publish the manifest only after the full temporary file arrives.
        # The Pi watcher ignores dot-prefixed files until the atomic rename.
        remote_tmp = "." + metadata.name + ".incoming"
        subprocess.run(["rsync", "-av", "--protect-args", "--",
                        str(metadata), destination + remote_tmp], check=True, timeout=120)
        subprocess.run(["ssh", "--", ssh_target,
                        "mv -- " + remote_staging_dir.rstrip("/") + "/" + remote_tmp +
                        " " + remote_staging_dir.rstrip("/") + "/" + metadata.name],
                       check=True, timeout=30)
    return {"manifest": manifest, "remote_prefix": prefix, "transferred": True}
