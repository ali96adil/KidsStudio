"""Read-only, bounded owner dashboard snapshot; never expose job payloads."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from .studio_queue import StudioQueue

# Fixed allowlist: no payload, result_json, worker credentials or arbitrary error text.
JOB_FIELDS = ("job_id", "kind", "state", "attempts", "created_at", "updated_at")
ATTENTION_STATES = frozenset({"FAILED"})

def snapshot(database: str | Path, limit: int = 25) -> dict:
    """Expose aggregates and sanitized job metadata without mutating the queue."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    queue = StudioQueue(database)
    status = queue.status()
    jobs = queue.list_jobs(limit=limit)
    safe = [{field: job[field] for field in JOB_FIELDS} for job in jobs]
    by_kind = Counter(job["kind"] for job in jobs)
    by_state_and_kind = {}
    for job in jobs:
        by_state_and_kind.setdefault(job["kind"], Counter())[job["state"]] += 1
    attention = [job for job in safe if job["state"] in ATTENTION_STATES]
    return {
        "schema_version": 2,
        "read_only": True,
        "paused": status["paused"],
        "counts": status["counts"],
        "recent_jobs": safe,
        "recent_window": {
            "limit": limit,
            "returned": len(safe),
            "truncated": sum(status["counts"].values()) > len(safe),
            "by_kind": dict(sorted(by_kind.items())),
            "by_kind_and_state": {
                kind: dict(sorted(states.items()))
                for kind, states in sorted(by_state_and_kind.items())
            },
        },
        "attention": {
            "failed_in_recent_window": len(attention),
            "recent_failed_jobs": attention,
            "queue_paused": status["paused"],
        },
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Local, read-only owner dashboard JSON")
    parser.add_argument("--db", required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.db, args.limit), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
