"""Offline technical qualification of a prospective FilmCraft H.264/AAC export.

Reads the specified private file and runs ONLY an explicitly requested local
ffprobe with an argv list (never a shell). No FilmCraft automation, media
editing, network access, upload or publication permission.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from .optional_tool_evidence import ToolEvidenceError, private_evidence_file
from .transfer_verify import verify_staged_file

_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")
_ALLOWED_FPS = {Fraction(24, 1), Fraction(25, 1), Fraction(30, 1),
                Fraction(30000, 1001)}
_MAX_BYTES = 20 * 1024**3
_FFPROBE_OUTPUT_MAX = 128 * 1024


def _read_probe(path: Path, *, runner: Callable[..., Any]) -> dict:
    command = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=format_name,duration:"
        "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,"
        "sample_rate,channels",
        "-of", "json",
        str(path),
    ]
    try:
        completed = runner(
            command, capture_output=True, text=True, check=False, timeout=25)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ToolEvidenceError("Local media probe unavailable.") from exc
    stdout = getattr(completed, "stdout", None)
    if (getattr(completed, "returncode", None) != 0
            or not isinstance(stdout, str)
            or len(stdout.encode("utf-8")) > _FFPROBE_OUTPUT_MAX):
        raise ToolEvidenceError("Local media probe failed or produced oversized output.")
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise ToolEvidenceError("Invalid local ffprobe response.") from exc
    if not isinstance(data, dict):
        raise ToolEvidenceError("Local media probe was not an object.")
    return data


def _checks(probe: dict) -> dict[str, bool]:
    tracks = probe.get("streams")
    container = probe.get("format")
    if not isinstance(tracks, list) or len(tracks) > 32 or not isinstance(container, dict):
        raise ToolEvidenceError("Expected bounded video/audio streams and format.")
    videos = [t for t in tracks if isinstance(t, dict) and t.get("codec_type") == "video"]
    audios = [t for t in tracks if isinstance(t, dict) and t.get("codec_type") == "audio"]
    v = videos[0] if len(videos) == 1 else {}
    a = audios[0] if len(audios) == 1 else {}
    try:
        fps = Fraction(str(v.get("avg_frame_rate", "0/1")))
        duration = float(container.get("duration", -1))
        sample_rate = int(a.get("sample_rate", -1))
    except (ValueError, TypeError, ZeroDivisionError):
        fps = Fraction(0)
        duration = -1
        sample_rate = -1
    format_name = container.get("format_name")
    return {
        "container_mp4": isinstance(format_name, str) and "mp4" in format_name.split(","),
        "duration_valid": math.isfinite(duration) and 0.1 <= duration <= 600,
        "single_video_stream": len(videos) == 1,
        "video_h264": v.get("codec_name") == "h264",
        "video_1280x720": (
            type(v.get("width")) is int and type(v.get("height")) is int
            and (v["width"], v["height"]) == (1280, 720)),
        "video_yuv420p": v.get("pix_fmt") == "yuv420p",
        "video_allowed_fps": fps in _ALLOWED_FPS,
        "single_audio_stream": len(audios) == 1,
        "audio_aac": a.get("codec_name") == "aac",
        "audio_48000_hz": sample_rate == 48000,
        "audio_stereo": type(a.get("channels")) is int and a["channels"] == 2,
    }


def qualify_filmcraft_export(
    *, evidence_root: str, relative_path: str, expected_sha256: str,
    runner: Callable[..., Any] = subprocess.run,
) -> dict:
    if not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256):
        raise ToolEvidenceError("A trusted SHA-256 is required.")
    file = private_evidence_file(
        evidence_root, relative_path, max_bytes=_MAX_BYTES)
    first = verify_staged_file(
        root=evidence_root, relative_path=relative_path,
        expected_sha256=expected_sha256, max_bytes=_MAX_BYTES)
    if first["status"] != "VERIFIED":
        raise ToolEvidenceError("Export digest does not match supplied SHA.")
    if file.suffix.lower() != ".mp4":
        raise ToolEvidenceError("This initial check supports MP4 exports only.")
    probe = _read_probe(file, runner=runner)
    checks = _checks(probe)
    technical_profile = None
    if all(checks.values()):
        video = next(s for s in probe["streams"] if s["codec_type"] == "video")
        fps = Fraction(str(video["avg_frame_rate"]))
        technical_profile = {
            "duration_seconds": float(probe["format"]["duration"]),
            "fps_numerator": fps.numerator,
            "fps_denominator": fps.denominator,
            "width": 1280,
            "height": 720,
            "audio_sample_rate": 48000,
            "audio_channels": 2,
        }
    second = verify_staged_file(
        root=evidence_root, relative_path=relative_path,
        expected_sha256=expected_sha256, max_bytes=_MAX_BYTES)
    if second["status"] != "VERIFIED" or second["bytes"] != first["bytes"]:
        raise ToolEvidenceError("Export changed while media was being probed.")
    return {
        "schema_version": 1,
        "status": ("FILMCRAFT_EXPORT_TECHNICAL_PASS_UNREVIEWED"
                   if all(checks.values()) else "FILMCRAFT_EXPORT_TECHNICAL_BLOCKED"),
        "checks": checks,
        "file_sha256": first["sha256"],
        "file_bytes": first["bytes"],
        "technical_profile": technical_profile,
        "file_integrity_checked_at_report_time": True,
        "editor_origin_authenticated": False,
        "video_visual_quality_verified": False,
        "audio_listening_review_completed": False,
        "captions_arabic_review_completed": False,
        "real_filmcraft_install_tested": False,
        "file_mutated": False,
        "transfer_performed": False,
        "upload_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only local FFprobe check for optional FilmCraft exports")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        report = qualify_filmcraft_export(
            evidence_root=args.evidence_root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256)
    except (ToolEvidenceError, ValueError, OSError):
        print(json.dumps({"status": "FILMCRAFT_EXPORT_CHECK_ERROR",
                          "file_mutated": False, "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "FILMCRAFT_EXPORT_TECHNICAL_PASS_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
