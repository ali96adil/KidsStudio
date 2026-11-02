"""Single-instance Pi staging-to-private-YouTube service.

Trusted metadata is provisioned locally; incoming manifests never
control video titles or channel selection. No public upload actions.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path

from .pi_staging_watcher import scan_once
from .pi_upload_queue import PiUploadQueue
from .pi_upload_queue_repair import recover_orphaned_sessions
from .pi_upload_token_provider import FileTokenProvider
from .pi_upload_worker import process_one
from .pi_youtube_release_check import load_credentials
from .youtube_upload_binding import UploadBindingStore


def read_titles(path: str | Path) -> dict[str, str]:
    source = Path(path)
    if source.is_symlink() or source.stat().st_size > 256 * 1024:
        raise ValueError("invalid title metadata file")
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and 0 < len(v.strip()) <= 100
        for k, v in data.items()
    ):
        raise ValueError("invalid trusted episode title mapping")
    return data


def pipeline_tick(*, queue, bindings, staging_dir, inbox_dir, session_dir,
                  token_provider, channel_id, titles) -> dict:
    # The worker is independent of the watcher: an incomplete staging
    # transfer cannot block already queued recovery jobs.
    watcher_error = False
    try:
        new_jobs = scan_once(
            staging_dir=staging_dir, inbox_dir=inbox_dir,
            session_dir=session_dir, queue=queue,
            token_provider=token_provider,
            expected_channel_id=channel_id,
            title_for_episode=lambda episode: titles.get(episode, ""),
        )
    except (OSError, ValueError):
        # Keep draining previously queued work even when staging is broken.
        new_jobs = []
        watcher_error = True
    completed = process_one(queue, bindings, token_provider)
    return {"queued": len(new_jobs), "processed": completed is not None,
            "watcher_error": watcher_error}


def run_pipeline(*, state_dir: str | Path, credentials: str | Path,
                 titles_file: str | Path, poll_seconds: float = 20.0,
                 once: bool = False) -> int:
    if not 1 <= poll_seconds <= 3600:
        raise ValueError("poll_seconds must be 1..3600")
    root = Path(state_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("state directory must be private (0700)")
    fd = os.open(root / "worker.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
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
        # Crash-safe recovery: a session can be persisted before its queue
        # INSERT. Restore only missing jobs, preserving existing job states.
        session_dir = root / "sessions"
        session_dir.mkdir(mode=0o700, exist_ok=True)
        if session_dir.is_symlink() or session_dir.stat().st_mode & 0o077:
            raise ValueError("session directory must be private")
        for directory in (root / "staging", root / "inbox"):
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or directory.stat().st_mode & 0o077:
                raise ValueError("media directory must be private")
        token_provider = FileTokenProvider(credentials)
        channel_id = load_credentials(Path(credentials))["channel_id"]
        recover_orphaned_sessions(queue, session_dir, channel_id)
        while True:
            tick_failed = False
            try:
                pipeline_tick(
                    queue=queue, bindings=bindings,
                    staging_dir=root / "staging",
                    inbox_dir=root / "inbox",
                    session_dir=root / "sessions",
                    token_provider=token_provider,
                    channel_id=channel_id,
                    titles=read_titles(titles_file),
                )
            except Exception:
                # Do not expose OAuth secrets or resumable session URLs.
                print("Pi pipeline tick failed; inspect private queue state", file=sys.stderr)
                tick_failed = True
            if once:
                return 2 if tick_failed else 0
            time.sleep(poll_seconds)
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kids Studio private Pi media pipeline")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--credentials", required=True)
    parser.add_argument("--titles-file", required=True)
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    return run_pipeline(
        state_dir=args.state_dir, credentials=args.credentials,
        titles_file=args.titles_file, poll_seconds=args.poll_seconds,
        once=args.once,
    )


if __name__ == "__main__":
    raise SystemExit(main())
