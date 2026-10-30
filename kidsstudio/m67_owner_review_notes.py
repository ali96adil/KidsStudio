"""M67 owner review notes for PRIVATE YouTube drafts.

This module stores an append-only local decision history. A review
decision is NOT a YouTube visibility change and never invokes APIs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import re


EPISODE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
VIDEO = re.compile(r"^[A-Za-z0-9_-]{11}$")
DECISIONS = {"ACCEPT_PRIVATE", "ACCEPT_WITH_NOTES", "REQUEST_CHANGES", "REJECT"}


class OwnerReviewError(ValueError):
    pass


def record(root, *, episode_id, video_id, decision, notes, reviewer="owner"):
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise OwnerReviewError("existing private episode root required")
    if not EPISODE.fullmatch(episode_id) or not VIDEO.fullmatch(video_id):
        raise OwnerReviewError("valid episode and YouTube video identifiers required")
    if decision not in DECISIONS or not isinstance(notes, str) or len(notes) > 10000:
        raise OwnerReviewError("invalid decision or notes")
    if decision in {"REQUEST_CHANGES", "REJECT", "ACCEPT_WITH_NOTES"} and not notes.strip():
        raise OwnerReviewError("review notes required for this decision")
    if reviewer != "owner":
        raise OwnerReviewError("owner review only")
    history = root / "owner_reviews"
    if history.is_symlink():
        raise OwnerReviewError("unsafe review folder")
    history.mkdir(mode=0o700, exist_ok=True)
    count = 1
    while (history / f"review_{count:04d}.json").exists():
        count += 1
        if count > 10000:
            raise OwnerReviewError("review history full")
    result = {
        "schema_version": 1, "episode_id": episode_id, "video_id": video_id,
        "decision": decision, "notes": notes.strip(), "reviewer": reviewer,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "youtube_visibility_changed": False,
        "public_release_authorized": False,
    }
    target = history / f"review_{count:04d}.json"
    with target.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write("\n")
    return {"status": "OWNER_REVIEW_RECORDED_NO_PUBLICATION",
            "review_file": str(target), **result}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--episode-id", required=True)
    p.add_argument("--video-id", required=True)
    p.add_argument("--decision", choices=sorted(DECISIONS), required=True)
    p.add_argument("--notes", default="")
    args = p.parse_args(argv)
    print(json.dumps(record(args.root, episode_id=args.episode_id,
                            video_id=args.video_id, decision=args.decision,
                            notes=args.notes), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
