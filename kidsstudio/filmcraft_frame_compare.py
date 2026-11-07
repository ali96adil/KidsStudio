"""Optional sampled frame comparison for two SHA-verified delivery MP4s.

Runs only local ffprobe/ffmpeg with fixed argv under explicit operator command.
Does not extract to disk, inspect audio, edit source files, or authorize release.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from PIL import Image, ImageChops, ImageStat, UnidentifiedImageError

from .filmcraft_baseline_compare import compare_filmcraft_baseline
from .optional_tool_evidence import ToolEvidenceError, private_evidence_file
from .transfer_verify import verify_staged_file

_FRAME_WIDTH = 320
_FRAME_HEIGHT = 180
_FRAME_MAX_BYTES = 8 * 1024 * 1024
_SAMPLE_FRACTIONS = (0.25, 0.50, 0.75)


def _frame_at(
    file: Path, second: float, *,
    runner: Callable[..., Any] = subprocess.run,
) -> Image.Image:
    # A low-resolution pipe capture avoids storing private content or screenshots.
    argv = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{second:.3f}",
        "-i", str(file),
        "-frames:v", "1",
        "-vf", f"scale={_FRAME_WIDTH}:{_FRAME_HEIGHT}:flags=bicubic",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    try:
        result = runner(argv, capture_output=True, check=False, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ToolEvidenceError("Local frame decoder failed.") from exc
    data = getattr(result, "stdout", None)
    if (getattr(result, "returncode", None) != 0
            or not isinstance(data, bytes)
            or not 16 <= len(data) <= _FRAME_MAX_BYTES):
        raise ToolEvidenceError("Frame decoder did not return bounded PNG data.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format != "PNG" or image.size != (_FRAME_WIDTH, _FRAME_HEIGHT):
                raise ToolEvidenceError("Frame decoder returned unexpected dimensions.")
            image.load()
            return image.convert("RGB")
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ToolEvidenceError("Frame decoder returned invalid image.") from exc


def compare_filmcraft_frames(
    *, evidence_root: str, baseline_relative_path: str,
    baseline_sha256: str, candidate_relative_path: str,
    candidate_sha256: str,
    probe_runner: Callable[..., Any] = subprocess.run,
    frame_runner: Callable[..., Any] = subprocess.run,
    mean_diff_limit: float = 0.06,
    changed_pixel_limit: float = 0.35,
    channel_threshold: int = 24,
) -> dict:
    for limit in (mean_diff_limit, changed_pixel_limit):
        if type(limit) not in (int, float) or not 0 <= limit <= 1:
            raise ToolEvidenceError("Frame difference limits must be 0..1.")
    if type(channel_threshold) is not int or not 0 <= channel_threshold <= 255:
        raise ToolEvidenceError("Channel threshold must be 0..255.")
    technical = compare_filmcraft_baseline(
        evidence_root=evidence_root,
        baseline_relative_path=baseline_relative_path,
        baseline_sha256=baseline_sha256,
        candidate_relative_path=candidate_relative_path,
        candidate_sha256=candidate_sha256,
        runner=probe_runner,
    )
    if technical["status"] != "FILMCRAFT_BASELINE_TECHNICALLY_COMPARABLE_UNREVIEWED":
        raise ToolEvidenceError("Technical comparison must pass before sampling frames.")
    baseline = private_evidence_file(
        evidence_root, baseline_relative_path, max_bytes=20 * 1024**3)
    candidate = private_evidence_file(
        evidence_root, candidate_relative_path, max_bytes=20 * 1024**3)
    samples = []
    for position in _SAMPLE_FRACTIONS:
        base_second = technical["baseline_duration_seconds"] * position
        candidate_second = technical["candidate_duration_seconds"] * position
        a = _frame_at(baseline, base_second, runner=frame_runner)
        b = _frame_at(candidate, candidate_second, runner=frame_runner)
        diff = ImageChops.difference(a, b)
        mean = sum(ImageStat.Stat(diff).mean) / (3 * 255)
        red, green, blue = diff.split()
        max_channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        changed = ImageStat.Stat(
            max_channel.point(lambda p: 255 if p > channel_threshold else 0)
        ).mean[0] / 255
        samples.append({
            "relative_position": position,
            "baseline_time_seconds": round(base_second, 3),
            "candidate_time_seconds": round(candidate_second, 3),
            "mean_rgb_absolute_difference": round(mean, 7),
            "changed_pixel_fraction": round(changed, 7),
            "within_limits": mean <= mean_diff_limit and changed <= changed_pixel_limit,
        })
    # Rehash both full media files after all external decoder invocations.
    for path, sha in ((baseline_relative_path, baseline_sha256),
                      (candidate_relative_path, candidate_sha256)):
        result = verify_staged_file(
            root=evidence_root, relative_path=path, expected_sha256=sha)
        if result["status"] != "VERIFIED":
            raise ToolEvidenceError("Media changed while frames were decoded.")
    return {
        "schema_version": 1,
        "status": (
            "FILMCRAFT_SAMPLED_FRAMES_WITHIN_LIMITS_UNREVIEWED"
            if all(item["within_limits"] for item in samples)
            else "FILMCRAFT_SAMPLED_FRAMES_DIFFER_REVIEW_REQUIRED"
        ),
        "samples": samples,
        "sample_width": _FRAME_WIDTH,
        "sample_height": _FRAME_HEIGHT,
        "mean_diff_limit": mean_diff_limit,
        "changed_pixel_limit": changed_pixel_limit,
        "baseline_sha256": technical["baseline_sha256"],
        "candidate_sha256": technical["candidate_sha256"],
        "technical_profile_comparable": True,
        "sampled_frames_decoded": len(samples) * 2,
        "entire_video_visually_verified": False,
        "original_episode_provenance_authenticated": False,
        "audio_quality_compared": False,
        "arabic_text_legibility_verified": False,
        "real_filmcraft_mac_run": "NOT_RUN",
        "media_files_modified": False,
        "upload_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Operator-requested local FilmCraft vs Godot sampled-frame comparison")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--baseline-relative-path", required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--candidate-relative-path", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        report = compare_filmcraft_frames(
            evidence_root=args.evidence_root,
            baseline_relative_path=args.baseline_relative_path,
            baseline_sha256=args.baseline_sha256,
            candidate_relative_path=args.candidate_relative_path,
            candidate_sha256=args.candidate_sha256,
        )
    except (ToolEvidenceError, ValueError, OSError, TypeError, KeyError, ZeroDivisionError):
        print(json.dumps({"status": "FILMCRAFT_FRAME_COMPARISON_ERROR",
                          "upload_approved": False, "publication_approved": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "FILMCRAFT_SAMPLED_FRAMES_WITHIN_LIMITS_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
