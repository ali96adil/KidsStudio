"""Bounded two-part art qualification before generating the whole bunny.

An approved reference-conditioned local ComfyUI workflow produces precisely
two independent layers: body and viewer-right arm. Technical evidence and
joint overlap screening are saved, but no artistic/public approval is given.
The Pi/remote studio is NOT allowed to trigger this exploratory probe.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw

from .comfy import prepare_submission
from .factory import (
    FactoryError, LocalComfyClient, _early_part_geometry_gate, _json_atomic,
    _store_rgba_png, inspect_reference_image,
)
from .planner import make_rig_plan
from .workflow_audit import audit_character_workflow


class ProbeError(ValueError):
    """The small-scale art qualification may not proceed."""


def joint_overlap(
    body_file: Path, arm_file: Path, pivot: list[int],
    *, radius: int = 38, alpha_threshold: int = 32,
) -> dict[str, Any]:
    """Look for both alpha masks meeting near the arm root.

    Nonzero overlap is useful preliminary evidence, NOT proof that a
    moving shoulder is seamless or proportionally correct.
    """
    with Image.open(body_file) as original_body, Image.open(arm_file) as original_arm:
        body = original_body.convert("RGBA")
        arm = original_arm.convert("RGBA")
        if body.size != arm.size:
            raise ProbeError("Body and arm sizes do not match.")
        width, height = body.size
        x, y = pivot
        region = (max(0, int(x) - radius), max(0, int(y) - radius),
                  min(width, int(x) + radius), min(height, int(y) + radius))
        if region[0] >= region[2] or region[1] >= region[3]:
            raise ProbeError("Invalid shoulder pivot/region.")
        a = body.getchannel("A").crop(region).point(
            lambda v: 255 if v >= alpha_threshold else 0
        )
        b = arm.getchannel("A").crop(region).point(
            lambda v: 255 if v >= alpha_threshold else 0
        )
        shared = ImageChops.multiply(a, b).histogram()[255]
        body_count = a.histogram()[255]
        arm_count = b.histogram()[255]
        return {
            "pivot": [int(x), int(y)], "radius": radius,
            "body_pixels": body_count, "arm_pixels": arm_count,
            "overlap_pixels": shared,
            "overlap_ratio_of_smaller_part": round(
                shared / min(body_count, arm_count), 5
            ) if min(body_count, arm_count) else 0.0,
            "technical_overlap_found": shared > 0,
            "seamless_motion_not_proven": True,
        }


def _checker(size: tuple[int, int], tile: int = 32) -> Image.Image:
    img = Image.new("RGB", size, (223, 227, 230))
    draw = ImageDraw.Draw(img)
    w, h = size
    for y in range(0, h, tile):
        for x in range(0, w, tile):
            if (x // tile + y // tile) % 2:
                draw.rectangle((x, y, min(w, x + tile), min(h, y + tile)),
                               fill=(178, 184, 190))
    return img.convert("RGBA")


def _make_evidence(
    body: Path, arm: Path, destination: Path, side: int,
    pivot: list[int],
) -> str:
    """Render five honest partial-rig views including two rotating-arm poses."""
    with Image.open(body) as source_body, Image.open(arm) as source_arm:
        torso = source_body.convert("RGBA")
        limb = source_arm.convert("RGBA")
    if torso.size != limb.size:
        raise ProbeError("Probe source canvas dimensions differ.")
    neutral = Image.alpha_composite(torso, limb)
    # Rotate the FULL transparent canvas about the exact approved shoulder
    # pivot. This is only an image-based motion diagnostic, not a Godot test.
    up = Image.alpha_composite(
        torso, limb.rotate(35, resample=Image.Resampling.BICUBIC,
                           center=tuple(pivot), expand=False)
    )
    down = Image.alpha_composite(
        torso, limb.rotate(-35, resample=Image.Resampling.BICUBIC,
                           center=tuple(pivot), expand=False)
    )
    frames = [
        ("BODY", torso), ("ARM RIGHT", limb),
        ("NEUTRAL", neutral), ("ARM +35 DEG", up), ("ARM -35 DEG", down),
    ]
    images: list[Image.Image] = []
    for label, view in frames:
        bg = _checker(view.size)
        bg.alpha_composite(view)
        bg.thumbnail((side, side), Image.Resampling.LANCZOS)
        images.append(bg.convert("RGB"))
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    sheet = Image.new("RGB", (width * len(images), height + 44),
                      (245, 246, 247))
    draw = ImageDraw.Draw(sheet)
    for index, ((label, _), image) in enumerate(zip(frames, images)):
        x = width * index
        draw.text((x + 12, 14), label, fill=(20, 24, 28))
        sheet.paste(image, (x, 44))
    sheet.save(destination, "PNG")
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def run_two_part_probe(
    blueprint_file: str | Path,
    workflow_file: str | Path,
    profile_file: str | Path,
    reference_image: str | Path,
    output_directory: str | Path,
    *, client: Any | None = None, timeout_seconds: int = 900,
    preview_side: int = 512,
) -> dict[str, Any]:
    """Produce body + right arm ONLY, with immutable evidence and no retries.

    This does not consume any remote/paid AI API. On a real Mac it invokes
    the approved local ComfyUI exactly twice after one canonical upload.
    """
    if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 3600:
        raise ProbeError("Timeout must be 30..3600 seconds per part.")
    if type(preview_side) is not int or not 128 <= preview_side <= 1024:
        raise ProbeError("Preview side must be 128..1024 pixels.")
    out = Path(output_directory).expanduser().resolve()
    if out.exists():
        raise FileExistsError("Probe directory exists; never overwrite test artwork.")
    if any((parent / ".git").exists() for parent in (out, *out.parents)):
        raise ProbeError("Production artwork must remain outside Git.")

    # All local-only and checksum-locked preflight operations happen before
    # any network request, new output folder, or GPU submission.
    preflight = audit_character_workflow(
        blueprint_file, workflow_file, profile_file, reference_image,
    )
    plan = make_rig_plan(blueprint_file)
    jobs = {job["part_id"]: job for job in plan["jobs"]}
    if not {"body", "arm_right"}.issubset(jobs):
        raise ProbeError("The probe needs body and arm_right in the approved rig.")
    for name in ("body", "arm_right"):
        if jobs[name]["expected_region"] is None:
            raise ProbeError("Probe requires strict placement regions on both parts.")
    policy = plan["rig_manifest_template"]["qa_policy"]
    if not policy["strict_parts"]:
        raise ProbeError("Probe requires strict_parts anatomical QA.")
    reference_bytes, reference_name, _ = inspect_reference_image(reference_image)
    prepared = {
        name: prepare_submission(
            workflow_file, profile_file,
            prompt_text=jobs[name]["prompt"],
            filename_prefix=f"KidsStudio/{plan['character_id']}/probe/{name}",
            reference_image_name=reference_name,
        )
        for name in ("body", "arm_right")
    }
    active = client if client is not None else LocalComfyClient()
    out.mkdir(parents=True, exist_ok=False)
    (out / "parts").mkdir()
    report: dict[str, Any] = {
        "schema_version": 1,
        "character_id": plan["character_id"],
        "status": "PROBE_RUNNING",
        "preview_is_not_publication_approval": True,
        "approved_workflow_sha256": preflight["workflow_sha256"],
        "reference_sha256": preflight["reference_sha256"],
        "part_order": ["body", "arm_right"],
        "evidence_panels": [
            "BODY", "ARM RIGHT", "NEUTRAL", "ARM +35 DEG", "ARM -35 DEG"
        ],
        "shoulder_pivot": jobs["arm_right"]["pivot"],
        "jobs": [],
        "qa": {},
    }
    report_file = out / "probe_report.json"
    _json_atomic(report_file, report)
    fingerprints: dict[str, str] = {}
    try:
        uploaded = active.upload_reference(reference_bytes, reference_name)
        if uploaded != reference_name:
            raise FactoryError("Canonical reference upload was not acknowledged.")
        for name in ("body", "arm_right"):
            job = jobs[name]
            entry = {"part_id": name, "status": "QUEUED"}
            report["jobs"].append(entry)
            _json_atomic(report_file, report)
            prompt_id = active.queue(prepared[name])
            entry["status"] = "RUNNING"
            entry["prompt_id"] = prompt_id
            _json_atomic(report_file, report)
            image_ref = active.await_image(
                prompt_id,
                save_node_id=prepared[name]["save_node_id"],
                timeout_seconds=timeout_seconds,
            )
            content = active.download_png(image_ref)
            target = out / "parts" / (name + ".png")
            digest = _store_rgba_png(
                content, target,
                (plan["canvas"]["width"], plan["canvas"]["height"]),
            )
            measures = _early_part_geometry_gate(
                target, job, policy, fingerprints
            )
            entry.update({
                "status": "COLLECTED", "sha256": digest,
                "file": "parts/" + name + ".png", "geometry": measures,
            })
            _json_atomic(report_file, report)

        body = out / "parts" / "body.png"
        arm = out / "parts" / "arm_right.png"
        overlap = joint_overlap(
            body, arm, jobs["arm_right"]["pivot"],
            alpha_threshold=policy["alpha_threshold"],
        )
        report["qa"]["shoulder_neutral"] = overlap
        evidence = out / "probe_contact_sheet.png"
        report["qa"]["contact_sheet_sha256"] = _make_evidence(
            body, arm, evidence, preview_side,
            jobs["arm_right"]["pivot"],
        )
        report["status"] = (
            "PROBE_READY_FOR_VISUAL_INSPECTION"
            if overlap["technical_overlap_found"] else
            "PROBE_BLOCKED_NO_SHOULDER_OVERLAP"
        )
    except Exception as exc:
        report["status"] = "PROBE_FAILED"
        report["error_type"] = type(exc).__name__
        # Raw local model/http exception text may contain private paths or URLs.
        report["error_code"] = "LOCAL_GENERATION_OR_QA_FAILURE"
        _json_atomic(report_file, report)
        raise
    _json_atomic(report_file, report)
    return report
