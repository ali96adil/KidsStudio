"""M60: reserve a NEW non-dispatchable recovery job identity on the Pi.

Do NOT insert into the ordinary jobs table yet. Existing M52/53/54 checks
apply only to old episode_assemble leases; claiming this new identity before
a dedicated M61 recovery worker and claim/heartbeat guards would bypass
provenance checks. M60 therefore fails closed and reserves an identity only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from uuid import uuid4

from .recovery_intake import (
    RecoveryIntake, RecoveryIntakeError, _private_envelope, _verify, _table,
    _sha_json,
)
from .studio_queue import StudioQueue

SHA=re.compile(r"^[0-9a-f]{64}$")
JOB=re.compile(r"^[0-9a-f]{32}$")
STATE="M60_RECOVERY_JOB_RESERVED_NOT_DISPATCHABLE"


class RecoveryAdmissionError(ValueError):
    """A non-executable M59 contract is ineligible for a new job."""


def _read_pinned_copy(path:str|Path,checksum:str,limit:int)->dict:
    raw=Path(path).expanduser()
    if (not raw.is_absolute() or raw.is_symlink() or
        not isinstance(checksum,str) or not SHA.fullmatch(checksum)):
        raise RecoveryAdmissionError("M60 exact private copied file digest needed.")
    source=raw.resolve()
    if (not source.is_file() or not 0<source.stat().st_size<=limit or
        any((p/".git").exists() for p in (source.parent,*source.parents))):
        raise RecoveryAdmissionError("M60 staged file unavailable or unsafe.")
    body=source.read_bytes()
    if hashlib.sha256(body).hexdigest()!=checksum:
        raise RecoveryAdmissionError("M60 copied staged file SHA no longer matches.")
    try:
        data=json.loads(body)
    except (UnicodeError,ValueError,OSError) as exc:
        raise RecoveryAdmissionError("M60 staged file JSON invalid.") from exc
    if not isinstance(data,dict):
        raise RecoveryAdmissionError("M60 JSON object required.")
    return data


class RecoveryAdmission:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_reservations(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_execution_recipes(proposal_id),
                reserved_job_id TEXT NOT NULL UNIQUE,
                original_job_id TEXT NOT NULL,
                original_plan_sha256 TEXT NOT NULL,
                original_scene_set_sha256 TEXT NOT NULL,
                original_catalogue_sha256 TEXT NOT NULL,
                original_script_sha256 TEXT NOT NULL,
                fresh_recipe_sha256 TEXT NOT NULL,
                fresh_manifest_sha256 TEXT NOT NULL,
                media_contract_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(
                    state='M60_RECOVERY_JOB_RESERVED_NOT_DISPATCHABLE'),
                created_at REAL NOT NULL
            )""")

    def reserve(self, *,
        proposal_file:str|Path,proposal_sha256:str,
        recipe_file:str|Path,recipe_sha256:str,
        manifest_file:str|Path,manifest_sha256:str,
    )->dict:
        """Atomically reserve a new identity, never dispatch or render.

        This is a system-gate decision, NOT an extra per-scene human
        approval. M61 must re-check each pin at claim and lease renewal.
        """
        try:
            proposal,proposal_file_sha=_private_envelope(
                proposal_file,proposal_sha256)
        except (RecoveryIntakeError,OSError,ValueError) as exc:
            raise RecoveryAdmissionError("M60 original M56 payload invalid.") from exc
        if not isinstance(recipe_sha256,str) or not SHA.fullmatch(recipe_sha256):
            raise RecoveryAdmissionError("M60 recipe digest required.")
        recipe=_read_pinned_copy(recipe_file,recipe_sha256,120000)
        outer=_read_pinned_copy(manifest_file,manifest_sha256,160000)
        if (set(outer)!={"schema_version","manifest","manifest_sha256"}
            or outer["schema_version"]!=2 or
            not isinstance(outer["manifest"],dict) or
            not isinstance(outer["manifest_sha256"],str) or
            not SHA.fullmatch(outer["manifest_sha256"]) or
            _sha_json(outer["manifest"])!=outer["manifest_sha256"]):
            raise RecoveryAdmissionError("M60 manifest SHA or format changed.")
        m=outer["manifest"]
        pid=proposal["proposal_id"]
        if (set(recipe)!={"schema_version","recovery_stage","series_id",
                          "episode_number","script","private_root",
                          "output_root","voice_rights","tools","clips"} or
            recipe["schema_version"]!=2 or
            recipe["recovery_stage"]!="M59_STAGED_ONLY_NO_EXECUTION" or
            m.get("schema_version")!=2 or
            m.get("status")!="M59_PRIVATE_RECOVERY_RECIPE_STAGED_NOT_EXECUTABLE" or
            m.get("proposal_id")!=pid or
            m.get("original_job_id")!=proposal["original_job_id"] or
            m.get("derived_recipe_sha256")!=recipe_sha256 or
            m.get("original_script_sha256")!=proposal["original_script_sha256"] or
            m.get("source_catalogue_sha256")!=
                proposal["source_catalogue_sha256"] or
            m.get("scene_count")!=proposal["scene_count"] or
            recipe.get("series_id")!=proposal["series_id"] or
            recipe.get("episode_number")!=proposal["episode_number"] or
            not isinstance(recipe.get("script"),dict) or
            recipe["script"].get("sha256")!=proposal["original_script_sha256"] or
            not isinstance(m.get("scenes"),list) or
            len(m["scenes"])!=proposal["scene_count"] or
            not isinstance(recipe.get("clips"),list) or
            len(recipe["clips"])!=proposal["scene_count"] or
            m.get("new_pi_job_id") is not None or
            m.get("auto_execute_allowed") is not False or
            m.get("auto_retry_allowed") is not False or
            m.get("public_release_authorized") is not False or
            m.get("new_m14_m49_lineage_required") is not True or
            m.get("fresh_m53_m54_lease_required") is not True or
            m.get("new_final_m7_quality_and_owner_preview_required") is not True):
            raise RecoveryAdmissionError("M60 staged recipe admission flags changed.")
        for index,(scene,original,clip) in enumerate(
                zip(m["scenes"],proposal["scenes"],recipe["clips"]),1):
            if (not isinstance(scene,dict) or not isinstance(clip,dict) or
                scene.get("scene")!=index or original["scene"]!=index or
                scene.get("strategy")!=original["strategy"] or
                scene.get("original_ltx_sha256")!=original["source_sha256"] or
                scene.get("selected_media_sha256")!=original["candidate_sha256"] or
                clip.get("video")!=original["candidate_path"] or
                clip.get("sha256")!=original["candidate_sha256"] or
                scene.get("applied_face_cleanup")!=clip.get("face_cleanup") or
                scene.get("publication_approved") is not False or
                scene.get("requires_new_scene_provenance_review") is not True):
                raise RecoveryAdmissionError("M60 staged scene SHA/provenance changed.")
            reused=scene["strategy"]=="REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
            if (scene["strategy"] not in (
                    "REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS",
                    "USE_ORIGINAL_APPROVED_LTX_SOURCE") or
                scene.get("full_m7_decode_confirmed") is not reused or
                clip["face_cleanup"]!=("none" if reused else
                                        original["source_face_cleanup"])):
                raise RecoveryAdmissionError("M60 recovered source/face policy changed.")
        with self.queue._connection(write=True) as db:
            if not _table(db,"studio_recovery_reservations"):
                raise RecoveryAdmissionError("M60 reservation schema missing.")
            try:
                checked=_verify(db,proposal,proposal_file_sha)
            except (RecoveryIntakeError,sqlite3.Error,ValueError,KeyError) as exc:
                raise RecoveryAdmissionError("M60 original Pi scene status changed.") from exc
            intent=db.execute("""SELECT * FROM studio_recovery_intents
                WHERE proposal_id=?""",(pid,)).fetchone()
            media=db.execute("""SELECT * FROM studio_recovery_media_contracts
                WHERE proposal_id=?""",(pid,)).fetchone()
            bound=db.execute("""SELECT * FROM studio_recovery_execution_recipes
                WHERE proposal_id=?""",(pid,)).fetchone()
            if (not intent or not media or not bound or
                intent["state"]!="M57_RECONCILIATION_REQUIRED_NO_QUEUE" or
                intent["proposal_sha256"]!=checked["proposal_sha256"] or
                intent["envelope_file_sha256"]!=proposal_file_sha or
                intent["original_plan_sha256"]!=checked["original_plan_sha256"] or
                intent["scene_set_sha256"]!=checked["scene_set_sha256"] or
                intent["source_catalogue_sha256"]!=checked["source_catalogue_sha256"] or
                media["state"]!="M58_MEDIA_BOUND_REQUIRES_FRESH_EXECUTION_CONTRACT" or
                media["contract_sha256"]!=bound["source_media_contract_sha256"] or
                bound["state"]!="M59_NONEXECUTABLE_RECIPE_BOUND" or
                bound["derived_recipe_sha256"]!=recipe_sha256 or
                bound["execution_manifest_sha256"]!=outer["manifest_sha256"] or
                bound["manifest_file_sha256"]!=manifest_sha256 or
                bound["recipe_id"]!="recovery_"+pid or
                m.get("new_recipe_id")!=bound["recipe_id"] or
                m.get("source_m58_contract_sha256")!=media["contract_sha256"] or
                m.get("source_m58_file_sha256")!=media["contract_file_sha256"] or
                db.execute("""SELECT 1 FROM studio_recovery_reservations
                    WHERE proposal_id=?""",(pid,)).fetchone()):
                raise RecoveryAdmissionError("M60 chained Pi M57–M59 contract changed or replayed.")
            # Never reuse the failed job ID or any previously issued queue ID.
            fresh=uuid4().hex
            if (fresh==proposal["original_job_id"] or
                db.execute("SELECT 1 FROM jobs WHERE job_id=?",
                           (fresh,)).fetchone()):
                raise RecoveryAdmissionError("M60 reserved job identity collision.")
            # Source copied-file SHA checks are still narrow TOCTOU fences;
            # M61 MUST check Mac-side exact bytes before FFmpeg.
            if (hashlib.sha256(Path(proposal_file).read_bytes()).hexdigest()
                    !=proposal_file_sha or
                hashlib.sha256(Path(recipe_file).read_bytes()).hexdigest()
                    !=recipe_sha256 or
                hashlib.sha256(Path(manifest_file).read_bytes()).hexdigest()
                    !=manifest_sha256):
                raise RecoveryAdmissionError("M60 staged files changed during reservation.")
            db.execute("""INSERT INTO studio_recovery_reservations VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?)""",(
                pid,fresh,proposal["original_job_id"],
                checked["original_plan_sha256"],checked["scene_set_sha256"],
                checked["source_catalogue_sha256"],
                proposal["original_script_sha256"],recipe_sha256,
                outer["manifest_sha256"],media["contract_sha256"],
                STATE,self.queue.clock()))
            self.queue._event(db,proposal["original_job_id"],
                "M60_RECOVERY_JOB_ID_RESERVED_NO_DISPATCH",{
                    "proposal_id":pid,"recipe_sha256":recipe_sha256})
        return {
            "status":STATE,"proposal_id":pid,
            "reserved_job_id":fresh,
            "job_inserted_in_queue":False,
            "worker_claimable":False,
            "mac_bytes_verified_by_pi":False,
            "auto_execute_allowed":False,
            "public_release_authorized":False,
        }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-recovery-admission")
    p.add_argument("--db",required=True)
    p.add_argument("--initialize",action="store_true")
    p.add_argument("--proposal",type=Path)
    p.add_argument("--proposal-sha256")
    p.add_argument("--recipe",type=Path)
    p.add_argument("--recipe-sha256")
    p.add_argument("--manifest",type=Path)
    p.add_argument("--manifest-sha256")
    args=p.parse_args(argv)
    try:
        worker=RecoveryAdmission(StudioQueue(args.db))
        if args.initialize and not any((args.proposal,args.recipe,args.manifest)):
            worker.initialize()
            out={"status":"M60_RESERVATION_SCHEMA_READY_NO_JOB"}
        elif (not args.initialize and args.proposal and args.proposal_sha256
              and args.recipe and args.recipe_sha256
              and args.manifest and args.manifest_sha256):
            out=worker.reserve(
                proposal_file=args.proposal,
                proposal_sha256=args.proposal_sha256,
                recipe_file=args.recipe,recipe_sha256=args.recipe_sha256,
                manifest_file=args.manifest,manifest_sha256=args.manifest_sha256)
        else:
            raise RecoveryAdmissionError("M60 initialize or pin exact copies.")
        print(json.dumps(out,ensure_ascii=False,sort_keys=True))
        return 0
    except (RecoveryAdmissionError,OSError,ValueError,sqlite3.Error,TypeError):
        print("M60_RECOVERY_ADMISSION_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
