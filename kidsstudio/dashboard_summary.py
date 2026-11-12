"""Pure, read-only dashboard view model from a trusted queue snapshot.

No episode linkage or publication approval is inferred from queue counts.
"""
from __future__ import annotations

import argparse
import json

from .queue_dashboard import queue_dashboard_snapshot


def build_dashboard_summary(snapshot: dict) -> dict:
    if not isinstance(snapshot, dict) or snapshot.get("status") != "READ_ONLY_QUEUE_SNAPSHOT":
        raise ValueError("invalid queue snapshot")
    counts = snapshot.get("jobs_by_kind_and_state")
    if not isinstance(counts, dict):
        raise ValueError("missing counts")
    states = ("QUEUED", "LEASED", "COMPLETED", "FAILED", "CANCELLED")
    totals = {state: 0 for state in states}
    for kind_counts in counts.values():
        if not isinstance(kind_counts, dict) or set(kind_counts) != set(states):
            raise ValueError("invalid state counts")
        for state in states:
            value = kind_counts[state]
            if type(value) is not int or value < 0:
                raise ValueError("invalid count")
            totals[state] += value
    if snapshot.get("total_jobs") != sum(totals.values()):
        raise ValueError("inconsistent total")
    if type(snapshot.get("queue_paused")) is not bool:
        raise ValueError("invalid paused flag")
    return {
        "schema_version": 1,
        "status": "DASHBOARD_SUMMARY_READ_ONLY",
        "queue_paused": snapshot["queue_paused"],
        "total_jobs": snapshot["total_jobs"],
        "waiting": totals["QUEUED"],
        "running": totals["LEASED"],
        "completed": totals["COMPLETED"],
        "needs_attention": totals["FAILED"],
        "cancelled": totals["CANCELLED"],
        "episode_status_available": False,
        "private_upload_status_available": False,
        "publication_approved": False,
        "queue_mutated": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only dashboard summary")
    parser.add_argument("--db", required=True)
    args = parser.parse_args(argv)
    try:
        result = build_dashboard_summary(queue_dashboard_snapshot(args.db))
    except (ValueError, OSError, TypeError):
        print(json.dumps({"status": "DASHBOARD_UNAVAILABLE",
                          "queue_mutated": False, "publication_approved": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
