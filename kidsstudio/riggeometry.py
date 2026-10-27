"""Spatial contracts for rig-first parts (not artistic quality judgments).

Strict mode rejects painted layers outside their allowed anatomical envelope,
empty/tiny impostor parts and identical artwork reused for multiple joints.
Legacy manifests remain supported with strict mode opt-in.
"""
from __future__ import annotations

import hashlib
from typing import Any

from PIL import Image

DEFAULT_POLICY = {
    "strict_parts": False,
    "max_outside_fraction": 0.20,
    "min_inside_fill_fraction": 0.005,
    "alpha_threshold": 32,
    "reject_identical_layers": True,
}


def validate_geometry_policy(
    policy: Any, width: int, height: int, parts: list[dict[str, Any]]
) -> dict[str, Any]:
    if policy is None:
        return dict(DEFAULT_POLICY)
    if not isinstance(policy, dict):
        raise ValueError("qa_policy must be an object.")
    extras = set(policy) - set(DEFAULT_POLICY)
    if extras:
        raise ValueError(f"Unknown qa_policy fields: {sorted(extras)}")
    result = {**DEFAULT_POLICY, **policy}
    if type(result["strict_parts"]) is not bool:
        raise ValueError("strict_parts must be true or false.")
    if type(result["reject_identical_layers"]) is not bool:
        raise ValueError("reject_identical_layers must be true or false.")
    for field in ("max_outside_fraction", "min_inside_fill_fraction"):
        value = result[field]
        if type(value) not in (float, int) or not 0 <= value <= 0.5:
            raise ValueError(f"{field} must be a fraction between 0 and 0.5.")
    threshold = result["alpha_threshold"]
    if type(threshold) is not int or not 1 <= threshold <= 255:
        raise ValueError("alpha_threshold must be an integer 1..255.")
    for i, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f"part[{i}] is not a valid object.")
        rect = part.get("expected_region")
        if rect is None and result["strict_parts"]:
            raise ValueError(f"part[{i}] needs expected_region in strict mode.")
        if rect is not None:
            if not (
                isinstance(rect, list) and len(rect) == 4
                and all(type(v) is int for v in rect)
                and 0 <= rect[0] < rect[2] <= width
                and 0 <= rect[1] < rect[3] <= height
            ):
                raise ValueError(
                    f"part[{i}] has invalid expected_region [left,top,right,bottom]."
                )
    return result


def measure_part_geometry(
    image: Image.Image, rect: list[int], *, alpha_threshold: int
) -> dict[str, Any]:
    """Count alpha-covered pixels inside/outside the allowed region."""
    alpha = image.getchannel("A")
    # Binary mask includes only alpha exceeding the floor to avoid halos.
    mask = alpha.point(lambda a: 255 if a >= alpha_threshold else 0)
    all_counts = mask.histogram()
    visible_pixels = all_counts[255]
    cropped = mask.crop(tuple(rect))
    inside_pixels = cropped.histogram()[255]
    outside_pixels = visible_pixels - inside_pixels
    region_area = (rect[2] - rect[0]) * (rect[3] - rect[1])
    return {
        "visible_pixels": visible_pixels,
        "inside_pixels": inside_pixels,
        "outside_pixels": outside_pixels,
        "outside_fraction": (
            round(outside_pixels / visible_pixels, 6) if visible_pixels else 1.0
        ),
        "inside_fill_fraction": round(inside_pixels / region_area, 6),
        "visible_bbox": list(mask.getbbox()) if mask.getbbox() else None,
    }


def pixel_fingerprint(image: Image.Image) -> str:
    """Content hash, unlike PNG-file hash it ignores metadata/encoding."""
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
