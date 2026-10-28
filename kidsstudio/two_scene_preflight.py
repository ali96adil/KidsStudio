"""M19: read-only TWO-scene voice handoff before any real Mac model run.

This checks two different owner-pinned scene scripts against an M13-style
scene plan, the parent M10 Mac asset contract, and two M6 voice recipes.
It does not call any engine, queue a job, open a network connection, edit
SQLite, or attest to genuine Pi/owner approval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

from .episode_assembly import _ensure_private, _required_file, digest
from .mac_contract import check_mac_contract, MacIntakeError
from .engine_qualification import EngineQualificationError
from .handoff_review import _approved, _stage, HandoffError
from .voice_animation_stage import StageError

SHA = re.compile(r"^[a-f0-9]{64}$")
ID = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")


class PilotPreflightError(ValueError):
    """Two-scene voice preparation is inconsistent or incomplete."""


def _canonical_local_file(path: str | Path, root: Path, *, limit: int) -> Path:
    requested = Path(path).expanduser()
    if not requested.is_absolute() or requested.is_symlink():
        raise PilotPreflightError("Private input must be absolute, non-symlinked.")
    resolved = requested.resolve()
    if (not resolved.is_relative_to(root) or not resolved.is_file()
            or not 0 < resolved.stat().st_size <= limit):
        raise PilotPreflightError("Private input is missing, outside Mac root or oversized.")
    _ensure_private(resolved.parent)
    return resolved


def inspect_two_scene_voice_pilot(
    mac_contract: str | Path,
    scene_plan: str | Path,
    *,
    scene_scripts: tuple[str | Path, str | Path],
    voice_recipes: tuple[str | Path, str | Path],
    system: str | None = None,
    arch: str | None = None,
    memory_bytes: int | None = None,
    free_bytes: int | None = None,
) -> dict[str, Any]:
    # M10 verifies exact checkpoint bytes, binaries and parent approved script.
    qualified = check_mac_contract(
        mac_contract, system=system, arch=arch,
        memory_bytes=memory_bytes, free_bytes=free_bytes,
    )
    mac_path = Path(mac_contract).expanduser().resolve()
    obj = json.loads(mac_path.read_text(encoding="utf-8"))
    root = _ensure_private(Path(obj["private_roots"][0]))
    engines = {entry["kind"]: entry for entry in obj["engine_manifests"]}
    parent_path, parent_sha = _approved(obj, "assets", "approved_script")
    if digest(parent_path) != parent_sha:
        raise PilotPreflightError("Approved parent episode source changed.")

    plan_path = _canonical_local_file(scene_plan, root, limit=100_000)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise PilotPreflightError("Private scene plan is invalid JSON.") from exc
    if not isinstance(plan, dict) or set(plan) != {
        "schema_version", "series_id", "episode_number",
        "episode_script_sha256", "scenes",
    }:
        raise PilotPreflightError("M13 scene plan schema mismatch.")
    if (type(plan["schema_version"]) is not int
            or plan["schema_version"] != 1
            or not isinstance(plan["series_id"], str)
            or not ID.fullmatch(plan["series_id"])
            or type(plan["episode_number"]) is not int
            or not 1 <= plan["episode_number"] <= 120
            or plan["episode_script_sha256"] != parent_sha
            or not isinstance(plan["scenes"], list)
            or len(plan["scenes"]) != 2):
        raise PilotPreflightError("Require exactly two scenes and the pinned parent script.")
    if len(scene_scripts) != 2 or len(voice_recipes) != 2:
        raise PilotPreflightError("Require exactly two scene scripts and voice recipes.")

    scenes = []
    scene_hashes = set()
    for index, (row, script_path, stage_path) in enumerate(
        zip(plan["scenes"], scene_scripts, voice_recipes), start=1
    ):
        if (not isinstance(row, dict) or set(row) != {
                "scene", "script_sha256", "objective"
            } or type(row["scene"]) is not int or row["scene"] != index
            or not isinstance(row["script_sha256"], str)
            or not SHA.fullmatch(row["script_sha256"])
            or not isinstance(row["objective"], str)
            or not 5 <= len(row["objective"].strip()) <= 220
            or row["script_sha256"] in scene_hashes):
            raise PilotPreflightError("Scene numbering, hash or teaching objective invalid.")
        scene_hashes.add(row["script_sha256"])
        script = _required_file(
            str(_canonical_local_file(script_path, root, limit=100_000)),
            row["script_sha256"], root,
        )
        recipe = _canonical_local_file(stage_path, root, limit=60_000)
        handoff = _stage(
            recipe, "voice_synthesize", root, obj, engines,
            expected_scene_script=(script, row["script_sha256"]),
        )
        scenes.append({
            "scene": index,
            "scene_script_sha256": row["script_sha256"],
            "voice_recipe_sha256": handoff["recipe_sha256"],
            "config_status": handoff["status"],
            "voice_rendered": False,
            "owner_wav_reviewed": False,
            "ltx_recipe_available": False,
        })

    return {
        "schema_version": 1,
        "status": "TWO_SCENE_VOICE_CONFIG_PINNED_NOT_RUN",
        "series_id": plan["series_id"],
        "episode_number": plan["episode_number"],
        "parent_script_sha256": parent_sha,
        "scene_plan_sha256": digest(plan_path),
        "mac_contract_sha256": qualified["contract_sha256"],
        "scene_count": 2,
        "scenes": scenes,
        "real_mac_execution_tested": False,
        "canonical_pi_scene_approval_verified": False,
        "actual_wrapper_api_tested": False,
        "voice_or_animation_generated": False,
        "educational_content_reviewed": False,
        "commercial_rights_verified": False,
        "file_modifications_performed": False,
        "model_inference_performed": False,
        "public_release_authorized": False,
        "next_action": (
            "Owner must independently verify this scene plan against Pi M13, "
            "review real wrapper APIs and licensing on Mac, then separately "
            "authorize the first one-shot voice stage. LTX requires a real "
            "owner-reviewed WAV SHA and a separate later stage recipe."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="studio-two-scene-preflight",
        description="Read-only two-scene M13/M10/M6 handoff; never starts AI.",
    )
    p.add_argument("--mac-contract", type=Path, required=True)
    p.add_argument("--scene-plan", type=Path, required=True)
    p.add_argument("--scene-1-script", type=Path, required=True)
    p.add_argument("--scene-1-voice-recipe", type=Path, required=True)
    p.add_argument("--scene-2-script", type=Path, required=True)
    p.add_argument("--scene-2-voice-recipe", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        report = inspect_two_scene_voice_pilot(
            args.mac_contract, args.scene_plan,
            scene_scripts=(args.scene_1_script, args.scene_2_script),
            voice_recipes=(args.scene_1_voice_recipe, args.scene_2_voice_recipe),
        )
    except (PilotPreflightError, HandoffError, MacIntakeError,
            EngineQualificationError, StageError, OSError, ValueError,
            KeyError, TypeError) as exc:
        # Do not echo private filesystem paths or text in operator error.
        print("TWO_SCENE_PREFLIGHT_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
