"""Read-only verification of one received Pi staging MP4 and its manifest.

No upload, queue write, credential access, or network connection.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pi_media_inbox import DIGEST_RE, EPISODE_RE, MAX_VIDEO_SIZE, file_digest


def verify_received(staging_dir: str | Path, manifest_name: str) -> dict:
    root = Path(staging_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("staging must be a real directory")
    if (Path(manifest_name).name != manifest_name or
            not manifest_name.endswith(".json") or
            manifest_name.startswith(".")):
        raise ValueError("unsafe manifest filename")
    metadata = root / manifest_name
    if metadata.is_symlink() or not metadata.is_file() or metadata.stat().st_size > 16384:
        raise ValueError("invalid manifest file")
    manifest = json.loads(metadata.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {
            "version", "episode_id", "size", "sha256", "filename"}:
        raise ValueError("invalid manifest schema")
    episode = manifest["episode_id"]
    digest = manifest["sha256"]
    size = manifest["size"]
    filename = manifest["filename"]
    if manifest["version"] != 1 or not isinstance(episode, str) or not EPISODE_RE.fullmatch(episode):
        raise ValueError("invalid episode")
    if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid sha256")
    if type(size) is not int or not 0 < size <= MAX_VIDEO_SIZE:
        raise ValueError("invalid video size")
    expected = episode + "-" + digest[:16]
    if filename != expected + ".mp4" or manifest_name != expected + ".json":
        raise ValueError("manifest/video names do not match digest")
    video = root / filename
    if video.is_symlink() or not video.is_file():
        raise ValueError("video missing or symlinked")
    if video.stat().st_size != size or file_digest(video) != digest:
        raise ValueError("received video failed SHA-256 or size verification")
    return {
        "status": "PI_MEDIA_VERIFIED_NOT_QUEUED",
        "episode_id": episode,
        "size": size,
        "sha256": digest,
        "network_checked": False,
        "youtube_uploaded": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-dir", type=Path, required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(verify_received(args.staging_dir, args.manifest), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
