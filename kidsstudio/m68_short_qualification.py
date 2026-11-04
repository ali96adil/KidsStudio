"""M68 deterministic offline short qualification pipeline.

Plans and checks every short independently. Never transfers or uploads.
The caller supplies already rendered MP4 files; this command validates and
pins them to source QA without silently accepting missing media.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .m68_full_decode import verify_decoded
from .m68_short_handoff import build_short_handoff


class ShortQualificationError(RuntimeError):
    pass


def qualify(root, plan, videos, *, decoder=verify_decoded,
            handoff_builder=build_short_handoff):
    root = Path(root).resolve()
    shorts = plan.get("shorts")
    if not isinstance(shorts, list) or not shorts:
        raise ShortQualificationError("no shorts planned")
    ids = [s.get("short_id") for s in shorts]
    if len(ids) != len(set(ids)):
        raise ShortQualificationError("duplicate short ids")
    if set(videos) != set(ids):
        raise ShortQualificationError("one MP4 path required for each short")
    results = []
    for short in shorts:
        short_id = short["short_id"]
        if short.get("source_episode_id") != plan.get("episode_id"):
            raise ShortQualificationError("short belongs to another episode")
        if short.get("youtube_visibility") != "PRIVATE_ONLY":
            raise ShortQualificationError("short must remain private")
        path = Path(videos[short_id])
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ShortQualificationError("short MP4 must be inside trusted root")
        receipt = decoder(short, path)
        handoff = handoff_builder(root, short, path, receipt)
        results.append({"short_id": short_id, "decode": receipt,
                        "handoff": handoff, "content_qa": "PENDING"})
    return {"status": "SHORTS_DECODED_HASH_PINNED_AWAIT_CONTENT_QA",
            "episode_id": plan["episode_id"], "shorts": results,
            "pi_transfer_authorized": False,
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--video-map", type=Path, required=True,
                   help="JSON mapping short_id to local MP4 path")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("qualification output already exists")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    videos = json.loads(args.video_map.read_text(encoding="utf-8"))
    result = qualify(args.root, plan, videos)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["status"], "count": len(result["shorts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
