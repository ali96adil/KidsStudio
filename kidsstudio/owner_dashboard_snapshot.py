"""Read-only, bounded owner dashboard snapshot; no job dispatch or remote calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from .studio_queue import StudioQueue

def snapshot(database: str | Path, limit: int = 25) -> dict:
    """Expose only aggregate counts and minimal job metadata, never payloads."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    queue = StudioQueue(database)
    status = queue.status()
    jobs = queue.list_jobs(limit=limit)
    safe = []
    for job in jobs:
        safe.append({
            "job_id": job["job_id"],
            "kind": job["kind"],
            "state": job["state"],
            "attempts": job["attempts"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        })
    return {
        "schema_version": 1,
        "read_only": True,
        "paused": status["paused"],
        "counts": status["counts"],
        "recent_jobs": safe,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Local, read-only owner dashboard JSON")
    parser.add_argument("--db", required=True)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.db, args.limit), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
