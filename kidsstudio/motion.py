"""Deterministic motion previews for full-canvas, layered RGBA character rigs.

This is evidence for visual QA. It does not make artistic approval decisions.
No Godot is needed for this first review renderer; production uses Godot later.
"""
from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .rigqa import check_rig


MOTIONS = ("neutral", "wave_right", "wave_left", "head_tilt", "jump", "walk")


def load_rig(manifest_path: str | Path) -> tuple[dict[str, Any], list[tuple[dict[str, Any], Image.Image]]]:
    source = Path(manifest_path).expanduser().resolve()
    report = check_rig(source)
    if not report["passed"]:
        raise ValueError("Rig technical QA failed: " + "; ".join(report["errors"]))
    data = json.loads(source.read_text(encoding="utf-8"))
    layers = [
        (part, Image.open(source.parent / part["file"]).convert("RGBA"))
        for part in sorted(data["parts"], key=lambda p: p["z"])
    ]
    return data, layers


def _angle(name: str, motion: str, phase: float) -> float:
    sine = math.sin(math.pi * phase)
    cycle = math.sin(2 * math.pi * phase)
    if motion == "wave_right":
        return 70 * sine if name == "arm_right" else (7 * cycle if name == "head" else 0)
    if motion == "wave_left":
        return -70 * sine if name == "arm_left" else (7 * cycle if name == "head" else 0)
    if motion == "head_tilt":
        return 14 * cycle if name in {"head", "ear_left", "ear_right", "eyes", "mouth"} else 0
    if motion == "walk":
        return {
            "leg_left": 22 * cycle,
            "leg_right": -22 * cycle,
            "arm_left": -17 * cycle,
            "arm_right": 17 * cycle,
        }.get(name, 0)
    return 0


def compose_frame(
    rig: tuple[dict[str, Any], list[tuple[dict[str, Any], Image.Image]]],
    motion: str,
    phase: float,
    *,
    background: tuple[int, int, int] = (247, 246, 239),
    max_side: int = 512,
) -> Image.Image:
    if motion not in MOTIONS:
        raise ValueError(f"Unknown motion: {motion}")
    if not 0 <= phase <= 1:
        raise ValueError("Motion phase must be within 0..1")
    data, layers = rig
    w, h = data["canvas"]["width"], data["canvas"]["height"]
    scene = Image.new("RGBA", (w, h), background + (255,))
    offset_y = int(-0.10 * h * math.sin(math.pi * phase)) if motion == "jump" else 0
    for part, img in layers:
        deg = _angle(part["id"], motion, phase)
        transformed = (
            img.rotate(deg, resample=Image.Resampling.BICUBIC,
                       center=tuple(part["pivot"]), expand=False)
            if abs(deg) > 0.001 else img
        )
        if offset_y:
            raised = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            raised.alpha_composite(transformed, (0, offset_y))
            transformed = raised
        scene.alpha_composite(transformed)
    result = scene.convert("RGB")
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        result = result.resize(
            (max(1, round(w * scale)), max(1, round(h * scale))),
            Image.Resampling.LANCZOS,
        )
    return result


def create_motion_evidence(
    manifest_path: str | Path, output_directory: str | Path,
    *, side: int = 384, gif: bool = True
) -> dict[str, Any]:
    if not 96 <= side <= 1024:
        raise ValueError("Preview side must be between 96 and 1024.")
    out = Path(output_directory).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Preview output directory must be empty.")
    out.mkdir(parents=True, exist_ok=True)
    rig = load_rig(manifest_path)

    samples = []
    for motion in MOTIONS:
        for phase in (0.0, 0.5, 1.0):
            frame = compose_frame(rig, motion, phase, max_side=side)
            samples.append((motion, phase, frame))
    pad, label_h, columns = 12, 24, 3
    tw = side + 2 * pad
    th = side + label_h + 2 * pad
    rows = math.ceil(len(samples) / columns)
    sheet = Image.new("RGB", (columns * tw, rows * th), (228, 230, 233))
    draw = ImageDraw.Draw(sheet)
    for i, (motion, phase, frame) in enumerate(samples):
        x = (i % columns) * tw + pad
        y = (i // columns) * th + pad
        sheet.paste(frame, (x + (side - frame.width) // 2, y))
        draw.text((x + 4, y + side + 4),
                  f"{motion} / {phase:.1f}", fill=(25, 38, 53))
    sheet_file = out / "motion_contact_sheet.png"
    sheet.save(sheet_file)

    source = Path(manifest_path).resolve()
    source_data = json.loads(source.read_text(encoding="utf-8"))
    source_hashes = {"rig.json": hashlib.sha256(source.read_bytes()).hexdigest()}
    for part in source_data["parts"]:
        path = source.parent / part["file"]
        source_hashes[part["file"]] = hashlib.sha256(path.read_bytes()).hexdigest()

    result: dict[str, Any] = {
        "status": "MOTION_EVIDENCE_READY_PENDING_VISUAL_REVIEW",
        "manifest": str(Path(manifest_path).resolve()),
        "contact_sheet": str(sheet_file),
        "motions": list(MOTIONS),
        "visual_review_required": True,
        "source_hashes": source_hashes,
        "contact_sheet_sha256": hashlib.sha256(sheet_file.read_bytes()).hexdigest(),
    }

    if gif:
        frames = []
        for motion in MOTIONS:
            for i in range(10):
                frames.append(compose_frame(rig, motion, i / 9, max_side=side))
        gif_file = out / "motion_preview.gif"
        frames[0].save(gif_file, save_all=True, append_images=frames[1:],
                       duration=90, loop=0, optimize=False)
        result["animation"] = str(gif_file)

    report = out / "motion_evidence.json"
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
