"""M60 Mac read-only recheck for a future dedicated recovery render worker.

The schema-2 source recipe remains NONEXECUTABLE. This verifier cannot
supply a lease or enqueue a job, and cannot generate a schema-1 recipe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .episode_assembly import digest
from .media_worker import MediaRecipes, MediaError
from .montage_recovery import RecoveryJournal, _canonical
from .recovery_execution_recipe import (
    prepare_private_recovery_recipe,RecoveryRecipeError
)

JOB=re.compile(r"^[0-9a-f]{32}$")
SHA=re.compile(r"^[0-9a-f]{64}$")


class RecoveryLocalGateError(ValueError):
    """M60 staged inputs diverge from the original approved private media."""


def verify_staged_m60_recovery(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict,proposal_id:str,
    prober=None,full_qa=None,
)->dict:
    """Recompute EVERY source SHA and M7 candidate decode, no writes."""
    args=dict(original_job_id=original_job_id,payload=payload,
              proposal_id=proposal_id)
    if prober is not None:args["prober"]=prober
    if full_qa is not None:args["full_qa"]=full_qa
    try:
        expected_recipe,expected_manifest=prepare_private_recovery_recipe(
            recipes,journal,**args)
        root=Path(expected_recipe["output_root"]).resolve()
        path=root/"_recovery_recipes"/(proposal_id+".json")
        outer=root/"_recovery_execution_manifests"/(proposal_id+".json")
        if (path.is_symlink() or outer.is_symlink() or
            not path.is_file() or not outer.is_file() or
            path.stat().st_size>120000 or
            outer.stat().st_size>160000):
            raise RecoveryLocalGateError("M60 original frozen M59 files missing.")
        raw=path.read_bytes()
        encoded=(json.dumps(expected_recipe,sort_keys=True,
            ensure_ascii=False,indent=2,allow_nan=False)+"\n").encode("utf-8")
        if (raw!=encoded or
            hashlib.sha256(raw).hexdigest()!=
                expected_manifest["derived_recipe_sha256"]):
            raise RecoveryLocalGateError("M60 staged media recipe changed.")
        evidence=json.loads(outer.read_text(encoding="utf-8"))
        if (not isinstance(evidence,dict) or
            set(evidence)!={"schema_version","manifest","manifest_sha256"} or
            evidence["schema_version"]!=2 or
            not isinstance(evidence["manifest"],dict) or
            evidence["manifest"]!=expected_manifest or
            evidence["manifest_sha256"]!=hashlib.sha256(
                _canonical(expected_manifest)).hexdigest()):
            raise RecoveryLocalGateError("M60 staged M59 metadata no longer current.")
        if (root/proposal_id).exists() or
            (root/proposal_id).is_symlink()):
            raise RecoveryLocalGateError("M60 future run ID already exists.")
        return {
            "status":"M60_MAC_STAGED_MEDIA_RECHECKED_NOT_EXECUTED",
            "proposal_id":proposal_id,
            "recipe_sha256":digest(path),
            "manifest_file_sha256":digest(outer),
            "recovered_candidates":expected_manifest["recovered_candidates"],
            "fallbacks":expected_manifest["fallbacks"],
            "new_pi_job_id":None,
            "media_rendered":False,
            "auto_execute_allowed":False,
            "public_release_authorized":False,
        }
    except (RecoveryRecipeError,MediaError,OSError,ValueError,
            UnicodeError,KeyError,TypeError) as exc:
        if isinstance(exc,RecoveryLocalGateError):raise
        raise RecoveryLocalGateError("M60 private media lineage recheck failed.") from exc


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-recovery-local-gate")
    p.add_argument("--recipes",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--original-job-id",required=True)
    p.add_argument("--original-payload",type=Path,required=True)
    p.add_argument("--proposal-id",required=True)
    args=p.parse_args(argv)
    try:
        j=Path(args.journal).expanduser()
        source=args.original_payload
        if (j.is_symlink() or not j.is_file() or
            source.is_symlink() or not source.is_file() or
            not 0<source.stat().st_size<=4096):
            raise RecoveryLocalGateError("M60 original private inputs absent.")
        result=verify_staged_m60_recovery(
            MediaRecipes(args.recipes),RecoveryJournal(j.resolve()),
            original_job_id=args.original_job_id,
            payload=json.loads(source.read_text(encoding="utf-8")),
            proposal_id=args.proposal_id)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (RecoveryLocalGateError,OSError,TypeError,ValueError):
        print("M60_LOCAL_MEDIA_RECHECK_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
