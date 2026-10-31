"""M68 render a 9:16 short from already QA-pinned M67 beat media.

Reframes the complete original image/animation inside a portrait composition;
never crops the original educational content. No upload or publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .m67_production_handoff import audit_assets, _safe_file, _sha


class ShortRenderError(RuntimeError):
    pass


def render_short(short, manifest, root, output, *, ffmpeg="ffmpeg", timeout=1800,
                 runner=subprocess.run):
    root = Path(root).resolve()
    output = Path(output)
    if not root.is_dir() or root.is_symlink():
        raise ShortRenderError("existing private episode root required")
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ShortRenderError("output must be new in existing directory")
    if output.parent.is_symlink() or not output.resolve().is_relative_to(root):
        raise ShortRenderError("output outside episode root")
    if not audit_assets(manifest, root)["render_authorized"]:
        raise ShortRenderError("source assets not QA-pinned")
    if short.get("source_episode_id") != manifest.get("episode_id"):
        raise ShortRenderError("source episode mismatch")
    if short.get("youtube_visibility") != "PRIVATE_ONLY" or short.get("public_release_authorized") is not False:
        raise ShortRenderError("unsafe release policy")
    indices = short.get("source_beats")
    if not isinstance(indices, list) or len(indices) != 1 or type(indices[0]) is not int:
        raise ShortRenderError("exactly one source beat required")
    index = indices[0]
    assets = manifest["assets"]
    if index < 1 or index > len(assets):
        raise ShortRenderError("source beat out of range")
    asset = assets[index - 1]
    duration = asset["end"] - asset["start"]
    if type(duration) is not int or not 4 <= duration <= 45:
        raise ShortRenderError("short duration invalid")
    if short.get("start_seconds") != asset["start"] or short.get("end_seconds") != asset["end"]:
        raise ShortRenderError("source timing changed")
    if short.get("source_asset_keys") != [asset["art"], asset["voice"]]:
        raise ShortRenderError("source asset references changed")
    if short.get("render") != {"width": 1080, "height": 1920,
                                "layout": "RECOMPOSE_SOURCE_ASSETS_NOT_CROP_MASTER"}:
        raise ShortRenderError("unsupported render plan")
    binary = shutil.which(ffmpeg)
    if not binary:
        raise ShortRenderError("FFmpeg required")
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    animation = asset.get("godot_animation")
    if animation is None:
        command += ["-loop", "1", "-framerate", "30", "-t", str(duration),
                    "-i", str(_safe_file(root, asset["art"]))]
    else:
        source = _safe_file(root, animation)
        if asset.get("godot_animation_qa") != "PASS" or asset.get("godot_animation_sha256") != _sha(source):
            raise ShortRenderError("animation QA or hash mismatch")
        command += ["-i", str(source)]
    command += ["-i", str(_safe_file(root, asset["voice"]))]
    # Fit the complete landscape composition in a portrait frame.
    # The clean surrounding space is reserved for later safe title/layout work.
    video_filter = ("[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xF6F1E8,"
                    "setsar=1,fps=30,trim=duration=" + str(duration) +
                    ",setpts=PTS-STARTPTS[v]")
    audio_filter = ("[1:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                    "apad,atrim=duration=" + str(duration) + ",asetpts=PTS-STARTPTS[a]")
    command += ["-filter_complex", video_filter + ";" + audio_filter,
                "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                str(output)]
    try:
        runner(command, check=True, capture_output=True, timeout=timeout)
        if not output.is_file() or output.stat().st_size == 0:
            raise ShortRenderError("missing encoded short")
    except (OSError, subprocess.SubprocessError, ShortRenderError) as exc:
        if output.exists():
            output.unlink()
        raise ShortRenderError("short composition failed") from exc
    return {"status": "SHORT_RENDERED_PENDING_INDEPENDENT_QA",
            "short_id": short["short_id"], "output": str(output),
            "duration_seconds_planned": duration,
            "source_episode_id": manifest["episode_id"],
            "youtube_upload_authorized": False,
            "public_release_authorized": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plan", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if plan.get("episode_id") != manifest.get("episode_id"):
        p.error("plan and manifest episode mismatch")
    results = []
    for short in plan["shorts"]:
        target = args.output_dir / (short["short_id"] + ".mp4")
        results.append(render_short(short, manifest, args.root, target))
    print(json.dumps({"status": "SHORTS_RENDERED_PENDING_QA",
                      "results": results, "public_release_authorized": False},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
