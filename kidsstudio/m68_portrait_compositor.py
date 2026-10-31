"""M68 portrait art-direction presets using only source-approved artwork.

Use a source image as a full-height blurred background and a sharp centered
foreground panel. The source stays completely visible and narration is reused.
This is an optional visual enhancement; it does not grant any QA approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

from .m67_production_handoff import audit_assets, _safe_file, _sha
from .m68_shorts_render import ShortRenderError


def render_portrait(short, manifest, root, output, *, ffmpeg="ffmpeg",
                    runner=subprocess.run, timeout=1800):
    root = Path(root).resolve()
    output = Path(output)
    if not root.is_dir() or output.exists() or output.is_symlink():
        raise ShortRenderError("private source directory and new output required")
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ShortRenderError("existing safe output directory required")
    if not output.resolve().is_relative_to(root):
        raise ShortRenderError("output outside source root")
    if not audit_assets(manifest, root)["render_authorized"]:
        raise ShortRenderError("source media QA not passed")
    if short.get("source_episode_id") != manifest.get("episode_id"):
        raise ShortRenderError("episode mismatch")
    if short.get("youtube_visibility") != "PRIVATE_ONLY":
        raise ShortRenderError("private-only short required")
    if short.get("public_release_authorized") is not False:
        raise ShortRenderError("public release must be blocked")
    beats = short.get("source_beats")
    if not isinstance(beats, list) or len(beats) != 1 or type(beats[0]) is not int:
        raise ShortRenderError("one source beat required")
    index = beats[0]
    if index < 1 or index > len(manifest["assets"]):
        raise ShortRenderError("beat out of range")
    asset = manifest["assets"][index - 1]
    duration = asset["end"] - asset["start"]
    if not 4 <= duration <= 45:
        raise ShortRenderError("invalid duration")
    if (short.get("start_seconds"), short.get("end_seconds")) != (asset["start"], asset["end"]):
        raise ShortRenderError("source timing mismatch")
    if short.get("source_asset_keys") != [asset["art"], asset["voice"]]:
        raise ShortRenderError("source references mismatch")
    binary = shutil.which(ffmpeg)
    if not binary:
        raise ShortRenderError("ffmpeg not available")
    animation = asset.get("godot_animation")
    if animation is not None:
        source = _safe_file(root, animation)
        if asset.get("godot_animation_qa") != "PASS" or _sha(source) != asset.get("godot_animation_sha256"):
            raise ShortRenderError("animation digest mismatch")
        video_input = ["-i", str(source)]
    else:
        video_input = ["-loop", "1", "-framerate", "30", "-t", str(duration),
                       "-i", str(_safe_file(root, asset["art"]))]
    # Two independently scaled copies: ambient blurred fill + uncropped main art.
    filtergraph = (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,boxblur=35:3,eq=brightness=-0.12[ambient];"
        "[fg]scale=1000:1450:force_original_aspect_ratio=decrease,"
        "setsar=1[hero];"
        "[ambient][hero]overlay=(W-w)/2:(H-h)/2:shortest=1,"
        "fps=30,trim=duration=" + str(duration) + ",setpts=PTS-STARTPTS[v];"
        "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,"
        "apad,atrim=duration=" + str(duration) + ",asetpts=PTS-STARTPTS[a]"
    )
    command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
               *video_input, "-i", str(_safe_file(root, asset["voice"])),
               "-filter_complex", filtergraph, "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(output)]
    try:
        runner(command, check=True, capture_output=True, timeout=timeout)
        if not output.is_file() or output.stat().st_size == 0:
            raise ShortRenderError("no rendered MP4")
    except (OSError, subprocess.SubprocessError, ShortRenderError) as exc:
        output.unlink(missing_ok=True)
        raise ShortRenderError("portrait composition failed") from exc
    return {"status": "PORTRAIT_RENDERED_PENDING_QA",
            "short_id": short["short_id"], "output": str(output),
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
        p.error("episode mismatch")
    results = []
    for short in plan["shorts"]:
        results.append(render_portrait(short, manifest, args.root,
                                      args.output_dir / (short["short_id"] + ".mp4")))
    print(json.dumps({"status": "PORTRAIT_SHORTS_PENDING_QA", "results": results},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
