"""M67 Godot animated overlay compositor.

An optional *real*, QA-pinned Godot animation replaces the static image
for a beat. The animation must match beat duration. Voice remains separately
pinned and checked. No publishing or transfer is performed.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from .m67_production_handoff import audit_assets, _safe_file, _sha
from .m67_episode_compositor import EpisodeComposeError


def compose_animated(manifest: dict, root: Path, output: Path, *,
                     ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
                     timeout: int = 1800) -> dict:
    root = Path(root).resolve()
    output = Path(output)
    if not root.is_dir() or root.is_symlink():
        raise EpisodeComposeError("private production directory required")
    if output.exists() or output.is_symlink():
        raise EpisodeComposeError("output already exists")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise EpisodeComposeError("existing output directory required")
    if not output.resolve().is_relative_to(root):
        raise EpisodeComposeError("output must remain in private production directory")
    if not audit_assets(manifest, root)["render_authorized"]:
        raise EpisodeComposeError("all base art/voice assets must pass QA")
    assets = manifest["assets"]
    if not 1 <= len(assets) <= 20:
        raise EpisodeComposeError("invalid beat count")
    ffmpeg_bin, ffprobe_bin = shutil.which(ffmpeg), shutil.which(ffprobe)
    if not ffmpeg_bin or not ffprobe_bin:
        raise EpisodeComposeError("local FFmpeg and FFprobe required")
    if not 30 <= timeout <= 7200:
        raise EpisodeComposeError("invalid timeout")
    cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for item in assets:
        seconds = item["end"] - item["start"]
        if type(seconds) is not int or not 1 <= seconds <= 120:
            raise EpisodeComposeError("invalid beat duration")
        animation = item.get("godot_animation")
        if animation is None:
            cmd += ["-loop", "1", "-framerate", "30", "-t", str(seconds),
                    "-i", str(_safe_file(root, item["art"]))]
        else:
            if item.get("godot_animation_qa") != "PASS":
                raise EpisodeComposeError("Godot animation QA not passed")
            file = _safe_file(root, animation)
            if item.get("godot_animation_sha256") != _sha(file):
                raise EpisodeComposeError("Godot animation digest mismatch")
            try:
                probe = subprocess.run(
                    [ffprobe_bin, "-v", "error", "-select_streams", "v:0",
                     "-show_entries", "format=duration:stream=width,height",
                     "-of", "json", str(file)],
                    check=True, capture_output=True, text=True, timeout=30)
                info = json.loads(probe.stdout)
                duration = float(info["format"]["duration"])
                streams = info.get("streams", [])
                if not streams or streams[0]["width"] < 320 or streams[0]["height"] < 180:
                    raise EpisodeComposeError("invalid animation dimensions")
                if abs(duration - seconds) > 0.15:
                    raise EpisodeComposeError("animation duration does not match beat")
            except (OSError, ValueError, KeyError, IndexError,
                    subprocess.SubprocessError) as exc:
                raise EpisodeComposeError("cannot validate animation metadata") from exc
            cmd += ["-i", str(file)]
        cmd += ["-i", str(_safe_file(root, item["voice"]))]
    filters = []
    for i, item in enumerate(assets):
        duration = item["end"] - item["start"]
        filters.append(
            f"[{2*i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"fps=30,trim=duration={duration},setpts=PTS-STARTPTS[v{i}]")
        filters.append(
            f"[{2*i+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"apad,atrim=duration={duration},asetpts=PTS-STARTPTS[a{i}]")
    filters.append(
        "".join(f"[v{i}][a{i}]" for i in range(len(assets))) +
        f"concat=n={len(assets)}:v=1:a=1[vout][aout]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[vout]",
            "-map", "[aout]", "-c:v", "libx264", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
        if not output.is_file() or output.stat().st_size == 0:
            raise EpisodeComposeError("missing encoded video")
    except (OSError, subprocess.SubprocessError, EpisodeComposeError) as exc:
        if output.exists():
            output.unlink()
        raise EpisodeComposeError("animated composition failed") from exc
    return {
        "status": "ANIMATED_VIDEO_PENDING_INDEPENDENT_QA",
        "output": str(output),
        "animated_beats": sum(item.get("godot_animation") is not None
                              for item in assets),
        "total_beats": len(assets),
        "render_qa": "PENDING",
        "pi_transfer_authorized": False,
        "youtube_upload_authorized": False,
        "public_release_authorized": False,
    }
