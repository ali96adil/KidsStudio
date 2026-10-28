"""M7 offline technical episode QA. Performs *machine* checks only.

An ffprobe/ffmpeg PASS never proves educational accuracy, child suitability,
lip-sync quality, sound pleasantness or permission to publish.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

from .episode_assembly import digest, EpisodeAssemblyError, _ensure_private

CHECKS = (
    "media_sha256_matches", "h264_video", "aac_audio", "one_video_stream",
    "one_audio_stream", "resolution_1280x720", "frame_rate_24",
    "sample_rate_48000", "duration_bounded", "full_decode_success"
)


class TechnicalQAError(ValueError):
    pass


def _probe(path: Path, ffprobe: str) -> dict[str, Any]:
    try:
        child = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,codec_name,width,height,"
             "r_frame_rate,sample_rate", "-of", "json", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
            timeout=45,
        )
        return json.loads(child.stdout.decode("utf-8"))
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, ValueError) as exc:
        raise TechnicalQAError("ffprobe could not inspect media.") from exc


def _decode(path: Path, ffmpeg: str) -> bool:
    try:
        child = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "error", "-xerror", "-i", str(path),
             "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=1800, check=False,
        )
        return child.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def inspect_video(file: str | Path, expected_sha256: str, *,
                  ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg",
                  probe_fn: Callable[[Path, str], dict] = _probe,
                  decode_fn: Callable[[Path, str], bool] = _decode) -> dict:
    from re import fullmatch
    path = Path(file).expanduser().resolve()
    if not isinstance(expected_sha256, str) or not fullmatch(r"[a-f0-9]{64}",expected_sha256):
        raise TechnicalQAError("Exact expected queue-receipt SHA256 required.")
    if not path.is_file() or path.suffix.lower() != ".mp4" or not path.stat().st_size:
        raise TechnicalQAError("Local private MP4 must exist.")
    _ensure_private(path.parent)
    sha = digest(path)
    raw = probe_fn(path, ffprobe)
    if not isinstance(raw, dict):
        raise TechnicalQAError("Malformed ffprobe response.")
    streams = raw.get("streams", [])
    if not isinstance(streams,list):
        raise TechnicalQAError("Malformed ffprobe streams.")
    video=[r for r in streams if r.get("codec_type")=="video"]
    audio=[r for r in streams if r.get("codec_type")=="audio"]
    v=video[0] if video else {}
    a=audio[0] if audio else {}
    try:
        duration=float(raw.get("format",{}).get("duration","nan"))
    except (TypeError,ValueError):
        duration=float("nan")
    fps=v.get("r_frame_rate")=="24/1" or v.get("r_frame_rate")=="24"
    checks={
        "media_sha256_matches": sha==expected_sha256,
        "h264_video":v.get("codec_name")=="h264",
        "aac_audio":a.get("codec_name")=="aac",
        "one_video_stream":len(video)==1,
        "one_audio_stream":len(audio)==1,
        "resolution_1280x720":v.get("width")==1280 and v.get("height")==720,
        "frame_rate_24":fps,
        "sample_rate_48000":a.get("sample_rate")=="48000",
        "duration_bounded":2.0 <= duration <= 900.0,
        "full_decode_success":False,
    }
    # Do not decode an untrusted mismatched asset or an obviously invalid file.
    if all(checks[k] for k in CHECKS if k != "full_decode_success"):
        checks["full_decode_success"]=decode_fn(path,ffmpeg) is True
    passed=all(checks.values())
    return {
        "schema_version":1,
        "status":"TECH_PASS_OWNER_REVIEW_PENDING" if passed else "TECH_FAILED",
        "media_sha256":sha,
        "expected_media_sha256":expected_sha256,
        "file_bytes":path.stat().st_size,
        "duration_seconds":round(duration,3) if checks["duration_bounded"] else None,
        "checks":checks,
        "subjective_checks_performed":False,
        "rights_verified":False,
        "publishing_approved":False,
    }


def save_report(report: dict, destination: str | Path) -> str:
    target=Path(destination).expanduser().resolve()
    _ensure_private(target.parent)
    if target.suffix!=".json":
        raise TechnicalQAError("Report output must end in .json.")
    # Atomic exclusive create, never overwrite previous QA evidence.
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as out:
        json.dump(report,out,ensure_ascii=False,indent=2,allow_nan=False)
        out.write("\n")
        out.flush();os.fsync(out.fileno())
    return digest(target)


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(prog="studio-episode-qa",
        description="Local FFmpeg media integrity audit; does not approve episodes.")
    p.add_argument("--video",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--ffprobe",default="ffprobe")
    p.add_argument("--ffmpeg",default="ffmpeg")
    args=p.parse_args(argv)
    try:
        result=inspect_video(args.video,args.sha256,
                             ffprobe=args.ffprobe,ffmpeg=args.ffmpeg)
        result["report_sha256"]=save_report(result,args.report)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["status"]=="TECH_PASS_OWNER_REVIEW_PENDING" else 1
    except (TechnicalQAError,EpisodeAssemblyError,OSError,ValueError) as exc:
        print("STUDIO_EPISODE_QA_ERROR: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
