"""M67 episode asset safety audit for the Mac -> Pi handoff.

Generates a manifest of exact media hashes and blocks missing/changed files.
This is an offline inventory only; never transfers or uploads anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


class HandoffError(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inventory(root, *, master, episode_id):
    root = Path(root).resolve()
    master = Path(master).resolve()
    if not root.is_dir() or not master.is_file() or not master.is_relative_to(root):
        raise HandoffError("master must be inside existing episode directory")
    if master.is_symlink() or master.stat().st_size == 0:
        raise HandoffError("master must be nonempty regular file")
    if master.suffix.lower() != ".mp4":
        raise HandoffError("MP4 master required")
    relative = master.relative_to(root)
    if any((root / part).is_symlink() for part in relative.parts[:-1]):
        raise HandoffError("symlink directory in master path")
    return {"schema_version": 1, "episode_id": episode_id,
            "status": "MASTER_INVENTORIED_NOT_TRANSFERRED",
            "master": {"relative_path": relative.as_posix(),
                       "bytes": master.stat().st_size,
                       "sha256": sha256_file(master)},
            "pi_transfer_authorized": False,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def verify_inventory(root, manifest):
    root = Path(root).resolve()
    rel = manifest["master"]["relative_path"]
    if (not isinstance(rel, str) or not rel
            or Path(rel).is_absolute() or ".." in Path(rel).parts):
        raise HandoffError("invalid relative path")
    master = root / rel
    if master.is_symlink() or not master.is_file() or not master.resolve().is_relative_to(root):
        raise HandoffError("unsafe master path")
    if (master.stat().st_size != manifest["master"]["bytes"]
            or sha256_file(master) != manifest["master"]["sha256"]):
        raise HandoffError("master integrity mismatch")
    return {"status": "MASTER_HASH_VERIFIED",
            "episode_id": manifest["episode_id"],
            "sha256": manifest["master"]["sha256"],
            "youtube_upload_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--master", type=Path, required=True)
    p.add_argument("--episode-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("inventory already exists")
    result = inventory(args.root, master=args.master, episode_id=args.episode_id)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "sha256": result["master"]["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
