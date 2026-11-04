"""M11 static final handoff: compare M10 Mac inventory against M6 recipes.

This cross-check does NOT execute code, load models, infer voice/audio/video,
approve content, or authorize uploads. It closes the gap between separately
valid inventories and separately valid stage recipes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .mac_contract import check_mac_contract, MacIntakeError
from .engine_qualification import EngineQualificationError
from .voice_animation_stage import StagePlan, StageError
from .episode_assembly import digest, _ensure_private
from .private_asset_intake import verify_import, IntakeError


class HandoffError(ValueError):
    """Two individually pinned manifests disagree on Mac production inputs."""


def _approved(obj: dict, group: str, role: str) -> tuple[Path,str]:
    choices=[entry for entry in obj[group] if entry["role"]==role]
    if len(choices)!=1:
        raise HandoffError("Owner Mac contract missing required role.")
    entry=choices[0]
    return Path(entry["path"]).resolve(),entry["sha256"]


def _match(obj: dict, group: str, role: str, path: Path, sha: str) -> None:
    expected_path,expected_sha=_approved(obj,group,role)
    if expected_path!=path.resolve() or expected_sha!=sha or digest(path)!=sha:
        raise HandoffError(f"Stage {role} is not the same owner-pinned Mac asset.")


def _stage(stage_file: str | Path, kind: str, root: Path, obj: dict,
           contract_engines: dict[str,dict], *,
           expected_scene_script: tuple[Path, str] | None = None) -> dict[str,Any]:
    stage=StagePlan(stage_file)
    if stage.kind!=kind or stage.root!=root:
        raise HandoffError("Stage kind or private root differs from Mac contract.")
    evidence=stage.preflight()
    runner=stage.data["runner"]
    for role,location,sha in (
        (("voice_wrapper" if kind=="voice_synthesize" else "ltx_wrapper"),
         stage.entrypoint,runner["entrypoint_sha256"]),
    ):
        _match(obj,"assets",role,location,sha)
    _match(obj,"tools",
           "voice_python" if kind=="voice_synthesize" else "ltx_python",
           stage.python,runner["python_sha256"])
    _match(obj,"tools","ffprobe",stage.ffprobe,digest(stage.ffprobe))
    engine=contract_engines[kind]
    if (stage.engine_manifest!=Path(engine["path"]).resolve() or
        digest(stage.engine_manifest)!=engine["sha256"]):
        raise HandoffError("Engine manifest differs from qualified Mac inventory.")
    if expected_scene_script is None:
        # Legacy M11 full-episode static handoff requires the same parent
        # approved_script recorded in the Mac inventory.
        _match(obj,"assets","approved_script",
               stage.script,stage.data["script"]["sha256"])
        if kind=="voice_synthesize":
            _match(obj,"assets","approved_script",
                   stage.inputs["script"],stage.data["inputs"]["script"]["sha256"])
    else:
        # M19 may use a DIFFERENT per-scene owner-approved script. Only the
        # two-scene scene-plan validator may supply this override; it has
        # already pinned the episode to the Mac contract and each scene to
        # its explicit source bytes. Do not silently use the parent script.
        if kind!="voice_synthesize":
            raise HandoffError("Scene script override is voice-only.")
        approved_path, approved_sha = expected_scene_script
        if (stage.script != approved_path or
            stage.data["script"]["sha256"] != approved_sha or
            stage.inputs["script"] != approved_path or
            stage.data["inputs"]["script"]["sha256"] != approved_sha or
            digest(approved_path) != approved_sha):
            raise HandoffError("Scene voice recipe differs from approved scene script.")
    if kind=="ltx_animate":
        original,origin_sha=_approved(obj,"assets","bunny_reference")
        character=stage.inputs["reference_image"]
        local_sha=stage.data["inputs"]["reference_image"]["sha256"]
        if local_sha!=origin_sha or digest(character)!=origin_sha:
            raise HandoffError("LTX Bunny reference differs from original owner-approved image.")
        if character!=original:
            # M10 allows original source in ComfyUI-Shared; M6 cannot read
            # from outside its worker root. Require M11 versioned private copy.
            if (character.name!="bunny_reference.png" or
                character.parent.parent.name!="imports" or
                character.parent.parent.parent.name!="assets"):
                raise HandoffError("Use an explicit M11 Bunny reference import under worker root.")
            verify_import(root,character.parent.name,origin_sha)
        if character!=original and original.is_relative_to(root):
            raise HandoffError("Use the original local approved reference, not a needless copy.")
    return {
        "stage":kind,
        "status":"PINNED_CONFIG_VALIDATED_ENGINE_NOT_RUN",
        "script_sha256":evidence["script_sha256"],
        "voice_sha256":evidence["source_voice_sha256"],
        "recipe_sha256":stage.recipe_hash,
        "runtime_sha256":runner["python_sha256"],
        "wrapper_sha256":runner["entrypoint_sha256"],
        "engine_manifest_sha256":digest(stage.engine_manifest),
        "output_root_agrees":stage.output_root.is_relative_to(root),
        "inference_performed":False,
        "human_qa_approved":False,
    }


def inspect_handoff(
    mac_contract: str | Path,
    voice_recipe: str | Path,
    *,
    ltx_recipe: str | Path | None = None,
    system: str | None = None,
    arch: str | None = None,
    memory_bytes: int | None = None,
    free_bytes: int | None = None
) -> dict[str,Any]:
    mac=Path(mac_contract).expanduser().resolve()
    qualified=check_mac_contract(mac,system=system,arch=arch,
                                 memory_bytes=memory_bytes,free_bytes=free_bytes)
    obj=json.loads(mac.read_text(encoding="utf-8"))
    root=_ensure_private(Path(obj["private_roots"][0]))
    engines={entry["kind"]:entry for entry in obj["engine_manifests"]}
    voice=_stage(voice_recipe,"voice_synthesize",root,obj,engines)
    ltx=_stage(ltx_recipe,"ltx_animate",root,obj,engines) if ltx_recipe else None
    if ltx and voice["script_sha256"]!=ltx["script_sha256"]:
        raise HandoffError("LTX and voice stage recipes pin different scripts.")
    return {
        "schema_version":1,
        "status":("STAGE_MANIFESTS_MATCH_NOT_RUN" if ltx else
                  "VOICE_READY_LTX_RECIPE_PENDING_APPROVED_WAV"),
        "mac_contract_sha256":qualified["contract_sha256"],
        "voice":voice,
        "ltx":ltx,
        "asset_roots_count":len(obj["private_roots"]),
        "models_executed":False,
        "actual_wrapper_api_tested":False,
        "voice_license_verified":False,
        "youtube_uploaded":False,
        "public_release_authorized":False,
        "next_action":("Use owner device for real stage test after approval."
                      if ltx else
                      "Qualify voice, produce owner-reviewed WAV, then pin LTX recipe."),
    }


def main(argv=None)->int:
    p=argparse.ArgumentParser(prog="studio-handoff-review")
    p.add_argument("--mac-contract",type=Path,required=True)
    p.add_argument("--voice-recipe",type=Path,required=True)
    p.add_argument("--ltx-recipe",type=Path)
    args=p.parse_args(argv)
    try:
        r=inspect_handoff(args.mac_contract,args.voice_recipe,ltx_recipe=args.ltx_recipe)
    except (HandoffError,MacIntakeError,EngineQualificationError,
            StageError,IntakeError,OSError,ValueError,KeyError,TypeError) as exc:
        print("STUDIO_HANDOFF_BLOCKED: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(r,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
