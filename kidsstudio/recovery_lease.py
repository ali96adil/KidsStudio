"""M61 separate one-shot Pi recovery lease; never enters ordinary queue.

Only local privileged activation may promote an M60 reservation. Dedicated
recovery_assemble capability never alters M52-M54 ordinary montage guards.
Every claim/pre-execution/heartbeat checks the ORIGINAL M32/M49/M51 source
receipts; expired or revoked work is terminal, never automatically retried.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any

from .studio_queue import StudioQueue, SAFE_KEY
from .recovery_intake import _private_envelope, _verify, _table, RecoveryIntakeError

PID=re.compile(r"^[0-9a-f]{32}$")
SHA=re.compile(r"^[0-9a-f]{64}$")
CAPABILITY="recovery_assemble"
READY="M61_READY_PRIVATE_RECOVERY"
LEASED="M61_LEASED_PRIVATE_RECOVERY"
DONE="M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW"
FAILED="M61_FAILED_REQUIRES_MANUAL_RECONCILIATION"
STATES=(READY,LEASED,DONE,FAILED)


class RecoveryLeaseError(ValueError):
    """Recovery job not eligible for a current, exclusive Pi lease."""


class RecoveryLeaseGate:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            if not _table(db,"studio_recovery_reservations"):
                raise RecoveryLeaseError("M60 reservation must be initialized first.")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_leases(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_reservations(proposal_id),
                reserved_job_id TEXT NOT NULL UNIQUE,
                proposal_file TEXT NOT NULL,
                proposal_file_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN (
                    'M61_READY_PRIVATE_RECOVERY',
                    'M61_LEASED_PRIVATE_RECOVERY',
                    'M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW',
                    'M61_FAILED_REQUIRES_MANUAL_RECONCILIATION')),
                worker_id TEXT,
                generation INTEGER NOT NULL DEFAULT 0,
                lease_expires REAL,
                result_sha256 TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")

    def _guard(self,db:sqlite3.Connection,row:sqlite3.Row)->dict[str,Any]:
        """Always check exact frozen Pi proposal and the current source QA."""
        p=Path(row["proposal_file"])
        if (p.is_symlink() or not p.is_absolute() or
            not p.is_file() or
            hashlib.sha256(p.read_bytes()).hexdigest()!=
                row["proposal_file_sha256"]):
            raise RecoveryLeaseError("Recovery proposal changed or went missing.")
        try:
            proposal,raw_sha=_private_envelope(p,row["proposal_file_sha256"])
            state=_verify(db,proposal,raw_sha)
        except (RecoveryIntakeError,OSError,sqlite3.Error,ValueError,
                KeyError,TypeError) as exc:
            raise RecoveryLeaseError("Current Pi scene/original job QA revoked.") from exc
        res=db.execute("""SELECT * FROM studio_recovery_reservations
            WHERE proposal_id=?""",(row["proposal_id"],)).fetchone()
        intent=db.execute("""SELECT * FROM studio_recovery_intents
            WHERE proposal_id=?""",(row["proposal_id"],)).fetchone()
        media=db.execute("""SELECT * FROM studio_recovery_media_contracts
            WHERE proposal_id=?""",(row["proposal_id"],)).fetchone()
        recipe=db.execute("""SELECT * FROM studio_recovery_execution_recipes
            WHERE proposal_id=?""",(row["proposal_id"],)).fetchone()
        if (not res or not intent or not media or not recipe or
            res["state"]!="M60_RECOVERY_JOB_RESERVED_NOT_DISPATCHABLE" or
            res["reserved_job_id"]!=row["reserved_job_id"] or
            res["original_job_id"]!=proposal["original_job_id"] or
            res["original_script_sha256"]!=proposal["original_script_sha256"] or
            res["original_plan_sha256"]!=state["original_plan_sha256"] or
            res["original_scene_set_sha256"]!=state["scene_set_sha256"] or
            res["original_catalogue_sha256"]!=state["source_catalogue_sha256"] or
            intent["proposal_sha256"]!=state["proposal_sha256"] or
            intent["envelope_file_sha256"]!=raw_sha or
            media["contract_sha256"]!=res["media_contract_sha256"] or
            recipe["derived_recipe_sha256"]!=res["fresh_recipe_sha256"] or
            recipe["execution_manifest_sha256"]!=res["fresh_manifest_sha256"] or
            recipe["source_media_contract_sha256"]!=res["media_contract_sha256"] or
            recipe["state"]!="M59_NONEXECUTABLE_RECIPE_BOUND"):
            raise RecoveryLeaseError("M61 chained recovery reservation changed.")
        return {"proposal_id":row["proposal_id"],
                "job_id":row["reserved_job_id"],
                "original_job_id":proposal["original_job_id"],
                "recipe_sha256":res["fresh_recipe_sha256"],
                "manifest_sha256":res["fresh_manifest_sha256"],
                "media_contract_sha256":res["media_contract_sha256"],
                "script_sha256":res["original_script_sha256"]}

    def _revoke(self,db:sqlite3.Connection,row:sqlite3.Row,reason:str)->None:
        db.execute("""UPDATE studio_recovery_leases SET state=?,
            worker_id=NULL,lease_expires=NULL,updated_at=?
            WHERE proposal_id=? AND state IN (?,?)""",
            (FAILED,self.queue.clock(),row["proposal_id"],READY,LEASED))
        source=db.execute("""SELECT original_job_id FROM
            studio_recovery_reservations WHERE proposal_id=?""",
            (row["proposal_id"],)).fetchone()
        self.queue._event(db,source["original_job_id"] if source else None,
                          "M61_RECOVERY_REVOKED",{"reason":reason})

    def activate(self,proposal_file:str|Path,*,sha256:str)->dict:
        """Explicit local Pi admission; no ordinary queue entry is created."""
        p=Path(proposal_file).expanduser()
        if not p.is_absolute() or p.is_symlink():
            raise RecoveryLeaseError("M61 requires private absolute Pi proposal.")
        try:
            proposal,digest=_private_envelope(p,sha256)
        except (RecoveryIntakeError,OSError,ValueError) as exc:
            raise RecoveryLeaseError("M61 copied proposal invalid.") from exc
        with self.queue._connection(write=True) as db:
            if not _table(db,"studio_recovery_leases"):
                raise RecoveryLeaseError("M61 schema not initialized.")
            paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            if not paused or paused["paused"]:
                raise RecoveryLeaseError("Studio paused.")
            res=db.execute("""SELECT * FROM studio_recovery_reservations
                WHERE proposal_id=?""",(proposal["proposal_id"],)).fetchone()
            if (not res or
                db.execute("""SELECT 1 FROM studio_recovery_leases
                    WHERE proposal_id=?""",(proposal["proposal_id"],)).fetchone()):
                raise RecoveryLeaseError("M61 reservation absent or activated before.")
            # Validate ALL current pins inside same write transaction.
            transient={"proposal_id":proposal["proposal_id"],
                       "proposal_file":str(p),
                       "proposal_file_sha256":digest,
                       "reserved_job_id":res["reserved_job_id"]}
            self._guard(db,transient)
            now=self.queue.clock()
            db.execute("""INSERT INTO studio_recovery_leases(
                proposal_id,reserved_job_id,proposal_file,
                proposal_file_sha256,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)""",
                (proposal["proposal_id"],res["reserved_job_id"],
                 str(p),digest,READY,now,now))
            self.queue._event(db,res["original_job_id"],
                "M61_RECOVERY_ACTIVATED_PRIVATE_NO_QUEUE",
                {"proposal_id":proposal["proposal_id"]})
        return {"status":READY,"job_id":res["reserved_job_id"],
                "ordinary_queue_job":False,"public_release_authorized":False}

    def claim(self,*,worker_id:str,capability:str,
              proposal_id:str,lease_seconds:int=120)->dict|None:
        if (not isinstance(worker_id,str) or not SAFE_KEY.fullmatch(worker_id)
            or capability!=CAPABILITY or type(lease_seconds) is not int or
            not 10<=lease_seconds<=3600 or
            not isinstance(proposal_id,str) or not PID.fullmatch(proposal_id)):
            raise RecoveryLeaseError("Dedicated M61 capability and bounded lease required.")
        with self.queue._connection(write=True) as db:
            paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            if not paused or paused["paused"]:
                return None
            now=self.queue.clock()
            # Fail-closed when any previous Mac start is ambiguous. Never
            # requeue an expired recovery lease or replay the same job.
            for row in db.execute("""SELECT * FROM studio_recovery_leases
                    WHERE state=? AND lease_expires<=?""",(LEASED,now)).fetchall():
                self._revoke(db,row,"M61_LEASE_EXPIRED_NO_AUTO_RETRY")
            row=db.execute("""SELECT * FROM studio_recovery_leases
                WHERE state=? AND proposal_id=? LIMIT 1""",
                (READY,proposal_id)).fetchone()
            if row is None:return None
            try:
                attested=self._guard(db,row)
            except RecoveryLeaseError:
                self._revoke(db,row,"M61_CLAIM_SOURCE_QA_REVOKED")
                return None
            until=now+lease_seconds
            db.execute("""UPDATE studio_recovery_leases SET
                state=?,worker_id=?,generation=generation+1,
                lease_expires=?,updated_at=?
                WHERE proposal_id=? AND state=?""",
                (LEASED,worker_id,until,now,row["proposal_id"],READY))
            self.queue._event(db,attested["original_job_id"],
                "M61_RECOVERY_LEASE_CLAIMED",
                {"generation":row["generation"]+1})
            return {**attested,"kind":CAPABILITY,
                    "generation":row["generation"]+1,
                    "lease_expires":until}

    def _current(self,db,*,job_id:str,worker_id:str,generation:int):
        if (not isinstance(job_id,str) or not PID.fullmatch(job_id) or
            not isinstance(worker_id,str) or not SAFE_KEY.fullmatch(worker_id)
            or type(generation) is not int or generation!=1):
            raise RecoveryLeaseError("M61 exact one-shot lease identity required.")
        row=db.execute("""SELECT * FROM studio_recovery_leases
            WHERE reserved_job_id=?""",(job_id,)).fetchone()
        if (not row or row["state"]!=LEASED or
            row["worker_id"]!=worker_id or row["generation"]!=generation):
            raise RecoveryLeaseError("M61 missing, replayed or revoked lease.")
        if row["lease_expires"] is None or row["lease_expires"]<=self.queue.clock():
            self._revoke(db,row,"M61_LEASE_EXPIRED_NO_AUTO_RETRY")
            return None
        return row

    def check(self,*,job_id:str,worker_id:str,generation:int,
              renew:bool=False,lease_seconds:int=120)->dict:
        if type(renew) is not bool or type(lease_seconds) is not int or not 10<=lease_seconds<=3600:
            raise RecoveryLeaseError("M61 bounded lease renewal required.")
        with self.queue._connection(write=True) as db:
            row=self._current(db,job_id=job_id,worker_id=worker_id,
                              generation=generation)
            if row is None:return {"status":"M61_REVOKED_NO_EXECUTION"}
            paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            try:
                if not paused or paused["paused"]:
                    raise RecoveryLeaseError("M61_STUDIO_PAUSED")
                proof=self._guard(db,row)
            except RecoveryLeaseError:
                self._revoke(db,row,"M61_CURRENT_RECOVERY_QA_REVOKED")
                return {"status":"M61_REVOKED_NO_EXECUTION"}
            if renew:
                db.execute("""UPDATE studio_recovery_leases SET
                    lease_expires=?,updated_at=?
                    WHERE proposal_id=?""",
                    (self.queue.clock()+lease_seconds,self.queue.clock(),
                     row["proposal_id"]))
            return {**proof,"status":"M61_CURRENT_PRIVATE_RECOVERY_LEASE",
                    "generation":generation,
                    "render_started":False,
                    "public_release_authorized":False}

    def complete(self,*,job_id:str,worker_id:str,generation:int,
                 result:dict)->dict:
        expected={"status","artifact_sha256","artifact_bytes",
                  "final_m7_full_decode_passed","publication_approved"}
        if (not isinstance(result,dict) or set(result)!=expected or
            result["status"]!="M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW" or
            not isinstance(result["artifact_sha256"],str) or
            not SHA.fullmatch(result["artifact_sha256"]) or
            type(result["artifact_bytes"]) is not int or
            not 0<result["artifact_bytes"]<=2_000_000_000 or
            result["final_m7_full_decode_passed"] is not True or
            result["publication_approved"] is not False):
            raise RecoveryLeaseError("M61 full M7 technical receipt required.")
        with self.queue._connection(write=True) as db:
            row=self._current(db,job_id=job_id,worker_id=worker_id,
                              generation=generation)
            if row is None:return {"status":"M61_REVOKED_NO_COMPLETION"}
            paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
            try:
                if not paused or paused["paused"]:
                    raise RecoveryLeaseError("M61_STUDIO_PAUSED")
                self._guard(db,row)
            except RecoveryLeaseError:
                self._revoke(db,row,"M61_COMPLETION_SOURCE_REVOKED")
                return {"status":"M61_REVOKED_NO_COMPLETION"}
            now=self.queue.clock()
            db.execute("""UPDATE studio_recovery_leases SET state=?,
                worker_id=NULL,lease_expires=NULL,result_sha256=?,
                updated_at=? WHERE proposal_id=?""",
                (DONE,result["artifact_sha256"],now,row["proposal_id"]))
            original=db.execute("""SELECT original_job_id FROM
                studio_recovery_reservations WHERE proposal_id=?""",
                (row["proposal_id"],)).fetchone()
            self.queue._event(db,original["original_job_id"],
                "M61_MASTER_TECH_PENDING_FINAL_REVIEW",
                              {"artifact_sha256":result["artifact_sha256"]})
            return {"status":DONE,"job_id":job_id,
                    "owner_private_review_required":True,
                    "public_release_authorized":False}

    def fail(self,*,job_id:str,worker_id:str,generation:int)->dict:
        with self.queue._connection(write=True) as db:
            row=self._current(db,job_id=job_id,worker_id=worker_id,
                              generation=generation)
            if row is not None:self._revoke(db,row,"M61_MAC_RECONCILIATION_REQUIRED")
            return {"status":FAILED,"retry_allowed":False}


