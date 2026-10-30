"""M67 Mac-to-Pi transfer using SSH/SCP and remote SHA256 verification.

Copies an MP4 to a temporary file on the Pi, verifies its SHA256 remotely,
then atomically renames it. No YouTube upload or public publication.
Requires an already configured SSH key and existing Pi incoming directory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from .m67_master_handoff import verify_inventory


class TransferError(RuntimeError):
    pass


_SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")


def transfer(root, manifest, *, host, user, remote_dir,
             runner=subprocess.run):
    if not _SAFE.fullmatch(host) or not _SAFE.fullmatch(user):
        raise TransferError("simple hostname and SSH username required")
    if not remote_dir.startswith("/") or not all(
            _SAFE.fullmatch(p) for p in remote_dir.split("/") if p):
        raise TransferError("remote directory must be an absolute safe path")
    verification = verify_inventory(root, manifest)
    digest = verification["sha256"]
    local = Path(root).resolve() / manifest["master"]["relative_path"]
    basename = f"{manifest['episode_id']}-{digest[:16]}.mp4"
    if not _SAFE.fullmatch(manifest["episode_id"]):
        raise TransferError("unsafe episode id")
    final = remote_dir.rstrip("/") + "/" + basename
    temporary = final + ".partial"
    target = f"{user}@{host}"
    ssh_opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                "-o", "StrictHostKeyChecking=yes"]
    def run(command, timeout=120):
        return runner(command, check=True, capture_output=True,
                      text=True, timeout=timeout)
    try:
        run(["ssh", *ssh_opts, target, "test", "-d", remote_dir])
        run(["ssh", *ssh_opts, target, "test", "!", "-e", final])
        run(["ssh", *ssh_opts, target, "test", "!", "-e", temporary])
        run(["scp", *ssh_opts, str(local), f"{target}:{temporary}"],
            timeout=7200)
        result = run(["ssh", *ssh_opts, target, "sha256sum", temporary])
        remote_digest = result.stdout.strip().split()[0]
        if remote_digest != digest:
            raise TransferError("remote SHA256 mismatch")
        run(["ssh", *ssh_opts, target, "mv", "-n", temporary, final])
        run(["ssh", *ssh_opts, target, "test", "-f", final])
    except (subprocess.SubprocessError, OSError) as exc:
        raise TransferError("SSH transfer failed; partial file may remain") from exc
    return {"status": "TRANSFERRED_TO_PI_HASH_VERIFIED",
            "episode_id": manifest["episode_id"],
            "remote_master": final, "sha256": digest,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--remote-dir", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("transfer report exists")
    manifest = json.loads(args.inventory.read_text(encoding="utf-8"))
    result = transfer(args.root, manifest, host=args.host, user=args.user,
                      remote_dir=args.remote_dir)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
