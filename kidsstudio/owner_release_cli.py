"""Owner-only release authorization CLI. Does not publish to YouTube."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .owner_release_gate import OwnerReleaseGate
from .owner_review_store import OwnerReviewStore
from .owner_video_reviews import _validate_id


def status(reviews: OwnerReviewStore, gate: OwnerReleaseGate, episode: str) -> dict:
    _validate_id(episode)
    current = reviews.latest().get(episode, {})
    state = current.get("state", "needs_review")
    decision = gate.latest(episode)
    return {
        "episode_id": episode,
        "review_state": state,
        "release_decision": decision,
        "eligible": gate.eligible(episode, state),
        "youtube_visibility_changed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Owner release decision (no YouTube writes)")
    parser.add_argument("--review-db", type=Path, required=True)
    parser.add_argument("--release-db", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("status")
    show.add_argument("--episode", required=True)
    decision = sub.add_parser("decide")
    decision.add_argument("--episode", required=True)
    decision.add_argument("--actor", required=True)
    decision.add_argument("--decision", choices=["hold", "release_authorized"], required=True)
    args = parser.parse_args()
    reviews = OwnerReviewStore(args.review_db)
    gate = OwnerReleaseGate(args.release_db)
    reviews.initialize()
    gate.initialize()
    if args.command == "decide":
        if args.decision == "release_authorized":
            current = reviews.latest().get(args.episode, {})
            if current.get("state") != "approved":
                parser.error("cannot authorize release without current approved review")
        gate.record(args.episode, args.decision, args.actor)
    print(json.dumps(status(reviews, gate, args.episode), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
