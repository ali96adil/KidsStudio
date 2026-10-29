"""M57 Pi-side immutable recovery-intent intake, no queue or actuation.

Receives a copied M56 private proposal as UNTRUSTED metadata, checks exact
source/scene lineage using Pi SQLite records in one write transaction, then
pins a distinct internal attempt identity. This is NOT permission to execute
a new montage, to reuse recovered bytes, or to replace M14/M49 contracts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

from .studio_queue import StudioQueue
from .studio_scenes import assert_scenes_ready, SceneError
from .series_manager import scene_script_fingerprint

SHA=re.compile(r"^[0-9a-f]{64}$")
JOB=re.compile(r"^[0-9a-f]{32}$")
MAX_BYTES=160_000
FROZEN_FLAGS=(
    "requires_new_catalogue_and_scene_provenance",
    "requires_new_pi_authorized_job_and_lease",
    "requires_new_final_m7_full_decode_and_quality_reviews",
    "owner_private_preview_required",
)
FORBIDDEN_FLAGS=(
    "auto_retry_allowed","auto_execute_allowed","auto_reuse_allowed",
    "public_release_authorized",
)
ALLOWED_STATUS="M56_FRESH_ATTEMPT_PROPOSED_NOT_QUEUED"


class RecoveryIntakeError(ValueError):
    """Proposed recovery would break Pi/M32 scene/queue lineage."""


def _sha_json(value:Any)->str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def _private_envelope(filename:str|Path, claimed_sha256:str)->tuple[dict,str]:
    src=Path(filename).expanduser()
    if (not src.is_absolute() or src.is_symlink() or
        not isinstance(claimed_sha256,str) or not SHA.fullmatch(claimed_sha256)):
        raise RecoveryIntakeError("Exact private non-symlink M56 envelope SHA required.")
    file=src.resolve()
    if (not file.is_file() or not 0<file.stat().st_size<=MAX_BYTES or
        any((p/".git").exists() for p in (file.parent,*file.parents))):
        raise RecoveryIntakeError("M56 envelope not a bounded private JSON file.")
    data=file.read_bytes()
    digest=hashlib.sha256(data).hexdigest()
    if digest!=claimed_sha256:
        raise RecoveryIntakeError("Transferred M56 envelope SHA mismatch.")
    try:
        envelope=json.loads(data)
    except (UnicodeError,ValueError) as exc:
        raise RecoveryIntakeError("M56 envelope not valid JSON.") from exc
    if (not isinstance(envelope,dict) or
        set(envelope)!={"schema_version","proposal","proposal_sha256"} or
        envelope["schema_version"]!=1 or
        not isinstance(envelope["proposal"],dict) or
        not isinstance(envelope["proposal_sha256"],str) or
        not SHA.fullmatch(envelope["proposal_sha256"]) or
        _sha_json(envelope["proposal"])!=envelope["proposal_sha256"]):
        raise RecoveryIntakeError("M56 immutable proposal hash/shape mismatch.")
    return envelope["proposal"],digest


def _table(db:sqlite3.Connection,name:str)->bool:
    return bool(db.execute("""SELECT 1 FROM sqlite_master
        WHERE type='table' AND name=?""",(name,)).fetchone())


def _verify(db:sqlite3.Connection,p:dict,hash_of_file:str)->dict:
    expected={
        "schema_version","status","proposal_id","original_job_id",
        "original_request_sha256","frozen_inspection_sha256",
        "original_assembly_recipe_sha256","original_script_sha256",
        "series_id","episode_number","scene_count","scenes",
        "verified_normalized_candidates","original_scene_fallback_count",
        "proposed_pi_job_id","source_catalogue_sha256",
        *FROZEN_FLAGS,*FORBIDDEN_FLAGS,
    }
    if (set(p)!=expected or p["schema_version"]!=1 or
        p["status"]!=ALLOWED_STATUS or
        not isinstance(p["proposal_id"],str) or not JOB.fullmatch(p["proposal_id"])
        or not isinstance(p["original_job_id"],str) or
        not JOB.fullmatch(p["original_job_id"]) or
        p["proposal_id"]==p["original_job_id"] or
        any(not isinstance(p[field],str) or not SHA.fullmatch(p[field])
            for field in ("original_request_sha256",
                          "frozen_inspection_sha256",
                          "original_assembly_recipe_sha256",
                          "original_script_sha256")) or
        not isinstance(p["series_id"],str) or
        type(p["episode_number"]) is not int or
        not 1<=p["episode_number"]<=120 or
        type(p["scene_count"]) is not int or
        not 2<=p["scene_count"]<=40 or
        not isinstance(p["scenes"],list) or
        len(p["scenes"])!=p["scene_count"] or
        type(p["verified_normalized_candidates"]) is not int or
        type(p["original_scene_fallback_count"]) is not int or
        p["verified_normalized_candidates"]<0 or
        p["verified_normalized_candidates"]+
            p["original_scene_fallback_count"]!=p["scene_count"] or
        p["proposed_pi_job_id"] is not None or
        any(p[field] is not True for field in FROZEN_FLAGS) or
        any(p[field] is not False for field in FORBIDDEN_FLAGS)):
        raise RecoveryIntakeError("M57 proposed attempt is not a non-actuating M56 plan.")
    catalogue=p["source_catalogue_sha256"]
    if not isinstance(catalogue,str) or not SHA.fullmatch(catalogue):
        raise RecoveryIntakeError("M57 original M49 catalogue SHA required.")
    sid,num=p["series_id"],p["episode_number"]
    for table in ("studio_episodes","studio_series","studio_orchestrator_plans",
                  "studio_orchestrator_render_contracts",
                  "studio_orchestrator_assembly_bindings",
                  "studio_scene_plans","studio_scenes","studio_scene_stages"):
        if not _table(db,table):
            raise RecoveryIntakeError("M57 complete M32/M49 schema required.")
    paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
    episode=db.execute("""SELECT e.state,e.source_sha256,e.render_job_id,
        e.render_attempt,s.state AS series_state
        FROM studio_episodes e JOIN studio_series s
        ON e.series_id=s.series_id WHERE e.series_id=? AND e.ordinal=?""",
        (sid,num)).fetchone()
    old=db.execute("SELECT * FROM jobs WHERE job_id=?",
                   (p["original_job_id"],)).fetchone()
    pinned=db.execute("""SELECT * FROM studio_orchestrator_plans
        WHERE series_id=? AND ordinal=?""",(sid,num)).fetchone()
    contract=db.execute("""SELECT * FROM studio_orchestrator_render_contracts
        WHERE series_id=? AND ordinal=?""",(sid,num)).fetchone()
    binding=db.execute("""SELECT * FROM studio_orchestrator_assembly_bindings
        WHERE series_id=? AND ordinal=?""",(sid,num)).fetchone()
    scene_plan=db.execute("""SELECT plan_sha256,episode_script_sha256
        FROM studio_scene_plans WHERE series_id=? AND ordinal=?""",
        (sid,num)).fetchone()
    if (not paused or paused["paused"] or
        not episode or episode["state"]!="BLOCKED" or
        episode["series_state"]!="ACTIVE" or
        episode["render_job_id"]!=p["original_job_id"] or
        episode["source_sha256"]!=p["original_script_sha256"] or
        not old or old["kind"]!="episode_assemble" or
        old["state"] not in ("FAILED","CANCELLED") or
        not pinned or pinned["script_sha256"]!=p["original_script_sha256"] or
        not contract or contract["plan_sha256"]!=pinned["plan_sha256"] or
        not binding or binding["plan_sha256"]!=pinned["plan_sha256"] or
        binding["catalogue_sha256"]!=catalogue or
        not scene_plan or
        scene_plan["plan_sha256"]!=pinned["scene_plan_sha256"] or
        scene_plan["episode_script_sha256"]!=p["original_script_sha256"] or
        contract["recipe_id"] is None):
        raise RecoveryIntakeError("M57 original failed episode/M32/M49 lineage changed.")
    if contract["catalogue_marker"] not in ("AFTER_SCENE_QA",catalogue):
        raise RecoveryIntakeError("M57 original M51 catalogue policy changed.")
    try:
        old_payload=json.loads(old["payload"])
    except (TypeError,ValueError) as exc:
        raise RecoveryIntakeError("M57 original Pi job payload invalid.") from exc
    if (not isinstance(old_payload,dict) or
        old_payload!={"recipe_id":contract["recipe_id"],
                      "script_sha256":p["original_script_sha256"],
                      "catalogue_sha256":catalogue} or
        _sha_json({"kind":"episode_assemble","payload":old_payload})!=
            p["original_request_sha256"] or
        old["request_key"]!=
            (f"series:{sid}:episode:{num}:"
             f"render:episode_assemble:a{episode['render_attempt']}:"
             f"{p['original_script_sha256'][:16]}")):
        raise RecoveryIntakeError("M57 proposed source job is not exact Pi render.")
    try:
        ready=assert_scenes_ready(db,sid,num,p["original_script_sha256"])
    except (SceneError,sqlite3.Error) as exc:
        raise RecoveryIntakeError("M57 current scene QA receipts no longer match.") from exc
    rows=db.execute("""SELECT scene,script_sha256 FROM studio_scenes
        WHERE series_id=? AND ordinal=? ORDER BY scene""",(sid,num)).fetchall()
    if (len(ready)!=p["scene_count"] or
        scene_script_fingerprint(rows)!=contract["scene_scripts_sha256"] or
        _sha_json(ready)!=binding["scene_set_sha256"]):
        raise RecoveryIntakeError("M57 immutable M49 scene-set changed.")
    recovered=0
    expected_scene_keys={
        "scene","strategy","source_sha256","source_face_cleanup",
        "candidate_path","candidate_sha256",
        "candidate_technical_status",
        "requires_new_scene_provenance_review",
        "candidate_approved_for_publication",
    }
    for idx,(candidate,approved) in enumerate(zip(p["scenes"],ready),1):
        if (not isinstance(candidate,dict) or
            set(candidate)!=expected_scene_keys or
            type(candidate["scene"]) is not int or
            candidate["scene"]!=idx or
            candidate["source_sha256"]!=approved["ltx_sha256"] or
            not isinstance(candidate["candidate_sha256"],str) or
            not SHA.fullmatch(candidate["candidate_sha256"]) or
            not isinstance(candidate["candidate_path"],str) or
            not candidate["candidate_path"].startswith("/") or
            len(candidate["candidate_path"])>4096 or
            candidate["source_face_cleanup"] not in ("none","bunny_v07") or
            candidate["requires_new_scene_provenance_review"] is not True or
            candidate["candidate_approved_for_publication"] is not False):
            raise RecoveryIntakeError("M57 source scenes are not current approved LTX.")
        if candidate["strategy"]=="REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS":
            if candidate["candidate_technical_status"]!="M7_TECH_PASS_NOT_FINAL_QA":
                raise RecoveryIntakeError("M57 recovered candidate missing M7 claim.")
            recovered+=1
        elif candidate["strategy"]=="USE_ORIGINAL_APPROVED_LTX_SOURCE":
            if (candidate["candidate_sha256"]!=approved["ltx_sha256"] or
                candidate["candidate_technical_status"] not in
                    ("NOT_REUSED","RECOVERED_CANDIDATE_FAILED_M7_USE_ORIGINAL")):
                raise RecoveryIntakeError("M57 original LTX fallback SHA changed.")
        else:
            raise RecoveryIntakeError("M57 unrecognized scene recovery operation.")
    if recovered!=p["verified_normalized_candidates"]:
        raise RecoveryIntakeError("M57 recovery/fallback totals changed.")
    return {
        "series_id":sid,"ordinal":num,
        "proposal_id":p["proposal_id"],
        "original_job_id":p["original_job_id"],
        "proposal_sha256":_sha_json(p),
        "envelope_file_sha256":hash_of_file,
        "original_plan_sha256":pinned["plan_sha256"],
        "scene_set_sha256":binding["scene_set_sha256"],
        "source_catalogue_sha256":catalogue,
        "recovered_candidates":recovered,
        "fallbacks":p["original_scene_fallback_count"],
    }


class RecoveryIntake:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_intents(
                proposal_id TEXT PRIMARY KEY,
                series_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
                original_job_id TEXT NOT NULL UNIQUE,
                proposal_sha256 TEXT NOT NULL UNIQUE,
                envelope_file_sha256 TEXT NOT NULL,
                original_plan_sha256 TEXT NOT NULL,
                scene_set_sha256 TEXT NOT NULL,
                source_catalogue_sha256 TEXT NOT NULL,
                recovered_candidates INTEGER NOT NULL,
                fallbacks INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(
                    state='M57_RECONCILIATION_REQUIRED_NO_QUEUE'),
                created_at REAL NOT NULL,
                FOREIGN KEY(series_id,ordinal)
                REFERENCES studio_episodes(series_id,ordinal)
            )""")

    def pin(self,filename:str|Path,*,sha256:str)->dict[str,Any]:
        proposal,outer=_private_envelope(filename,sha256)
        with self.queue._connection(write=True) as db:
            if not _table(db,"studio_recovery_intents"):
                raise RecoveryIntakeError("M57 intake schema not initialized.")
            checked=_verify(db,proposal,outer)
            if (db.execute("""SELECT 1 FROM studio_recovery_intents WHERE
                original_job_id=? OR proposal_id=?""",
                (checked["original_job_id"],checked["proposal_id"])).fetchone()):
                raise RecoveryIntakeError("M57 recovery intent already pinned.")
            # Recheck externally copied bytes under the lock to catch a
            # source-file race between read and the new immutable DB row.
            if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=outer:
                raise RecoveryIntakeError("M57 envelope changed while pinning.")
            db.execute("""INSERT INTO studio_recovery_intents VALUES(
                ?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                checked["proposal_id"],checked["series_id"],checked["ordinal"],
                checked["original_job_id"],checked["proposal_sha256"],
                checked["envelope_file_sha256"],checked["original_plan_sha256"],
                checked["scene_set_sha256"],checked["source_catalogue_sha256"],
                checked["recovered_candidates"],checked["fallbacks"],
                "M57_RECONCILIATION_REQUIRED_NO_QUEUE",
                self.queue.clock()))
            self.queue._event(db,checked["original_job_id"],
                "M57_PRIVATE_RECOVERY_INTENT_PINNED",
                {"proposal_sha256":checked["proposal_sha256"],
                 "candidate_count":checked["recovered_candidates"]})
        return {"status":"M57_PRIVATE_RECOVERY_INTENT_PINNED_NO_JOB_QUEUED",
                "proposal_id":checked["proposal_id"],
                "original_job_id":checked["original_job_id"],
                "recovered_candidates":checked["recovered_candidates"],
                "fallbacks":checked["fallbacks"],
                "new_pi_job_id":None,
                "mac_media_verified_by_pi":False,
                "auto_execute_allowed":False,"public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="studio-recovery-intake")
    parser.add_argument("--db",required=True)
    parser.add_argument("--initialize",action="store_true")
    parser.add_argument("--proposal",type=Path)
    parser.add_argument("--sha256")
    args=parser.parse_args(argv)
    try:
        intake=RecoveryIntake(StudioQueue(args.db))
        if args.initialize and args.proposal is None and args.sha256 is None:
            intake.initialize()
            out={"status":"M57_SCHEMA_INITIALIZED_NO_JOB_QUEUED"}
        elif not args.initialize and args.proposal and args.sha256:
            out=intake.pin(args.proposal,sha256=args.sha256)
        else:
            raise RecoveryIntakeError("Initialize or pin exact copied proposal.")
        print(json.dumps(out,ensure_ascii=False,sort_keys=True))
        return 0
    except (RecoveryIntakeError,OSError,sqlite3.Error,ValueError,TypeError):
        print("M57_RECOVERY_INTAKE_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
