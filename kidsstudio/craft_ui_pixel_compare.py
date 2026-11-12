"""Offline pixel-level comparison for authorized KidsStudio dashboard screenshots.

No Craft Anything execution, browser navigation, image edits or media upload.
Pixel differences are diagnostic; they cannot certify accessibility or usability.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat, UnidentifiedImageError

from .craft_ui_evidence import audit_craft_ui_evidence
from .optional_tool_evidence import ToolEvidenceError, private_evidence_file, read_private_json

_MAX_PIXELS = 12_000_000
_MAX_PNG_BYTES = 15 * 1024 * 1024


def _rgb_from_private_png(root: str, relative_path: str) -> Image.Image:
    file = private_evidence_file(root, relative_path, max_bytes=_MAX_PNG_BYTES)
    try:
        with Image.open(file) as image:
            width, height = image.size
            if (image.format != "PNG" or not 1 <= width <= 5120
                    or not 1 <= height <= 16000 or width * height > _MAX_PIXELS):
                raise ToolEvidenceError("PNG dimensions or format unsupported.")
            image.load()  # Unlike the basic IHDR audit, fully decode the source.
            if "A" in image.getbands() or "transparency" in image.info:
                image = image.convert("RGBA")
                white = Image.new("RGBA", image.size, (255, 255, 255, 255))
                return Image.alpha_composite(white, image).convert("RGB")
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ToolEvidenceError("Screenshot could not be fully decoded.") from exc


def compare_craft_ui(
    *, evidence_root: str, baseline_manifest: dict,
    candidate_manifest: dict, mean_diff_limit: float = 0.01,
    changed_pixel_limit: float = 0.05, channel_threshold: int = 24,
) -> dict:
    for value in (mean_diff_limit, changed_pixel_limit):
        if type(value) not in (float, int) or not 0 <= value <= 1:
            raise ToolEvidenceError("Difference limits must be 0..1.")
    if type(channel_threshold) is not int or not 0 <= channel_threshold <= 255:
        raise ToolEvidenceError("Channel threshold must be an integer 0..255.")
    # Rehash all files before any of their pixels are analyzed.
    base_report = audit_craft_ui_evidence(root=evidence_root, manifest=baseline_manifest)
    candidate_report = audit_craft_ui_evidence(root=evidence_root, manifest=candidate_manifest)
    baseline = {r["viewport_css_width"]: r for r in baseline_manifest["screenshots"]}
    candidate = {r["viewport_css_width"]: r for r in candidate_manifest["screenshots"]}
    results = []
    for viewport in (375, 768, 1280):
        reference = _rgb_from_private_png(evidence_root, baseline[viewport]["relative_path"])
        actual = _rgb_from_private_png(evidence_root, candidate[viewport]["relative_path"])
        if reference.size != actual.size:
            raise ToolEvidenceError("Screenshots must have identical pixel dimensions at each viewport.")
        diff = ImageChops.difference(reference, actual)
        mean_diff = sum(ImageStat.Stat(diff).mean) / (3 * 255)
        red, green, blue = diff.split()
        largest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        # 0 or 255 mask, so its mean divided by 255 is the changed fraction.
        mask = largest.point(lambda value: 255 if value > channel_threshold else 0)
        changed_fraction = ImageStat.Stat(mask).mean[0] / 255
        within = mean_diff <= mean_diff_limit and changed_fraction <= changed_pixel_limit
        results.append({
            "viewport_css_width_reported": viewport,
            "pixel_width": reference.width,
            "pixel_height": reference.height,
            "mean_rgb_absolute_difference": round(mean_diff, 7),
            "changed_pixel_fraction": round(changed_fraction, 7),
            "within_configured_thresholds": within,
            "baseline_sha256": baseline[viewport]["sha256"].lower(),
            "candidate_sha256": candidate[viewport]["sha256"].lower(),
        })
    return {
        "schema_version": 1,
        "status": ("CRAFT_PIXEL_COMPARE_WITHIN_LIMITS_UNREVIEWED"
                   if all(r["within_configured_thresholds"] for r in results)
                   else "CRAFT_PIXEL_COMPARE_DIFFERENT_REVIEW_REQUIRED"),
        "viewports": results,
        "mean_diff_limit": mean_diff_limit,
        "changed_pixel_limit": changed_pixel_limit,
        "channel_threshold": channel_threshold,
        "all_screenshots_hash_verified": (
            base_report["status"] == "CRAFT_UI_EVIDENCE_HASH_VERIFIED_VISUAL_UNREVIEWED"
            and candidate_report["status"] == "CRAFT_UI_EVIDENCE_HASH_VERIFIED_VISUAL_UNREVIEWED"),
        "full_png_decoding_performed": True,
        "pixel_difference_measured": True,
        "baseline_provenance_authenticated": False,
        "candidate_provenance_authenticated": False,
        "real_craft_anything_invoked": False,
        "layout_functionality_verified": False,
        "accessibility_verified": False,
        "arabic_text_reviewed": False,
        "production_approved": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local two-manifest screenshot comparison")
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--baseline-manifest", required=True)
    parser.add_argument("--candidate-manifest", required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_craft_ui(
            evidence_root=args.evidence_root,
            baseline_manifest=read_private_json(args.evidence_root, args.baseline_manifest),
            candidate_manifest=read_private_json(args.evidence_root, args.candidate_manifest),
        )
    except (ToolEvidenceError, ValueError, OSError, TypeError, KeyError):
        print(json.dumps({"status": "CRAFT_PIXEL_COMPARE_ERROR",
                          "production_approved": False, "publication_approved": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "CRAFT_PIXEL_COMPARE_WITHIN_LIMITS_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
