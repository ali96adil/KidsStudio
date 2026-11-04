"""M67 local-only six-beat audiovisual compositor.

Consumes real QA-pinned images and WAV files. Produces an MP4 using FFmpeg.
No model inference, Google connection, publishing, or automatic QA approval.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from .m67_production_handoff import audit_assets, _safe_file, ProductionHandoffError


class EpisodeComposeError(RuntimeError):
    pass


def compose(manifest: dict, root: Path, output: Path, *,
            ffmpeg: str = "ffmpeg", timeout: int = 1800) -> dict:
    root = Path(root).resolve()
    output = Path(output)
    if not root.is_dir() or root.is_symlink():
        raise EpisodeComposeError("private production directory required")
    if output.exists() or output.is_symlink():
        raise EpisodeComposeError("refuse to overwrite video")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise EpisodeComposeError("existing output directory required")
    if not output.resolve().is_relative_to(root):
        raise EpisodeComposeError("output must remain inside private production directory")
    result = audit_assets(manifest, root)
    if not result["render_authorized"]:
        raise EpisodeComposeError("assets missing, altered or not QA-approved")
    assets = manifest["assets"]
    if not 1 <= len(assets) <= 20:
        raise EpisodeComposeError("invalid number of scenes")
    executable = shutil.which(ffmpeg)
    if executable is None:
        raise EpisodeComposeError("local FFmpeg executable required")
    if not 30 <= timeout <= 7200:
        raise EpisodeComposeError("invalid timeout")
    # Each scene image is a static prop/background. This does NOT render
    # character rig animation. The full Godot layer can be integrated later.
    command = [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for item in assets:
        seconds = item["end"] - item["start"]
        if type(seconds) is not int or not 1 <= seconds <= 120:
            raise EpisodeComposeError("invalid scene duration")
        command += ["-loop", "1", "-framerate", "30", "-t", str(seconds),
                    "-i", str(_safe_file(root, item["art"]))]
        command += ["-i", str(_safe_file(root, item["voice"]))]
    filters = []
    for index, item in enumerate(assets):
        seconds = item["end"] - item["start"]
        filters.append(
            f"[{2*index}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"fps=30,trim=duration={seconds},setpts=PTS-STARTPTS[v{index}]"
        )
        filters.append(
            f"[{2*index+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"apad,atrim=duration={seconds},asetpts=PTS-STARTPTS[a{index}]"
        )
    joined = "".join(f"[v{i}][a{i}]" for i in range(len(assets)))
    filters.append(f"{joined}concat=n={len(assets)}:v=1:a=1[vout][aout]")
    command += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True,
                       timeout=timeout)
        if not output.is_file() or output.stat().st_size == 0:
            raise EpisodeComposeError("FFmpeg produced no video")
    except (OSError, subprocess.SubprocessError, EpisodeComposeError) as exc:
        if output.exists():
            output.unlink()
        raise EpisodeComposeError("local composition failed") from exc
    return {
        "status": "VIDEO_COMPOSED_PENDING_INDEPENDENT_QA",
        "output": str(output),
        "duration_seconds_planned": assets[-1]["end"],
        "render_qa": "PENDING",
        "pi_transfer_authorized": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.manifest.is_symlink() or not args.manifest.is_file():
            raise EpisodeComposeError("regular manifest required")
        report = compose(json.loads(args.manifest.read_text(encoding="utf-8")),
                         args.root, args.output)
        code = 0
    except (OSError, ValueError, EpisodeComposeError, ProductionHandoffError) as exc:
        report = {"status": "COMPOSE_BLOCKED", "reason": str(exc)}
        code = 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
