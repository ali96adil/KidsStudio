"""M67 offline macOS voice worker using installed say and ffmpeg.

Uses system voices only. Arabic voice must be selected explicitly; never
silently substitute an English voice. Output remains pending QA.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess


class VoiceBatchError(RuntimeError):
    pass


def render_voices(packet, root, *, voice, say="say", ffmpeg="ffmpeg",
                  runner=subprocess.run):
    root = Path(root).resolve()
    if not root.is_dir() or root.is_symlink():
        raise VoiceBatchError("existing episode root required")
    if not voice or not isinstance(voice, str) or voice.startswith("-"):
        raise VoiceBatchError("explicit macOS Arabic voice required")
    if shutil.which(say) is None or shutil.which(ffmpeg) is None:
        raise VoiceBatchError("macOS say and ffmpeg required")
    report_file = root / "voice_batch_report.json"
    if report_file.exists() or report_file.is_symlink():
        raise VoiceBatchError("report already exists")
    report = {"episode_id": packet["episode_id"], "status": "RUNNING",
              "voices": [], "voice_qa": "PENDING",
              "youtube_upload_authorized": False}
    def save():
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    save()
    for job in packet["jobs"]:
        beat = job["beat"]
        target = root / job["voice"]["output"]
        temp = target.with_suffix(".aiff")
        if target.exists() or target.is_symlink() or temp.exists() or temp.is_symlink():
            raise VoiceBatchError("existing output would be overwritten")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            runner([say, "-v", voice, "-o", str(temp), job["voice"]["text"]],
                   check=True, capture_output=True, timeout=120)
            runner([ffmpeg, "-nostdin", "-v", "error", "-n", "-i", str(temp),
                    "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
                    str(target)], check=True, capture_output=True, timeout=120)
            if not target.is_file() or target.stat().st_size == 0:
                raise VoiceBatchError("voice output missing")
            report["voices"].append({"beat": beat, "file": job["voice"]["output"],
                                     "status": "PENDING_QA"})
            save()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError, VoiceBatchError) as exc:
            report["status"] = "BLOCKED"
            report["failed_beat"] = beat
            report["error_type"] = type(exc).__name__
            save()
            raise VoiceBatchError(f"voice generation failed at beat {beat}") from exc
        finally:
            if temp.is_file() and not temp.is_symlink():
                temp.unlink()
    report["status"] = "VOICES_GENERATED_PENDING_QA"
    save()
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--voice", required=True)
    args = p.parse_args(argv)
    report = render_voices(
        json.loads(args.jobs.read_text(encoding="utf-8")),
        args.root, voice=args.voice)
    print(json.dumps({"status": report["status"],
                      "voices": len(report["voices"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
