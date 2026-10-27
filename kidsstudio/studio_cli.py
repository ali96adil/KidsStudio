"""Local Studio Director queue-control utility; never executes queued jobs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .studio_queue import QueueError, StudioQueue, KINDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="studioctl", description="KidsStudio local Pi queue and audit log"
    )
    parser.add_argument("--db", type=Path, required=True,
                        help="Absolute/local SQLite path OUTSIDE the Git repository")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("init", help="Initialize new local SQLite queue; no overwrite")
    add = sub.add_parser("enqueue", help="Record one idempotent production request")
    add.add_argument("--kind", required=True, choices=sorted(KINDS))
    add.add_argument("--key", required=True, help="Unique stable request id")
    add.add_argument("--payload-file", type=Path, required=True)
    add.add_argument("--max-attempts", type=int, default=2)
    sub.add_parser("status", help="Summarize pending/leased/completed jobs")
    listing = sub.add_parser("list", help="Show the most recent jobs")
    listing.add_argument("--limit", type=int, default=25)
    detail = sub.add_parser("get", help="Show a single job")
    detail.add_argument("job_id")
    log = sub.add_parser("events", help="Inspect audit trail")
    log.add_argument("--job-id")
    log.add_argument("--limit", type=int, default=100)
    sub.add_parser("pause", help="Stop new claims (already leased jobs continue)")
    sub.add_parser("resume", help="Re-enable new job claims")
    cancel = sub.add_parser("cancel", help="Cancel a pending/leased job")
    cancel.add_argument("job_id")
    args = parser.parse_args(argv)

    try:
        queue = StudioQueue(args.db)
        if args.operation == "init":
            queue.initialize()
            result = {"status": "INITIALIZED", "db": str(queue.path)}
        elif args.operation == "enqueue":
            payload = json.loads(args.payload_file.read_text(encoding="utf-8"))
            row = queue.enqueue(
                kind=args.kind, request_key=args.key, payload=payload,
                max_attempts=args.max_attempts,
            )
            result = {"job_id": row["job_id"], "request_key": row["request_key"],
                      "state": row["state"], "kind": row["kind"]}
        elif args.operation == "status":
            result = queue.status()
        elif args.operation == "list":
            result = [
                {"job_id": row["job_id"], "request_key": row["request_key"],
                 "kind": row["kind"], "state": row["state"],
                 "attempts": row["attempts"], "max_attempts": row["max_attempts"]}
                for row in queue.list_jobs(limit=args.limit)
            ]
        elif args.operation == "get":
            result = queue.get(args.job_id)
        elif args.operation == "events":
            result = queue.events(args.job_id, limit=args.limit)
        elif args.operation == "pause":
            result = {"paused": queue.set_paused(True)}
        elif args.operation == "resume":
            result = {"paused": queue.set_paused(False)}
        else:
            row = queue.cancel(args.job_id)
            result = {"job_id": row["job_id"], "state": row["state"]}
    except (QueueError, FileExistsError, OSError, ValueError,
            json.JSONDecodeError) as exc:
        print("STUDIOCTL_ERROR: " + str(exc), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
