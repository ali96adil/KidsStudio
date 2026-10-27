"""CI end-to-end Godot 4.7.2 + FFmpeg smoke with generated synthetic layers.

This intentionally uses NO children's media, proprietary character art, online
model inference, ComfyUI or vision-model credentials. Real Godot executes the
checked-in rig player and must produce a real MP4 (not mock subprocesses).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw

from kidsstudio.godot_export import export_godot
from kidsstudio.godot_render import render_godot_project


def _layer(name: str, canvas: tuple[int, int]) -> Image.Image:
    art = Image.new("RGBA", canvas)
    pen = ImageDraw.Draw(art)
    shapes: dict[str, tuple[str, tuple[int, int, int, int], tuple[int, int, int, int]]] = {
        "body": ("ellipse", (35, 50, 91, 107), (242, 190, 163, 255)),
        "head": ("ellipse", (30, 24, 99, 71), (244, 195, 170, 255)),
        "arm_left": ("ellipse", (17, 56, 43, 95), (228, 155, 145, 255)),
        "arm_right": ("ellipse", (87, 54, 113, 97), (230, 162, 150, 255)),
        "leg_left": ("ellipse", (42, 97, 59, 125), (239, 176, 170, 255)),
        "leg_right": ("ellipse", (66, 98, 83, 125), (240, 178, 172, 255)),
        "ear_left": ("ellipse", (38, 4, 52, 36), (240, 176, 160, 255)),
        "ear_right": ("ellipse", (76, 5, 90, 37), (241, 177, 161, 255)),
        "eyes": ("ellipse", (49, 41, 56, 48), (25, 20, 24, 255)),
        "mouth": ("ellipse", (62, 54, 68, 60), (103, 45, 51, 255)),
    }
    _, bounds, fill = shapes[name]
    pen.ellipse(bounds, fill=fill)
    return art


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/ci_godot_smoke.py /tmp/safe-test-root")
    base = Path(sys.argv[1]).expanduser().resolve()
    if base.exists():
        raise FileExistsError("Smoke root must not exist to protect earlier render.")
    (base / "source" / "assets").mkdir(parents=True)
    width, height = 128, 128
    pivots: dict[str, list[int]] = {
        "body": [64, 65], "head": [64, 65],
        "arm_left": [39, 59], "arm_right": [91, 57],
        "leg_left": [51, 100], "leg_right": [73, 100],
        "ear_left": [46, 31], "ear_right": [83, 32],
        "eyes": [53, 43], "mouth": [65, 57],
    }
    names = list(pivots)
    for part_id in names:
        _layer(part_id, (width, height)).save(
            base / "source" / "assets" / (part_id + ".png")
        )
    manifest = {
        "schema_version": 1,
        "character_id": "ci_synthetic_bunny",
        "canvas": {"width": width, "height": height},
        "parts": [
            {
                "id": name, "file": "assets/" + name + ".png",
                "pivot": pivots[name], "z": i,
            }
            for i, name in enumerate(names)
        ],
    }
    rig_file = base / "source" / "rig.json"
    rig_file.write_text(json.dumps(manifest), encoding="utf-8")
    # Generate only 3 frames to minimize public-CI GPU/CPU cost, while
    # executing GDScript, textures, timeline and video encoding end-to-end.
    spec = {
        "schema_version": 1,
        "fps": 30,
        "duration_seconds": 0.1,
        "beats": [{"start": 0, "end": 0.1, "motion": "wave_right"}],
    }
    scene_file = base / "source" / "scene.json"
    scene_file.write_text(json.dumps(spec), encoding="utf-8")
    project = base / "godot_project"
    exported = export_godot(rig_file, scene_file, project)
    assert exported["status"] == "PREVIEW_ONLY_UNAPPROVED"
    result = render_godot_project(
        project, base / "movie", timeout_seconds=120
    )
    mp4 = Path(result["mp4"])
    if not mp4.is_file() or mp4.stat().st_size <= 1000:
        raise RuntimeError("Godot/FFmpeg did not produce a usable video file.")
    if result["frames_expected"] != 3:
        raise RuntimeError("Godot produced unexpected frame count.")
    print("REAL_GODOT_SMOKE_PASS")
    print(json.dumps({
        "status": result["status"],
        "mp4_bytes": result["mp4_bytes"],
        "mp4_sha256": result["mp4_sha256"],
        "frames_expected": result["frames_expected"],
        "asset_status": exported["status"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
