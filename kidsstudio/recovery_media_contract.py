"""M58: private Mac media-byte revalidation before Pi recovery binding.

One-way immutable JSON contract, NO render, Pi job enqueue, model calls,
publishing or overwrite. A copied Mac manifest is NOT a signature.
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

from .episode_assembly import EpisodeAssembler, digest
from .episode_quality import CHECKS, inspect_video
from .media_worker import MediaRecipes, MediaError
from .montage_recovery import (
    RecoveryJournal, RecoveryError, _canonical, inspect_quarantined_montage
)

SHA=re.compile(r"^[0-9a-f]{64}$")
JOB=re.compile(r"^[0-9a-f]{32}$")
MAX_PROPOSAL=160_000
REUSE="REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
FALLBACK="USE_ORIGINAL_APPROVED_LTX_SOURCE"
STATUS="M58_MAC_MEDIA_BYTES_RECHECKED_NOT_RENDERED"


class RecoveryMediaError(ValueError):
    """M58 cannot attest a recovered media selection or approval."""


def _load_frozen_proposal(root:Path,proposal_id:str)->tuple[dict,str]:
    if not isinstance(proposal_id,str) or not JOB.fullmatch(proposal_id):
        raise RecoveryMediaError("M58 requires exact M56 proposal identity.")
    file=root/"_recovery_proposals"/(proposal_id+".json")
    if (file.is_symlink() or not file.is_file() or
        not 0<file.stat().st_size<=MAX_PROPOSAL):
        raise RecoveryMediaError("M56 frozen private proposal missing.")
    try:
        value=json.loads(file.read_text(encoding="utf-8"))
    except (UnicodeError,OSError,ValueError) as exc:
        raise RecoveryMediaError("M56 frozen proposal unreadable.") from exc
    if (not isinstance(value,dict) or
        set(value)!={"schema_version","proposal","proposal_sha256"} or
        value["schema_version"]!=1 or not isinstance(value["proposal"],dict) or
        not isinstance(value["proposal_sha256"],str) or
        not SHA.fullmatch(value["proposal_sha256"]) or
        hashlib.sha256(_canonical(value["proposal"])).hexdigest()!=
        value["proposal_sha256"] or
        value["proposal"].get("proposal_id")!=proposal_id or
        value["proposal"].get("status")!=
            "M56_FRESH_ATTEMPT_PROPOSED_NOT_QUEUED"):
        raise RecoveryMediaError("M56 proposal hash or status mismatch.")
    return value["proposal"],value["proposal_sha256"]


def _qa_ok(qa:Any,expected:str)->bool:
    return (isinstance(qa,dict) and
        qa.get("status")=="TECH_PASS_OWNER_REVIEW_PENDING" and
        qa.get("media_sha256")==expected and
        qa.get("expected_media_sha256")==expected and
        isinstance(qa.get("checks"),dict) and
        set(qa["checks"])==set(CHECKS) and
        all(qa["checks"][key] is True for key in CHECKS) and
        qa.get("rights_verified") is False and
        qa.get("publishing_approved") is False and
        qa.get("subjective_checks_performed") is False)


def verify_private_recovery_media(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict[str,Any],proposal_id:str,
    prober=None,
    full_qa:Callable[[Path,str],dict[str,Any]]|None=None,
)->dict[str,Any]:
    """Rehash ALL selected bytes, and full-decode each reused normalized clip.

    The Pi receives only hashes/scene indexes, no arbitrary Mac file paths.
    """
    if (not isinstance(original_job_id,str) or not JOB.fullmatch(original_job_id)
        or not isinstance(payload,dict) or
        not isinstance(payload.get("recipe_id"),str)):
        raise RecoveryMediaError("M58 original job/payload invalid.")
    try:
        item=recipes.resolve("episode_assemble",payload["recipe_id"])
        assembler=EpisodeAssembler(item["inputs"]["episode_recipe"])
        root=assembler.output_root
        proposal,proposal_sha=_load_frozen_proposal(root,proposal_id)
        params={"job_id":original_job_id,"payload":payload}
        if prober is not None:
            params["prober"]=prober
        current=inspect_quarantined_montage(recipes,journal,**params)
    except (RecoveryError,MediaError,OSError,ValueError,TypeError,
            KeyError,AttributeError) as exc:
        if isinstance(exc,RecoveryMediaError):
            raise
        raise RecoveryMediaError("M58 original journal/scene proof changed.") from exc
    if (proposal.get("original_job_id")!=original_job_id or
        proposal.get("original_request_sha256")!=current["request_sha256"] or
        proposal.get("frozen_inspection_sha256") is None or
        proposal.get("original_assembly_recipe_sha256")!=current["recipe_sha256"] or
        proposal.get("original_script_sha256")!=current["original_script_sha256"] or
        proposal.get("source_catalogue_sha256")!=current["catalogue_sha256"] or
        proposal.get("series_id")!=current["series_id"] or
        proposal.get("episode_number")!=current["episode_number"] or
        proposal.get("scene_count")!=current["scene_count"] or
        not isinstance(proposal.get("scenes"),list) or
        len(proposal["scenes"])!=current["scene_count"] or
        proposal.get("proposed_pi_job_id") is not None or
        proposal.get("auto_execute_allowed") is not False or
        proposal.get("auto_reuse_allowed") is not False or
        proposal.get("public_release_authorized") is not False):
        raise RecoveryMediaError("M58 original M56 private proposal lineage changed.")
    frozen=root/"_recovery_evidence"/(original_job_id+".json")
    if frozen.is_symlink() or not frozen.is_file():
        raise RecoveryMediaError("M58 M55 inspection evidence unavailable.")
    try:old=json.loads(frozen.read_text())
    except (OSError,UnicodeError,ValueError) as exc:
        raise RecoveryMediaError("M58 M55 inspection unreadable.") from exc
    if (not isinstance(old,dict) or not isinstance(old.get("report"),dict) or
        not isinstance(old.get("report_sha256"),str) or
        hashlib.sha256(_canonical(current)).hexdigest()!=old["report_sha256"] or
        _canonical(old["report"])!=_canonical(current) or
        proposal["frozen_inspection_sha256"]!=old["report_sha256"]):
        raise RecoveryMediaError("M58 frozen M55 evidence no longer matches bytes.")
    if current["warnings"] and any(w not in (
        "FAILED_TO_PROBE_OUTPUT","EMPTY_OR_OVERSIZED_RENDER_ARTIFACT")
        for w in current["warnings"]):
        raise RecoveryMediaError("M58 unexpected private output requires triage.")

    qa_fn=full_qa
    if qa_fn is None:
        def qa_fn(path:Path,expected:str)->dict[str,Any]:
            return inspect_video(path,expected,ffprobe=assembler.ffprobe,
                                 ffmpeg=assembler.ffmpeg)
    stages=[]
    reused=0
    for index,(original,scene) in enumerate(
            zip(assembler.recipe["clips"],proposal["scenes"]),1):
        if (not isinstance(scene,dict) or type(scene.get("scene")) is not int or
            scene["scene"]!=index or
            scene.get("source_sha256")!=original["sha256"] or
            scene.get("source_face_cleanup")!=original["face_cleanup"] or
            scene.get("candidate_approved_for_publication") is not False or
            scene.get("requires_new_scene_provenance_review") is not True):
            raise RecoveryMediaError("M58 original scene provenance differs.")
        original_path=Path(original["video"])
        if (original_path.is_symlink() or not original_path.is_file() or
            digest(original_path)!=original["sha256"]):
            raise RecoveryMediaError("M58 original approved LTX bytes changed.")
        strategy=scene.get("strategy")
        if strategy==REUSE:
            if scene.get("candidate_technical_status")!="M7_TECH_PASS_NOT_FINAL_QA":
                raise RecoveryMediaError("M58 reused scene lacks original M7 gate.")
            path=root/original_job_id/(f"{index:03}_normalized.mp4")
            if (path.is_symlink() or not path.is_file() or
                path.resolve()!=path or scene.get("candidate_path")!=str(path)
                or not isinstance(scene.get("candidate_sha256"),str) or
                not SHA.fullmatch(scene["candidate_sha256"]) or
                digest(path)!=scene["candidate_sha256"]):
                raise RecoveryMediaError("M58 recovered candidate differs from M56.")
            try:checked=qa_fn(path,scene["candidate_sha256"])
            except (OSError,ValueError,KeyError,TypeError) as exc:
                raise RecoveryMediaError("M58 full M7 decode could not pass.") from exc
            if not _qa_ok(checked,scene["candidate_sha256"]):
                raise RecoveryMediaError("M58 media failed fresh full M7 validation.")
            reused+=1
        elif strategy==FALLBACK:
            if (scene.get("candidate_path")!=str(original_path) or
                scene.get("candidate_sha256")!=original["sha256"] or
                scene.get("candidate_technical_status") not in
                    ("NOT_REUSED","RECOVERED_CANDIDATE_FAILED_M7_USE_ORIGINAL")):
                raise RecoveryMediaError("M58 fallback source is not approved original.")
        else:
            raise RecoveryMediaError("M58 strategy not accepted.")
        stages.append({
            "scene":index,"strategy":strategy,
            "original_ltx_sha256":original["sha256"],
            "selected_media_sha256":scene["candidate_sha256"],
            "full_m7_decode_confirmed":strategy==REUSE,
            "new_scene_provenance_required":True,
            "publication_approved":False,
        })
    if (reused!=proposal.get("verified_normalized_candidates") or
        len(stages)-reused!=proposal.get("original_scene_fallback_count")):
        raise RecoveryMediaError("M58 recovered/fallback counts changed.")
    return {
        "schema_version":1,"status":STATUS,
        "proposal_id":proposal_id,"proposal_sha256":proposal_sha,
        "original_job_id":original_job_id,
        "original_script_sha256":proposal["original_script_sha256"],
        "source_catalogue_sha256":proposal["source_catalogue_sha256"],
        "scene_count":len(stages),
        "scenes":stages,
        "recovered_candidates":reused,
        "fallbacks":len(stages)-reused,
        "new_pi_job_id":None,
        "pi_media_bytes_verified":False,
        "requires_new_execution_contract":True,
        "requires_fresh_mac_pre_execution_verification":True,
        "requires_final_master_m7_and_private_owner_preview":True,
        "auto_execute_allowed":False,
        "public_release_authorized":False,
    }


def freeze_private_recovery_media_contract(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict[str,Any],proposal_id:str,
    prober=None,full_qa=None,
)->dict[str,Any]:
    contract=verify_private_recovery_media(
        recipes,journal,original_job_id=original_job_id,
        payload=payload,proposal_id=proposal_id,prober=prober,
        full_qa=full_qa)
    item=recipes.resolve("episode_assemble",payload["recipe_id"])
    root=Path(item["output_root"]).resolve()
    folder=root/"_recovery_media_contracts"
    if folder.is_symlink():
        raise RecoveryMediaError("M58 contract folder must not be a symlink.")
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.resolve()!=folder:
        raise RecoveryMediaError("M58 evidence path escaped private root.")
    target=folder/(proposal_id+".json")
    envelope={"schema_version":1,"contract":contract,
              "contract_sha256":hashlib.sha256(_canonical(contract)).hexdigest()}
    encoded=json.dumps(envelope,ensure_ascii=False,sort_keys=True,
                       allow_nan=False,indent=2).encode("utf-8")+b"\n"
    try:fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:
        raise RecoveryMediaError("M58 contract already frozen; cannot overwrite.") from exc
    with os.fdopen(fd,"wb") as out:
        out.write(encoded);out.flush();os.fsync(out.fileno())
    return {
        "status":"M58_MAC_PRIVATE_MEDIA_CONTRACT_FROZEN_NO_RENDER",
        "proposal_id":proposal_id,
        "contract_file_sha256":hashlib.sha256(encoded).hexdigest(),
        "contract_sha256":envelope["contract_sha256"],
        "recovered_candidates":contract["recovered_candidates"],
        "fallbacks":contract["fallbacks"],
        "new_pi_job_id":None,"auto_execute_allowed":False,
        "public_release_authorized":False,
    }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-recovery-media-contract")
    p.add_argument("--recipes",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--original-job-id",required=True)
    p.add_argument("--original-payload-json",type=Path,required=True)
    p.add_argument("--proposal-id",required=True)
    p.add_argument("--freeze",action="store_true")
    args=p.parse_args(argv)
    try:
        payload_path=args.original_payload_json
        if (payload_path.is_symlink() or not payload_path.is_file() or
            not 0<payload_path.stat().st_size<=4096):
            raise RecoveryMediaError("M58 original payload file unavailable.")
        path=Path(args.journal).expanduser()
        if path.is_symlink() or not path.is_file():
            raise RecoveryMediaError("M58 original Mac journal missing.")
        payload=json.loads(payload_path.read_text(encoding="utf-8"))
        recipes=MediaRecipes(args.recipes)
        journal=RecoveryJournal(path.resolve())
        kw=dict(original_job_id=args.original_job_id,payload=payload,
                proposal_id=args.proposal_id)
        result=(freeze_private_recovery_media_contract(recipes,journal,**kw)
                if args.freeze else verify_private_recovery_media(
                    recipes,journal,**kw))
        print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (RecoveryMediaError,RecoveryError,MediaError,OSError,
            ValueError,TypeError,KeyError) as exc:
        print("M58_MEDIA_CONTRACT_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
