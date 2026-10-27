"""Safe, deterministic technical validation of rig-first character assets.

A technical pass is NOT a visual or educational approval. All artwork requires
independent visual QA and, where relevant, rights/pedagogical checks.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from .riggeometry import (
    validate_geometry_policy, measure_part_geometry, pixel_fingerprint
)

MINIMUM_PARTS = frozenset(
    {"body", "head", "arm_left", "arm_right", "leg_left", "leg_right"}
)
MAX_CANVAS = 4096
MAX_PARTS = 128


def _fail(report: dict[str, Any], issue: str) -> None:
    report["errors"].append(issue)


def check_rig(manifest_path: str | Path) -> dict[str, Any]:
    """Return a machine-readable technical QA report without editing assets."""
    manifest = Path(manifest_path).expanduser()
    report: dict[str, Any] = {
        "schema_version": 1,
        "manifest": str(manifest),
        "status": "FAIL",
        "passed": False,
        "errors": [],
        "warnings": [],
        "parts_checked": 0,
        "anatomical_checks_enabled": False,
        "part_geometry": {},
        "visual_review_required": True,
    }
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(report, f"Cannot load rig manifest: {exc}")
        return report

    if not isinstance(data, dict):
        _fail(report, "Manifest must be a JSON object.")
        return report
    if data.get("schema_version") != 1:
        _fail(report, "Unsupported schema_version; expected 1.")

    name = data.get("character_id")
    if not isinstance(name, str) or not name.strip():
        _fail(report, "character_id must be a nonempty string.")

    canvas = data.get("canvas")
    if not isinstance(canvas, dict):
        _fail(report, "canvas must be an object.")
        return report
    width, height = canvas.get("width"), canvas.get("height")
    if not (type(width) is int and type(height) is int
            and 1 <= width <= MAX_CANVAS and 1 <= height <= MAX_CANVAS):
        _fail(report, "Invalid canvas dimensions.")
        return report

    parts = data.get("parts")
    if not isinstance(parts, list) or not (1 <= len(parts) <= MAX_PARTS):
        _fail(report, f"parts must be a list of 1 to {MAX_PARTS} entries.")
        return report

    try:
        policy = validate_geometry_policy(
            data.get("qa_policy"), width, height, parts
        )
    except ValueError as exc:
        _fail(report, f"Invalid rig geometry policy: {exc}")
        return report
    strict = policy["strict_parts"]
    report["anatomical_checks_enabled"] = strict
    seen_fingerprints: dict[str, str] = {}

    ids: set[str] = set()
    files: set[Path] = set()
    base = manifest.resolve().parent
    for index, part in enumerate(parts):
        label = f"part[{index}]"
        if not isinstance(part, dict):
            _fail(report, f"{label} must be an object.")
            continue

        ident = part.get("id")
        if not isinstance(ident, str) or not ident:
            _fail(report, f"{label}: invalid id.")
            continue
        label = ident
        if ident in ids:
            _fail(report, f"{label}: duplicate part id.")
        ids.add(ident)

        raw = part.get("file")
        if not isinstance(raw, str) or not raw or "\\" in raw:
            _fail(report, f"{label}: invalid relative PNG file path.")
            continue
        rel = Path(raw)
        if rel.is_absolute() or rel.suffix.lower() != ".png" or ".." in rel.parts:
            _fail(report, f"{label}: unsafe or non-PNG file path.")
            continue
        image_path = (base / rel).resolve()
        if not image_path.is_relative_to(base):
            _fail(report, f"{label}: file escapes manifest directory.")
            continue
        if image_path in files:
            _fail(report, f"{label}: image reused for more than one part.")
        files.add(image_path)

        pivot = part.get("pivot")
        if not (isinstance(pivot, list) and len(pivot) == 2 and
                all(type(v) in (int, float) for v in pivot) and
                0 <= pivot[0] < width and 0 <= pivot[1] < height):
            _fail(report, f"{label}: pivot must be two in-canvas numbers.")
            continue

        if type(part.get("z")) is not int:
            _fail(report, f"{label}: z must be an integer.")
            continue

        try:
            with Image.open(image_path) as img:
                img.load()
                if img.format != "PNG":
                    _fail(report, f"{label}: file is not a PNG.")
                if img.mode != "RGBA":
                    _fail(report, f"{label}: image must be RGBA (has alpha).")
                    continue
                if img.size != (width, height):
                    _fail(report, f"{label}: image dimensions differ from canvas.")
                    continue
                if strict and policy["reject_identical_layers"]:
                    fingerprint = pixel_fingerprint(img)
                    if fingerprint in seen_fingerprints:
                        _fail(
                            report,
                            f"{label}: identical RGBA artwork reused from "
                            f"{seen_fingerprints[fingerprint]}, not an independent layer."
                        )
                    else:
                        seen_fingerprints[fingerprint] = label

                alpha = img.getchannel("A")
                extrema = alpha.getextrema()
                if extrema is None or extrema[1] == 0:
                    _fail(report, f"{label}: image contains no visible pixels.")
                if extrema is None or extrema[0] != 0:
                    _fail(report, f"{label}: image has no fully transparent pixels.")
                rect = part.get("expected_region")
                if strict and rect is not None:
                    measures = measure_part_geometry(
                        img, rect, alpha_threshold=policy["alpha_threshold"]
                    )
                    report["part_geometry"][label] = {
                        "expected_region": rect,
                        **measures
                    }
                    if measures["visible_pixels"] == 0:
                        _fail(report, f"{label}: no sufficiently opaque artwork.")
                    elif (
                        measures["outside_fraction"] >
                        policy["max_outside_fraction"] + 1e-6
                    ):
                        _fail(
                            report,
                            f"{label}: artwork is outside anatomical region "
                            f"({measures['outside_fraction']:.1%} of visible pixels)."
                        )
                    if (
                        measures["inside_fill_fraction"] + 1e-6 <
                        policy["min_inside_fill_fraction"]
                    ):
                        _fail(
                            report,
                            f"{label}: too little artwork inside expected region "
                            f"({measures['inside_fill_fraction']:.2%} fill)."
                        )
                bbox = alpha.getbbox()
                if bbox:
                    px, py = pivot
                    tolerance = 64
                    if not (bbox[0] - tolerance <= px <= bbox[2] + tolerance
                            and bbox[1] - tolerance <= py <= bbox[3] + tolerance):
                        report["warnings"].append(
                            f"{label}: pivot is far from visible pixels; visually confirm."
                        )
                report["parts_checked"] += 1
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            _fail(report, f"{label}: cannot read PNG: {exc}")

    for missing in sorted(MINIMUM_PARTS - ids):
        _fail(report, f"Missing required part: {missing}")

    if not report["errors"]:
        report["passed"] = True
        report["status"] = "TECHNICAL_PASS_PENDING_VISUAL_REVIEW"
        report["warnings"].append(
            "Anatomical bounds, when enabled, are not a guarantee of seamless "
            "overlap, consistent art, good acting, or correct animation."
        )
    return report
