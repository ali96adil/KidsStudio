"""M68 verify a rendered short with FFprobe before any Pi handoff.

Checks actual stream dimensions, audio presence and planned duration.
Read-only verification: does not authorize upload or publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .m67_master_handoff import sha256_file


class ShortVerifyError(RuntimeError):
    pass


def verify_short(short, video, *, ffprobe="ffprobe", runner=subprocess.run):
    video = Path(video)
    if video.is_symlink() or not video.is_file() or video.stat().st_size == 0:
        raise ShortVerifyError("regular nonempty MP4 required")
    if video.suffix.lower() != ".mp4":
        raise ShortVerifyError("MP4 required")
    executable = shutil.which(ffprobe)
    if executable is None:
        raise ShortVerifyError("FFprobe required")
    command = [executable, "-v", "error", "-show_entries",
               "format=duration:stream=codec_type,width,height",
               "-of", "json", str(video)]
    try:
        result = runner(command, check=True, capture_output=True, text=True, timeout=45)
        info = json.loads(result.stdout)
        streams = info["streams"]
        videos = [s for s in streams if s.get("codec_type") == "video"]
        audios = [s for s in streams if s.get("codec_type") == "audio"]
        duration = float(info["format"]["duration"])
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        raise ShortVerifyError("unable to inspect encoded short") from exc
    expected = short["end_seconds"] - short["start_seconds"]
    if len(videos) != 1 or not audios:
        raise ShortVerifyError("one video and an audio stream required")
    if videos[0].get("width") != 1080 or videos[0].get("height") != 1920:
        raise ShortVerifyError("wrong portrait resolution")
    if not 4 <= duration <= 45.5 or abs(duration - expected) > 0.5:
        raise ShortVerifyError("encoded duration mismatch")
    return {"status": "SHORT_MEDIA_TECHNICALLY_VERIFIED_PENDING_CONTENT_QA",
            "short_id": short["short_id"], "source_episode_id": short["source_episode_id"],
            "video_sha256": sha256_file(video), "bytes": video.stat().st_size,
            "duration_seconds": duration, "width": 1080, "height": 1920,
            "youtube_upload_authorized": False, "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--short-id", required=True)
    p.add_argument("--video", type=Path, required=True)
    args = p.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    matches = [s for s in plan["shorts"] if s["short_id"] == args.short_id]
    if len(matches) != 1:
        p.error("short id must uniquely match plan")
    result = verify_short(matches[0], args.video)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
