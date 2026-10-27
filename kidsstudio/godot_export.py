"""Export a self-contained Godot 4 rig-player project from approved parts.

No Godot process is launched and no external publishing occurs. Exported
artwork is copied only to a local non-repository directory.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from .motion import MOTIONS
from .rigqa import check_rig

PART_ID = re.compile(r"^[a-zA-Z0-9_]{1,80}$")
EPSILON = 1e-5
MAX_BEATS = 200


class GodotExportError(ValueError):
    """Scene is invalid or rig is not safe to export."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_scene_spec(path: str | Path) -> dict[str, Any]:
    """Strict timeline: contiguous beats, no gaps, no unsafe actions."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GodotExportError(f"Cannot read scene specification: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise GodotExportError("Scene specification schema_version must be 1.")
    fps = data.get("fps")
    duration = data.get("duration_seconds")
    if type(fps) is not int or not (1 <= fps <= 60):
        raise GodotExportError("fps must be an integer between 1 and 60.")
    if type(duration) not in (float, int) or not (0.1 <= duration <= 600):
        raise GodotExportError("duration_seconds must be between 0.1 and 600.")
    beats = data.get("beats")
    if not isinstance(beats, list) or not (1 <= len(beats) <= MAX_BEATS):
        raise GodotExportError("Scene must contain 1..200 beats.")
    next_start = 0.0
    for index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            raise GodotExportError(f"beat[{index}] must be an object.")
        start, end, motion = (beat.get("start"), beat.get("end"), beat.get("motion"))
        if type(start) not in (float, int) or type(end) not in (float, int):
            raise GodotExportError(f"beat[{index}]: start/end must be numbers.")
        if not (abs(start - next_start) < EPSILON and
                end > start and end <= duration + EPSILON):
            raise GodotExportError(f"beat[{index}]: timeline has a gap, overlap, or invalid end.")
        if motion not in MOTIONS:
            raise GodotExportError(f"beat[{index}]: unknown action: {motion!r}")
        next_start = float(end)
    if abs(next_start - duration) > EPSILON:
        raise GodotExportError("The last beat must end at duration_seconds.")
    return data


def check_review_gate(
    manifest_path: str | Path,
    review_report: str | Path,
    evidence_path: str | Path,
) -> dict[str, Any]:
    """Check review is PASS and tied to the exact current PNG layers.

    A local AI PASS is only an internal asset gate, never publication permission.
    """
    manifest = Path(manifest_path).expanduser().resolve()
    review = Path(review_report).expanduser().resolve()
    evidence = Path(evidence_path).expanduser().resolve()
    try:
        decision = json.loads(review.read_text(encoding="utf-8"))
        proof = json.loads(evidence.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GodotExportError(f"Review evidence unavailable: {exc}") from exc
    if not isinstance(decision, dict) or not isinstance(proof, dict):
        raise GodotExportError("Review evidence must contain JSON objects.")
    if (decision.get("status") != "APPROVED_BY_LOCAL_AI_QA" or
        decision.get("verdict") != "PASS" or
        decision.get("owner_release_approval_required") is not True):
        raise GodotExportError("A valid independent local AI PASS is required.")
    if decision.get("evidence_sha256") != _digest(evidence):
        raise GodotExportError("Review is not tied to current motion evidence.")
    rig = json.loads(manifest.read_text(encoding="utf-8"))
    hashes = {"rig.json": _digest(manifest)}
    for part in rig["parts"]:
        hashes[part["file"]] = _digest(manifest.parent / part["file"])
    if proof.get("source_hashes") != hashes:
        raise GodotExportError("Review was made for different source layers.")
    sheet = evidence.parent / "motion_contact_sheet.png"
    if proof.get("contact_sheet_sha256") != _digest(sheet):
        raise GodotExportError("Contact sheet changed after review.")
    return decision


def export_godot(
    manifest_path: str | Path,
    scene_path: str | Path,
    output_directory: str | Path,
    *,
    require_reviewed: bool = False,
    review_report: str | Path | None = None,
    evidence_path: str | Path | None = None,
) -> dict[str, Any]:
    manifest = Path(manifest_path).expanduser().resolve()
    scene_file = Path(scene_path).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    report = check_rig(manifest)
    if not report["passed"]:
        raise GodotExportError("Rig technical QA failed: " + "; ".join(report["errors"]))
    scene = load_scene_spec(scene_file)
    if output.exists():
        raise FileExistsError("Godot export directory already exists; never overwrite.")
    if any((parent / ".git").exists() for parent in (output, *output.parents)):
        raise GodotExportError("Do not export original image assets inside Git.")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    for part in data["parts"]:
        if not PART_ID.fullmatch(part["id"]):
            raise GodotExportError(f"Unsafe Godot node id: {part['id']!r}")
    # Animated features need these joints even though basic technical QA may not.
    needed = {"body", "head", "arm_left", "arm_right", "leg_left", "leg_right"}
    if not needed.issubset({part["id"] for part in data["parts"]}):
        raise GodotExportError("Required Godot joints are missing.")
    if require_reviewed:
        if review_report is None or evidence_path is None:
            raise GodotExportError("A review report and motion evidence are required.")
        check_review_gate(manifest, review_report, evidence_path)

    # All input validation finishes before assets are written.
    assets = output / "assets"
    scripts = output / "scripts"
    assets.mkdir(parents=True, exist_ok=False)
    scripts.mkdir()
    normalized = copy.deepcopy(data)
    for part in normalized["parts"]:
        src = (manifest.parent / part["file"]).resolve()
        target = assets / (part["id"] + ".png")
        shutil.copyfile(src, target)
        part["file"] = "assets/" + part["id"] + ".png"
    (output / "rig.json").write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    (output / "scene_spec.json").write_text(
        json.dumps(scene, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    script_path = Path(__file__).with_name("godot_player.gd")
    (scripts / "rig_player.gd").write_bytes(script_path.read_bytes())
    (output / "project.godot").write_text(
        '; Generated by KidsStudio. Do not overwrite this export.\n'
        'config_version=5\n\n'
        '[application]\n\n'
        'config/name="KidsStudio Rig Preview"\n'
        'run/main_scene="res://main.tscn"\n\n'
        '[display]\n\n'
        'window/size/viewport_width=1280\n'
        'window/size/viewport_height=720\n\n'
        '[rendering]\n\n'
        'renderer/rendering_method="gl_compatibility"\n'
        'renderer/rendering_method.mobile="gl_compatibility"\n',
        encoding="utf-8"
    )
    (output / "main.tscn").write_text(
        '[gd_scene load_steps=2 format=3]\n\n'
        '[ext_resource type="Script" path="res://scripts/rig_player.gd" id="1"]\n\n'
        '[node name="KidsStudioRigPreview" type="Node2D"]\n'
        'script = ExtResource("1")\n',
        encoding="utf-8"
    )
    status = (
        "INTERNAL_RIG_QA_PASSED_NOT_PUBLICATION_APPROVED"
        if require_reviewed else "PREVIEW_ONLY_UNAPPROVED"
    )
    metadata = {
        "schema_version": 1,
        "character_id": data["character_id"],
        "status": status,
        "owner_publication_approval_required": True,
        "scene_duration_seconds": scene["duration_seconds"],
        "fps": scene["fps"],
        "source_manifest_sha256": _digest(manifest),
        "source_scene_sha256": _digest(scene_file),
        "exported_parts": [part["id"] for part in normalized["parts"]],
    }
    (output / "export_report.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata
