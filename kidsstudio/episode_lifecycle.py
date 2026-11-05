"""Pure read-only episode lifecycle projection for an owner dashboard.

Accepts explicit verified events, never changes queue state or grants approvals.
"""
from __future__ import annotations

import argparse
import json
import re

_STATES = (
    "SCRIPT_PENDING", "SCRIPT_READY", "PRODUCTION_PENDING",
    "RENDER_READY", "PRIVATE_UPLOAD_PENDING", "PRIVATE_UPLOADED",
    "OWNER_REVIEW_PENDING", "REVISION_REQUIRED", "PUBLICATION_APPROVED",
)
_TRANSITIONS = {
    "SCRIPT_PENDING": {"SCRIPT_READY"},
    "SCRIPT_READY": {"PRODUCTION_PENDING"},
    "PRODUCTION_PENDING": {"RENDER_READY"},
    "RENDER_READY": {"PRIVATE_UPLOAD_PENDING"},
    "PRIVATE_UPLOAD_PENDING": {"PRIVATE_UPLOADED"},
    "PRIVATE_UPLOADED": {"OWNER_REVIEW_PENDING"},
    "OWNER_REVIEW_PENDING": {"REVISION_REQUIRED", "PUBLICATION_APPROVED"},
    "REVISION_REQUIRED": {"SCRIPT_READY", "PRODUCTION_PENDING"},
    "PUBLICATION_APPROVED": set(),
}
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def project_episode(*, episode_id: str, events: list[dict]) -> dict:
    if not isinstance(episode_id, str) or not _ID.fullmatch(episode_id):
        raise ValueError("invalid episode id")
    if not isinstance(events, list) or len(events) > 1000:
        raise ValueError("invalid event count")
    state = "SCRIPT_PENDING"
    for event in events:
        if not isinstance(event, dict) or event.get("episode_id") != episode_id:
            raise ValueError("invalid event episode")
        next_state = event.get("state")
        if next_state not in _TRANSITIONS[state]:
            raise ValueError("invalid lifecycle transition")
        if next_state == "PUBLICATION_APPROVED" and (
            event.get("actor") != "owner" or event.get("explicit_approval") is not True
        ):
            raise ValueError("owner approval required")
        state = next_state
    return {
        "schema_version": 1,
        "episode_id": episode_id,
        "state": state,
        "events_processed": len(events),
        "requires_owner_review": state in {
            "PRIVATE_UPLOADED", "OWNER_REVIEW_PENDING", "REVISION_REQUIRED"
        },
        "publication_approved_in_supplied_events": state == "PUBLICATION_APPROVED",
        "publication_performed": False,
        "queue_mutated": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only episode state projection")
    parser.add_argument("--episode-id", required=True)
    parser.add_argument("--events-json", required=True,
                        help="Local JSON file with trusted episode events")
    args = parser.parse_args(argv)
    try:
        from pathlib import Path
        file = Path(args.events_json)
        if file.stat().st_size > 512 * 1024:
            raise ValueError("events file too large")
        events = json.loads(file.read_text(encoding="utf-8"))
        report = project_episode(episode_id=args.episode_id, events=events)
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "INVALID_EVENTS",
                          "publication_performed": False, "queue_mutated": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
