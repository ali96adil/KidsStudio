"""Generate structured rig-part prompts, not artwork.

This is the deterministic planning stage. A future AI art-generation adapter will
submit these instructions to ComfyUI and persist provenance and visual QA results.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .rigqa import MINIMUM_PARTS, MAX_CANVAS


def make_rig_plan(blueprint_path: str | Path) -> dict[str, Any]:
    blueprint = Path(blueprint_path)
    data = json.loads(blueprint.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Invalid blueprint schema_version.")
    canvas = data.get("canvas", {})
    w, h = canvas.get("width"), canvas.get("height")
    if not (type(w) is int and type(h) is int and
            1 <= w <= MAX_CANVAS and 1 <= h <= MAX_CANVAS):
        raise ValueError("Invalid canvas.")
    identity = data.get("identity_prompt")
    character_id = data.get("character_id")
    if not isinstance(identity, str) or not identity.strip():
        raise ValueError("identity_prompt is required.")
    if not isinstance(character_id, str) or not character_id.strip():
        raise ValueError("character_id is required.")
    parts = data.get("parts")
    if not isinstance(parts, list):
        raise ValueError("parts must be a list.")
    ids = [p.get("id") for p in parts if isinstance(p, dict)]
    if len(ids) != len(parts) or len(set(ids)) != len(ids):
        raise ValueError("Each rig part needs a unique id.")
    if not MINIMUM_PARTS.issubset(set(ids)):
        raise ValueError("Missing essential head/body/limb parts.")

    jobs = []
    for part in parts:
        ident, instruction = part.get("id"), part.get("instruction")
        pivot, z = part.get("pivot"), part.get("z")
        if not isinstance(ident, str) or not ident:
            raise ValueError("Part id must be a non-empty string.")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"Missing instruction for {ident}.")
        if not (isinstance(pivot, list) and len(pivot) == 2
                and all(type(v) in (int, float) for v in pivot)
                and 0 <= pivot[0] < w and 0 <= pivot[1] < h):
            raise ValueError(f"Invalid pivot for {ident}.")
        if type(z) is not int:
            raise ValueError(f"Invalid z-order for {ident}.")
        jobs.append({
            "part_id": ident,
            "target_png": f"assets/{ident}.png",
            "pivot": pivot,
            "z": z,
            "prompt": (
                f"Original character: {identity}. "
                f"Draw ONLY this isolated rig layer: {instruction}. "
                f"Preserve scale and registration within a {w}x{h} canvas. "
                "Transparent background. Keep concealed shoulder/neck/hip "
                "overlap regions fully painted for rotation. Clean layer edges. "
                "No other character parts, scene elements, labels or watermark."
            ),
        })

    return {
        "schema_version": 1,
        "character_id": character_id,
        "canvas": {"width": w, "height": h},
        "status": "PLAN_ONLY_NO_ART_GENERATED",
        "source_blueprint": str(blueprint),
        "jobs": jobs,
        "rig_manifest_template": {
            "schema_version": 1,
            "character_id": character_id,
            "canvas": {"width": w, "height": h},
            "parts": [
                {"id": j["part_id"], "file": j["target_png"],
                 "pivot": j["pivot"], "z": j["z"]}
                for j in jobs
            ],
        },
    }
