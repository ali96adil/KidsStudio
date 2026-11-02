"""Systemd-friendly, single-instance private upload queue service."""
from __future__ import annotations

import argparse
import fcntl
import os
import sys
import time
from pathlib import Path

from .pi_upload_queue import PiUploadQueue
from .pi_upload_worker import process_one
from .pi_upload_token_provider import FileTokenProvider
from .youtube_upload_binding import UploadBindingStore


def run_service(*, state_dir: str | Path, credential_path: str | Path, poll_seconds: float = 20.0, once: bool = False) -> int:
    if not 1 <= poll_seconds <= 3600:
        raise ValueError("poll_seconds must be 1..3600")
    root = Path(state_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("state directory must be private")
    lock_path = root / "worker.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 2
        queue = PiUploadQueue(root / "queue.sqlite")
        queue.initialize()
        bindings = UploadBindingStore(root / "bindings.sqlite")
        bindings.initialize()
        queue.recover_interrupted()
        token_provider = FileTokenProvider(credential_path)
        while True:
            try:
                process_one(queue, bindings, token_provider)
            except Exception:
                # Never print session URLs, access tokens or OAuth exceptions.
                print("upload job failed; inspect queue state", file=sys.stderr)
            if once:
                return 0
            time.sleep(poll_seconds)
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kids Studio private Pi upload recovery service")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    return run_service(
        state_dir=args.state_dir,
        credential_path=args.credentials,
        poll_seconds=args.poll_seconds,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
