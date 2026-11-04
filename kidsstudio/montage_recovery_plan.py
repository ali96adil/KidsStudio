"""M56: propose a fresh, separate private montage attempt from M55 evidence.

A prepared proposal is NEVER an enqueued/renderable Pi job. Reused scene
candidates pass fresh M7 technical full-decode and immutable SHA checks;
all other scenes fall back to the previously approved original LTX MP4.
Existing M14/M49/M51/M52 and M7 final gates are not amended or bypassed.
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
from uuid import uuid4

from .episode_assembly import EpisodeAssembler, digest
from .episode_quality import CHECKS, inspect_video
from .media_worker import MediaRecipes, MediaError
from .montage_recovery import (
    RecoveryError, RecoveryJournal, _canonical, inspect_quarantined_montage,
)

JOB=re.compile(r"^[a-f0-9]{32}$")
NORMAL=re.compile(r"^([0-9]{3})_normalized\.mp4$")
SHA=re.compile(r"^[a-f0-9]{64}$")
MAX_FROZEN_BYTES=160_000


class RecoveryPlanError(ValueError):
    """Original montage or recovered candidate has untrusted provenance."""


def _frozen_report(root: Path, original_job_id: str) -> tuple[dict, str]:
    file=root/"_recovery_evidence"/(original_job_id+".json")
    if (file.is_symlink() or not file.is_file() or
        not 0<file.stat().st_size<=MAX_FROZEN_BYTES):
        raise RecoveryPlanError("M56 requires exact frozen M55 evidence.")
    try:
        snapshot=json.loads(file.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError) as exc:
        raise RecoveryPlanError("M56 frozen evidence unreadable.") from exc
    if (not isinstance(snapshot,dict) or
        set(snapshot)!={"schema_version","report","report_sha256"} or
        snapshot["schema_version"]!=1 or
        not isinstance(snapshot["report"],dict) or
        not isinstance(snapshot["report_sha256"],str) or
        not SHA.fullmatch(snapshot["report_sha256"]) or
        hashlib.sha256(_canonical(snapshot["report"])).hexdigest()!=
        snapshot["report_sha256"] or
        snapshot["report"].get("job_id")!=original_job_id or
        snapshot["report"].get("status")!="M55_QUARANTINED_INSPECTION_ONLY"):
        raise RecoveryPlanError("M56 M55 frozen inspection identity mismatch.")
    return snapshot["report"],snapshot["report_sha256"]


def plan_private_montage_recovery(
    recipes: MediaRecipes,
    journal: RecoveryJournal, *,
    original_job_id: str,
    payload: dict[str,Any],
    proposal_id: str,
    prober=None,
    full_qa: Callable[[Path,str],dict[str,Any]] | None = None,
) -> dict[str,Any]:
    """Pure dry-run: no writes, no Pi job, no model execution, no reuse grants.

    full_qa must perform M7 full media decode on every candidate it passes.
    Only injected synthetic test functions may substitute a fake check.
    """
    if (not isinstance(original_job_id,str) or
        not JOB.fullmatch(original_job_id) or
        not isinstance(proposal_id,str) or
        not JOB.fullmatch(proposal_id) or proposal_id==original_job_id):
        raise RecoveryPlanError("M56 new 32-hex proposal identity must differ.")
    if not isinstance(payload,dict) or not isinstance(payload.get("recipe_id"),str):
        raise RecoveryPlanError("M56 exact original payload required.")
    try:
        catalogue=recipes.resolve("episode_assemble",payload["recipe_id"])
        assembler=EpisodeAssembler(catalogue["inputs"]["episode_recipe"])
        root=assembler.output_root
        if prober is None:
            current=inspect_quarantined_montage(
                recipes,journal,job_id=original_job_id,payload=payload)
        else:
            current=inspect_quarantined_montage(
                recipes,journal,job_id=original_job_id,
                payload=payload,prober=prober)
        frozen,frozen_sha=_frozen_report(root,original_job_id)
        if _canonical(current)!=_canonical(frozen):
            raise RecoveryPlanError("M56 frozen M55 evidence is stale or incomplete.")
    except (RecoveryError,MediaError,OSError,ValueError,KeyError,
            TypeError,AttributeError) as exc:
        if isinstance(exc,RecoveryPlanError):
            raise
        raise RecoveryPlanError("M56 private source or snapshot verification failed.") from exc
    if current["warnings"] and any(w not in {
            "FAILED_TO_PROBE_OUTPUT","EMPTY_OR_OVERSIZED_RENDER_ARTIFACT"
        } for w in current["warnings"]):
        raise RecoveryPlanError("M56 suspicious unexpected artifacts require triage.")
    proposal_file=root/"_recovery_proposals"/(proposal_id+".json")
    if (proposal_file.exists() or proposal_file.is_symlink() or
        (root/proposal_id).exists()):
        raise RecoveryPlanError("M56 proposal or render identity already exists.")

    by_scene={}
    for artifact in current["artifacts"]:
        match=NORMAL.fullmatch(artifact["name"])
        if match:
            by_scene[int(match.group(1))]=artifact
    checks=full_qa
    if checks is None:
        def checks(path:Path,expected:str) -> dict[str,Any]:
            return inspect_video(
                path,expected,ffmpeg=assembler.ffmpeg,
                ffprobe=assembler.ffprobe)
    stages=[]
    for position,source in enumerate(assembler.recipe["clips"],1):
        original_path=Path(source["video"])
        if original_path.is_symlink() or not original_path.is_file() or (
            digest(original_path)!=source["sha256"]):
            raise RecoveryPlanError("M56 original approved scene source changed.")
        chosen=by_scene.get(position)
        strategy="USE_ORIGINAL_APPROVED_LTX_SOURCE"
        media=original_path
        media_sha=source["sha256"]
        technical_status="NOT_REUSED"
        if (chosen is not None and
            chosen.get("status")=="NORMALIZED_CANDIDATE_NOT_APPROVED_FOR_REUSE" and
            isinstance(chosen.get("sha256"),str) and
            SHA.fullmatch(chosen["sha256"])):
            candidate=root/original_job_id/chosen["name"]
            if (candidate.is_symlink() or not candidate.is_file() or
                candidate.resolve()!=candidate or
                digest(candidate)!=chosen["sha256"]):
                raise RecoveryPlanError("M56 recovered media bytes changed.")
            try:
                qa=checks(candidate,chosen["sha256"])
            except (OSError,ValueError,TypeError,KeyError):
                qa=None
            if (isinstance(qa,dict) and
                qa.get("status")=="TECH_PASS_OWNER_REVIEW_PENDING" and
                qa.get("media_sha256")==chosen["sha256"] and
                qa.get("expected_media_sha256")==chosen["sha256"] and
                isinstance(qa.get("checks"),dict) and
                set(qa["checks"])==set(CHECKS) and
                all(qa["checks"].get(key) is True for key in CHECKS) and
                qa.get("publishing_approved") is False and
                qa.get("rights_verified") is False and
                qa.get("subjective_checks_performed") is False):
                strategy="REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
                media=candidate
                media_sha=chosen["sha256"]
                technical_status="M7_TECH_PASS_NOT_FINAL_QA"
            else:
                technical_status="RECOVERED_CANDIDATE_FAILED_M7_USE_ORIGINAL"
        stages.append({
            "scene":position,
            "strategy":strategy,
            "source_sha256":source["sha256"],
            "source_face_cleanup":source["face_cleanup"],
            "candidate_path":str(media),
            "candidate_sha256":media_sha,
            "candidate_technical_status":technical_status,
            "requires_new_scene_provenance_review":True,
            "candidate_approved_for_publication":False,
        })
    count=sum(stage["strategy"].startswith("REUSE_RECOVERED_")
              for stage in stages)
    plan={
        "schema_version":1,
        "status":"M56_FRESH_ATTEMPT_PROPOSED_NOT_QUEUED",
        "proposal_id":proposal_id,
        "original_job_id":original_job_id,
        "original_request_sha256":current["request_sha256"],
        "frozen_inspection_sha256":frozen_sha,
        "original_assembly_recipe_sha256":current["recipe_sha256"],
        "original_script_sha256":current["original_script_sha256"],
        "series_id":current["series_id"],
        "episode_number":current["episode_number"],
        "scene_count":current["scene_count"],
        "scenes":stages,
        "verified_normalized_candidates":count,
        "original_scene_fallback_count":len(stages)-count,
        "proposed_pi_job_id":None,
        "source_catalogue_sha256":payload.get("catalogue_sha256"),
        "requires_new_catalogue_and_scene_provenance":True,
        "requires_new_pi_authorized_job_and_lease":True,
        "requires_new_final_m7_full_decode_and_quality_reviews":True,
        "owner_private_preview_required":True,
        "auto_retry_allowed":False,
        "auto_execute_allowed":False,
        "auto_reuse_allowed":False,
        "public_release_authorized":False,
    }
    return plan


def freeze_private_montage_recovery(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict[str,Any],proposal_id:str,
    prober=None,full_qa=None,
) -> dict[str,Any]:
    """Write an exclusive, PRIVATE proposal only; do not queue or render."""
    plan=plan_private_montage_recovery(recipes,journal,
        original_job_id=original_job_id,payload=payload,
        proposal_id=proposal_id,prober=prober,full_qa=full_qa)
    recipe=recipes.resolve("episode_assemble",payload["recipe_id"])
    root=Path(recipe["output_root"]).resolve()
    folder=root/"_recovery_proposals"
    if folder.is_symlink():
        raise RecoveryPlanError("M56 proposal folder cannot be symlinked.")
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.resolve()!=folder:
        raise RecoveryPlanError("M56 proposal destination escaped private root.")
    target=folder/(proposal_id+".json")
    envelope={"schema_version":1,"proposal":plan,
              "proposal_sha256":hashlib.sha256(_canonical(plan)).hexdigest()}
    encoded=json.dumps(envelope,sort_keys=True,ensure_ascii=False,
                       allow_nan=False,indent=2).encode("utf-8")+b"\n"
    try:
        fd=os.open(str(target),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError as exc:
        raise RecoveryPlanError("M56 proposal already frozen.") from exc
    with os.fdopen(fd,"wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {"status":"M56_PRIVATE_PROPOSAL_FROZEN_NO_JOB_QUEUED",
            "proposal_id":proposal_id,
            "proposal_sha256":envelope["proposal_sha256"],
            "verified_normalized_candidates":plan["verified_normalized_candidates"],
            "original_scene_fallback_count":plan["original_scene_fallback_count"],
            "auto_execute_allowed":False,"public_release_authorized":False}


def main(argv:list[str]|None=None) -> int:
    p=argparse.ArgumentParser(prog="studio-montage-recovery-plan")
    p.add_argument("--recipes",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--original-job-id",required=True)
    p.add_argument("--original-payload-json",type=Path,required=True)
    p.add_argument("--proposal-id",default=None,
                   help="fresh 32-hex internal proposal identifier, NOT Pi job ID")
    p.add_argument("--freeze",action="store_true",
                   help="write only immutable private proposal; NEVER execute")
    args=p.parse_args(argv)
    try:
        from .montage_recovery import RecoveryJournal
        if (args.original_payload_json.is_symlink() or
            not args.original_payload_json.is_file() or
            not 0<args.original_payload_json.stat().st_size<=4096):
            raise RecoveryPlanError("M56 exact original private payload missing.")
        path=Path(args.journal).expanduser()
        if path.is_symlink() or not path.is_file():
            raise RecoveryPlanError("M56 original Mac STARTED journal required.")
        payload=json.loads(args.original_payload_json.read_text(encoding="utf-8"))
        recipes=MediaRecipes(args.recipes)
        journal=RecoveryJournal(path.resolve())
        proposal=args.proposal_id or uuid4().hex
        result=(freeze_private_montage_recovery(recipes,journal,
            original_job_id=args.original_job_id,payload=payload,
            proposal_id=proposal) if args.freeze else
            plan_private_montage_recovery(recipes,journal,
            original_job_id=args.original_job_id,payload=payload,
            proposal_id=proposal))
        print(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2))
        return 0
    except (RecoveryPlanError,RecoveryError,MediaError,OSError,ValueError,
            TypeError,KeyError) as exc:
        print("MONTAGE_RECOVERY_PLAN_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
