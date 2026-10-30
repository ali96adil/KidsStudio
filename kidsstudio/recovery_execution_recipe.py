"""M59: prepare a distinct PRIVATE recovery montage recipe and sealed metadata.

The M4-shaped staged recipe uses schema_version=2 and an explicit
non-executable marker, so EpisodeAssembler rejects it even when called
directly. The companion M59 manifest is also schema 2; M60+ must add a
new authorization and lease gate before compiling an executable recipe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable

from .episode_assembly import EpisodeAssembler, _ensure_private, digest
from .media_worker import MediaRecipes, MediaError
from .montage_recovery import RecoveryJournal, _canonical
from .recovery_media_contract import (
    RecoveryMediaError, verify_private_recovery_media,
    _load_frozen_proposal, REUSE, FALLBACK
)

JOB=re.compile(r"^[0-9a-f]{32}$")
SHA=re.compile(r"^[0-9a-f]{64}$")
MAX_CONTRACT=160_000

class RecoveryRecipeError(ValueError):
    """The fresh montage recipe is not bound to fully checked original bytes."""


def _frozen_media_contract(root:Path,proposal_id:str)->tuple[dict,str,str]:
    file=root/"_recovery_media_contracts"/(proposal_id+".json")
    if file.is_symlink() or not file.is_file() or not 0<file.stat().st_size<=MAX_CONTRACT:
        raise RecoveryRecipeError("M59 exact frozen M58 media contract required.")
    try:
        raw=file.read_bytes()
        value=json.loads(raw)
    except (OSError,UnicodeError,ValueError) as exc:
        raise RecoveryRecipeError("M59 unreadable M58 contract.") from exc
    if (not isinstance(value,dict) or
        set(value)!={"schema_version","contract","contract_sha256"} or
        value["schema_version"]!=1 or not isinstance(value["contract"],dict) or
        not isinstance(value["contract_sha256"],str) or
        not SHA.fullmatch(value["contract_sha256"]) or
        hashlib.sha256(_canonical(value["contract"])).hexdigest()!=
            value["contract_sha256"]):
        raise RecoveryRecipeError("M59 frozen M58 contract SHA mismatch.")
    return value["contract"],value["contract_sha256"],hashlib.sha256(raw).hexdigest()


def prepare_private_recovery_recipe(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict[str,Any],proposal_id:str,
    prober=None,full_qa:Callable|None=None,
)->tuple[dict[str,Any],dict[str,Any]]:
    """Read-only derivation: no output files, queue operations or inference."""
    if (not isinstance(original_job_id,str) or not JOB.fullmatch(original_job_id)
        or not isinstance(proposal_id,str) or not JOB.fullmatch(proposal_id)
        or proposal_id==original_job_id):
        raise RecoveryRecipeError("M59 distinct original/proposal IDs required.")
    try:
        approved=recipes.resolve("episode_assemble",payload["recipe_id"])
        assembler=EpisodeAssembler(approved["inputs"]["episode_recipe"])
        kwargs={"original_job_id":original_job_id,"payload":payload,
                "proposal_id":proposal_id}
        if prober is not None:kwargs["prober"]=prober
        if full_qa is not None:kwargs["full_qa"]=full_qa
        actual=verify_private_recovery_media(recipes,journal,**kwargs)
        frozen,contract_sha,contract_file_sha=_frozen_media_contract(
            assembler.output_root,proposal_id)
        if _canonical(actual)!=_canonical(frozen):
            raise RecoveryRecipeError("M59 M58 media bytes or frozen contract stale.")
        proposal,proposal_sha=_load_frozen_proposal(assembler.output_root,proposal_id)
    except (MediaError,RecoveryMediaError,OSError,ValueError,KeyError,
            TypeError,AttributeError) as exc:
        if isinstance(exc,RecoveryRecipeError):raise
        raise RecoveryRecipeError("M59 original recipe/media provenance not ready.") from exc

    if (proposal["original_job_id"]!=original_job_id or
        proposal["proposal_id"]!=proposal_id or
        actual["proposal_sha256"]!=proposal_sha or
        actual["original_script_sha256"]!=
            assembler.recipe["script"]["sha256"] or
        len(actual["scenes"])!=len(assembler.recipe["clips"]) or
        actual["new_pi_job_id"] is not None or
        actual["auto_execute_allowed"] is not False or
        actual["public_release_authorized"] is not False):
        raise RecoveryRecipeError("M59 original M56/M58 identity changed.")
    output=assembler.output_root
    if (output/(proposal_id)).exists():
        raise RecoveryRecipeError("M59 proposed ID already used as media run.")
    names=("_recovery_recipes","_recovery_execution_manifests")
    for folder in names:
        if (output/folder).is_symlink():
            raise RecoveryRecipeError("M59 staging folder must not be a link.")
        if (output/folder/(proposal_id+".json")).exists() or
            (output/folder/(proposal_id+".json")).is_symlink()):
            raise RecoveryRecipeError("M59 staged recipe/manifest already exists.")
    clips=[]
    scenes=[]
    for number,(prior,selection,source) in enumerate(zip(
            assembler.recipe["clips"],actual["scenes"],proposal["scenes"]),1):
        if (selection["scene"]!=number or source["scene"]!=number or
            prior["sha256"]!=selection["original_ltx_sha256"] or
            source["source_sha256"]!=prior["sha256"] or
            source["candidate_sha256"]!=selection["selected_media_sha256"] or
            selection["strategy"]!=source["strategy"]):
            raise RecoveryRecipeError("M59 original scene order/sha mismatch.")
        if selection["strategy"]==REUSE:
            candidate=(output/original_job_id/
                       f"{number:03}_normalized.mp4")
            # Already-normalized selected clips have no face rewrite stage.
            cleanup="none"
        elif selection["strategy"]==FALLBACK:
            candidate=Path(prior["video"])
            cleanup=prior["face_cleanup"]
        else:
            raise RecoveryRecipeError("M59 unrecognized recovery scene selection.")
        if (candidate.is_symlink() or not candidate.is_file() or
            candidate.resolve()!=candidate or
            not candidate.is_relative_to(assembler.root) or
            digest(candidate)!=selection["selected_media_sha256"]):
            raise RecoveryRecipeError("M59 selected private source bytes changed.")
        clips.append({"video":str(candidate),
                      "sha256":selection["selected_media_sha256"],
                      "face_cleanup":cleanup})
        scenes.append({
            "scene":number,"strategy":selection["strategy"],
            "original_ltx_sha256":prior["sha256"],
            "selected_media_sha256":selection["selected_media_sha256"],
            "applied_face_cleanup":cleanup,
            "full_m7_decode_confirmed":selection["full_m7_decode_confirmed"],
            "requires_new_scene_provenance_review":True,
            "publication_approved":False,
        })
    derived={
        "schema_version":2,
        "recovery_stage":"M59_STAGED_ONLY_NO_EXECUTION",
        "series_id":assembler.recipe["series_id"],
        "episode_number":assembler.recipe["episode_number"],
        "script":dict(assembler.recipe["script"]),
        "private_root":str(assembler.root),
        "output_root":str(output),
        "voice_rights":assembler.recipe["voice_rights"],
        "tools":dict(assembler.recipe["tools"]),
        "clips":clips,
    }
    # Exact raw bytes used for exclusive creation; SHA matches final file.
    recipe_bytes=(json.dumps(derived,ensure_ascii=False,sort_keys=True,
                             indent=2,allow_nan=False)+"\n").encode("utf-8")
    recipe_sha=hashlib.sha256(recipe_bytes).hexdigest()
    manifest={
        "schema_version":2,
        "status":"M59_PRIVATE_RECOVERY_RECIPE_STAGED_NOT_EXECUTABLE",
        "proposal_id":proposal_id,
        "original_job_id":original_job_id,
        "original_script_sha256":actual["original_script_sha256"],
        "source_catalogue_sha256":actual["source_catalogue_sha256"],
        "source_m58_contract_sha256":contract_sha,
        "source_m58_file_sha256":contract_file_sha,
        "derived_recipe_sha256":recipe_sha,
        "new_recipe_id":"recovery_"+proposal_id,
        "scene_count":len(scenes),
        "scenes":scenes,
        "recovered_candidates":actual["recovered_candidates"],
        "fallbacks":actual["fallbacks"],
        "new_pi_job_id":None,
        "new_m14_m49_lineage_required":True,
        "fresh_m53_m54_lease_required":True,
        "new_final_m7_quality_and_owner_preview_required":True,
        "auto_execute_allowed":False,
        "auto_retry_allowed":False,
        "public_release_authorized":False,
    }
    return derived,manifest


def freeze_private_recovery_recipe(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict[str,Any],proposal_id:str,
    prober=None,full_qa:Callable|None=None,
)->dict[str,Any]:
    """Stage non-executable v2 recipe/metadata once, no media catalogue."""
    recipe,manifest=prepare_private_recovery_recipe(
        recipes,journal,original_job_id=original_job_id,
        payload=payload,proposal_id=proposal_id,
        prober=prober,full_qa=full_qa)
    root=Path(recipe["output_root"]).resolve()
    folders=[root/"_recovery_recipes",root/"_recovery_execution_manifests"]
    for folder in folders:
        if folder.is_symlink():
            raise RecoveryRecipeError("M59 unsafe staging folder.")
        folder.mkdir(parents=True,mode=0o700,exist_ok=True)
        if folder.resolve()!=folder:
            raise RecoveryRecipeError("M59 staging folder escaped private output.")
    destinations=[p/(proposal_id+".json") for p in folders]
    recipe_bytes=(json.dumps(recipe,ensure_ascii=False,sort_keys=True,
                             indent=2,allow_nan=False)+"\n").encode("utf-8")
    envelope={"schema_version":2,"manifest":manifest,
              "manifest_sha256":hashlib.sha256(_canonical(manifest)).hexdigest()}
    manifest_bytes=(json.dumps(envelope,ensure_ascii=False,sort_keys=True,
                               indent=2,allow_nan=False)+"\n").encode("utf-8")
    if hashlib.sha256(recipe_bytes).hexdigest()!=manifest["derived_recipe_sha256"]:
        raise RecoveryRecipeError("M59 derived recipe hash changed during freeze.")
    for target,body in zip(destinations,(recipe_bytes,manifest_bytes)):
        try:
            fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError as exc:
            raise RecoveryRecipeError(
                "M59 existing staged file cannot be overwritten.") from exc
        with os.fdopen(fd,"wb") as out:
            out.write(body);out.flush();os.fsync(out.fileno())
    return {
        "status":"M59_PRIVATE_RECOVERY_RECIPE_FROZEN_NO_JOB",
        "proposal_id":proposal_id,
        "recipe_sha256":manifest["derived_recipe_sha256"],
        "execution_manifest_file_sha256":hashlib.sha256(manifest_bytes).hexdigest(),
        "execution_manifest_sha256":envelope["manifest_sha256"],
        "recovered_candidates":manifest["recovered_candidates"],
        "fallbacks":manifest["fallbacks"],
        "new_pi_job_id":None,
        "auto_execute_allowed":False,
        "public_release_authorized":False,
    }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-recovery-execution-recipe")
    p.add_argument("--recipes",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--original-job-id",required=True)
    p.add_argument("--original-payload-json",type=Path,required=True)
    p.add_argument("--proposal-id",required=True)
    p.add_argument("--freeze",action="store_true")
    args=p.parse_args(argv)
    try:
        original=args.original_payload_json
        if (original.is_symlink() or not original.is_file() or
            not 0<original.stat().st_size<=4096):
            raise RecoveryRecipeError("M59 exact original payload file missing.")
        source=Path(args.journal).expanduser()
        if source.is_symlink() or not source.is_file():
            raise RecoveryRecipeError("M59 original Mac STARTED journal required.")
        recipes=MediaRecipes(args.recipes)
        journal=RecoveryJournal(source.resolve())
        payload=json.loads(original.read_text(encoding="utf-8"))
        kw=dict(original_job_id=args.original_job_id,payload=payload,
                proposal_id=args.proposal_id)
        if args.freeze:
            result=freeze_private_recovery_recipe(recipes,journal,**kw)
        else:
            recipe,manifest=prepare_private_recovery_recipe(recipes,journal,**kw)
            result={"status":manifest["status"],"manifest":manifest,
                    "candidate_recipe_sha256":manifest["derived_recipe_sha256"],
                    "rendered":False,"public_release_authorized":False}
        print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (RecoveryRecipeError,MediaError,OSError,ValueError,TypeError,
            KeyError) as exc:
        print("M59_RECOVERY_RECIPE_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
