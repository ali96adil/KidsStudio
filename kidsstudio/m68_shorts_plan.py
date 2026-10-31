"""M68 derive vertical short edit decisions from an existing M67 storyboard.

No new media generation. Each selection preserves the source narration and
references the already-produced beat assets; the renderer must recompose 9:16.
This planning stage never authorizes YouTube upload or public release.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class ShortsPlanError(ValueError):
    pass


def derive(storyboard, *, max_shorts=3):
    beats = storyboard.get("beats")
    if not isinstance(beats, list) or not beats:
        raise ShortsPlanError("source storyboard beats required")
    if not isinstance(max_shorts, int) or isinstance(max_shorts, bool) or not 1 <= max_shorts <= 3:
        raise ShortsPlanError("max_shorts must be 1..3")
    episode_id = storyboard.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise ShortsPlanError("episode_id required")
    allowed = {"teach", "transfer", "recall", "reinforce"}
    candidates = []
    for index, beat in enumerate(beats, 1):
        if not isinstance(beat, dict):
            raise ShortsPlanError("invalid beat")
        start, end = beat.get("start"), beat.get("end")
        if (not isinstance(start, (int, float)) or isinstance(start, bool)
                or not isinstance(end, (int, float)) or isinstance(end, bool)
                or end <= start):
            raise ShortsPlanError("invalid beat timing")
        if beat.get("purpose") in allowed and 4 <= end - start <= 45:
            candidates.append((index, beat))
    shorts = []
    for index, beat in candidates[:max_shorts]:
        shorts.append({
            "short_id": f"{episode_id}-short-{len(shorts) + 1:02d}",
            "source_episode_id": episode_id,
            "source_beats": [index],
            "source_asset_keys": [f"art/beat_{index:02d}.png", f"voice/beat_{index:02d}.wav"],
            "start_seconds": beat["start"],
            "end_seconds": beat["end"],
            "narration": beat.get("narration", ""),
            "learning_purpose": beat["purpose"],
            "render": {"width": 1080, "height": 1920, "layout": "RECOMPOSE_SOURCE_ASSETS_NOT_CROP_MASTER"},
            "status": "SHORT_PLAN_PENDING_MEDIA_QA_AND_RENDER",
            "youtube_visibility": "PRIVATE_ONLY",
            "youtube_upload_authorized": False,
            "public_release_authorized": False,
        })
    return {"schema_version": 1, "episode_id": episode_id,
            "series_id": storyboard.get("series_id"),
            "status": "SHORTS_PLANNED_NOT_RENDERED" if shorts else "NO_SUITABLE_SHORTS",
            "shorts": shorts, "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--storyboard", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--max-shorts", type=int, default=3)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("output already exists")
    result = derive(json.loads(args.storyboard.read_text(encoding="utf-8")),
                    max_shorts=args.max_shorts)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "shorts": len(result["shorts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
