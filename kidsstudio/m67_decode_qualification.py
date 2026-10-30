"""Independent FFprobe qualification of M67 generated media.

Reads every actual PNG/WAV using FFmpeg's decoders, not just file headers.
Never grants visual, voice, educational or publication approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .m67_production_handoff import _safe_file, _sha


class MediaDecodeError(RuntimeError):
    pass


def decode_check(packet, root, *, ffmpeg="ffmpeg", ffprobe="ffprobe",
                 runner=subprocess.run):
    root = Path(root).resolve()
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise MediaDecodeError("FFmpeg and FFprobe are required")
    results = []
    for job in packet["jobs"]:
        entry = {"beat": job["beat"], "status": "DECODE_PENDING", "issues": []}
        for kind, expected_type in (("visual", "video"), ("voice", "audio")):
            try:
                file = _safe_file(root, job[kind]["output"])
                probe = runner([ffprobe, "-v", "error", "-show_streams",
                                "-of", "json", str(file)],
                               capture_output=True, text=True, check=True,
                               timeout=30)
                streams = json.loads(probe.stdout)["streams"]
                matching = [s for s in streams if s.get("codec_type") == expected_type]
                if len(matching) != 1:
                    raise MediaDecodeError("unexpected media streams")
                stream = matching[0]
                if kind == "visual":
                    if (stream.get("width"), stream.get("height")) != (1280, 720):
                        raise MediaDecodeError("image dimensions mismatch")
                else:
                    if int(stream.get("sample_rate", 0)) != 48000:
                        raise MediaDecodeError("voice sample rate mismatch")
                    if stream.get("codec_name") not in ("pcm_s16le", "pcm_s24le", "pcm_s32le"):
                        raise MediaDecodeError("uncompressed PCM WAV required")
                    if int(stream.get("channels", 0)) not in (1, 2):
                        raise MediaDecodeError("invalid voice channels")
                # Decode the full media stream and reject corruption that a
                # PNG header or WAV container inspection would miss.
                runner([ffmpeg, "-v", "error", "-xerror", "-i", str(file),
                        "-f", "null", "-"], capture_output=True,
                       check=True, timeout=90)
                entry[kind + "_sha256"] = _sha(file)
            except (OSError, ValueError, KeyError, subprocess.SubprocessError,
                    MediaDecodeError) as exc:
                entry["issues"].append({"asset": kind, "error": type(exc).__name__})
        entry["status"] = "DECODED_PENDING_QA" if not entry["issues"] else "BLOCKED"
        results.append(entry)
    return {
        "episode_id": packet["episode_id"],
        "status": ("MEDIA_DECODED_PENDING_QA"
                   if all(x["status"] == "DECODED_PENDING_QA" for x in results)
                   else "BLOCKED"),
        "results": results,
        "visual_qa": "PENDING", "voice_qa": "PENDING",
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--jobs", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        p.error("output exists")
    report = decode_check(json.loads(args.jobs.read_text(encoding="utf-8")),
                          args.root)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": report["status"], "beats": len(report["results"])}))
    return 0 if report["status"] == "MEDIA_DECODED_PENDING_QA" else 2


if __name__ == "__main__":
    raise SystemExit(main())
