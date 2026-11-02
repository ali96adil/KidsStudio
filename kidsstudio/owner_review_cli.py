"""CLI to record explicit owner review decisions without publishing."""
from __future__ import annotations

import argparse
import json
from .owner_video_reviews import append_review, latest_reviews, read_journal, STATES

def main() -> None:
    parser = argparse.ArgumentParser(description="Kids Studio offline owner reviews")
    parser.add_argument("--journal", required=True, help="Local review journal JSON path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="Show latest review state per episode")
    add = sub.add_parser("record", help="Record a new owner review decision")
    add.add_argument("--episode", required=True)
    add.add_argument("--state", choices=sorted(STATES), required=True)
    add.add_argument("--note", default="")
    args = parser.parse_args()
    if args.command == "record":
        result = append_review(args.journal, episode_id=args.episode,
                               state=args.state, note=args.note)
    else:
        result = latest_reviews(read_journal(args.journal))
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
