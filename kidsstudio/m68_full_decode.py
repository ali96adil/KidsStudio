"""M68 full MP4 decode gate, independent of metadata checks."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .m68_shorts_verify import verify_short, ShortVerifyError


def verify_decoded(short, video, *, ffmpeg="ffmpeg", runner=subprocess.run):
    report = verify_short(short, video)
    binary = shutil.which(ffmpeg)
    if not binary:
        raise ShortVerifyError("FFmpeg required for complete decode")
    command = [binary, "-hide_banner", "-v", "error", "-xerror",
               "-nostdin", "-i", str(video), "-map", "0:v:0",
               "-map", "0:a:0", "-f", "null", "-"]
    try:
        runner(command, check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ShortVerifyError("complete video and audio decode failed") from exc
    report["status"] = "SHORT_FULLY_DECODED_PENDING_CONTENT_QA"
    report["full_decode"] = "PASS"
    report["youtube_upload_authorized"] = False
    report["public_release_authorized"] = False
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--short-id", required=True)
    p.add_argument("--video", type=Path, required=True)
    args = p.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    matching = [s for s in plan["shorts"] if s["short_id"] == args.short_id]
    if len(matching) != 1:
        p.error("short id must match exactly once")
    print(json.dumps(verify_decoded(matching[0], args.video),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
