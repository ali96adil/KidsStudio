"""M67 resumable Mac-to-Pi transfer with remote hash reconciliation.

A verified final file is idempotent. An unverified final file blocks.
A stale .partial is never deleted automatically; operator must inspect it.
No upload or publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from .m67_master_handoff import verify_inventory


SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ResumeError(RuntimeError):
    pass


def _digest(text):
    match = re.match(r"^([0-9a-f]{64})(?:\s|$)", text.strip())
    if not match:
        raise ResumeError("invalid remote sha256sum response")
    return match.group(1)


def transfer_resumable(root, manifest, *, host, user, remote_dir,
                       runner=subprocess.run):
    if not all(isinstance(x, str) and SAFE.fullmatch(x) for x in (host, user)):
        raise ResumeError("unsafe SSH endpoint")
    if (not isinstance(remote_dir, str) or not remote_dir.startswith("/")
            or any(not part or part in (".", "..") or not SAFE.fullmatch(part)
                   for part in remote_dir[1:].split("/"))):
        raise ResumeError("unsafe remote directory")
    verified = verify_inventory(root, manifest)
    episode = manifest["episode_id"]
    if not isinstance(episode, str) or not SAFE.fullmatch(episode):
        raise ResumeError("unsafe episode id")
    digest = verified["sha256"]
    local = Path(root).resolve() / manifest["master"]["relative_path"]
    final = remote_dir + "/" + episode + "-" + digest[:16] + ".mp4"
    partial = final + ".partial"
    target = user + "@" + host
    options = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
               "-o", "ConnectTimeout=10"]

    def ssh(*args):
        return runner(["ssh", *options, target, *args], check=False,
                      capture_output=True, text=True, timeout=120)

    directory = ssh("test", "-d", remote_dir)
    if directory.returncode != 0:
        raise ResumeError("remote inbox directory missing")
    existing = ssh("test", "-f", final)
    if existing.returncode == 0:
        check = ssh("sha256sum", final)
        if check.returncode or _digest(check.stdout) != digest:
            raise ResumeError("existing final file differs; manual reconciliation")
        return {"status": "ALREADY_TRANSFERRED_HASH_VERIFIED",
                "remote_master": final, "sha256": digest,
                "youtube_uploaded": False, "public_release_authorized": False}
    if existing.returncode != 1:
        raise ResumeError("unable to inspect remote final file")
    staged = ssh("test", "-e", partial)
    if staged.returncode == 0:
        raise ResumeError("existing partial requires manual reconciliation")
    if staged.returncode != 1:
        raise ResumeError("unable to inspect remote partial file")
    try:
        runner(["scp", *options, str(local), target + ":" + partial],
               check=True, capture_output=True, text=True, timeout=7200)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ResumeError("copy interrupted; remote partial retained") from exc
    result = ssh("sha256sum", partial)
    if result.returncode or _digest(result.stdout) != digest:
        raise ResumeError("partial SHA mismatch; manual reconciliation")
    moved = ssh("mv", "-n", partial, final)
    if moved.returncode:
        raise ResumeError("remote rename failed")
    check = ssh("sha256sum", final)
    if check.returncode or _digest(check.stdout) != digest:
        raise ResumeError("final SHA mismatch")
    return {"status": "TRANSFERRED_TO_PI_HASH_VERIFIED",
            "remote_master": final, "sha256": digest,
            "youtube_uploaded": False, "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--remote-dir", required=True)
    args = p.parse_args(argv)
    report = transfer_resumable(
        args.root, json.loads(args.inventory.read_text(encoding="utf-8")),
        host=args.host, user=args.user, remote_dir=args.remote_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
