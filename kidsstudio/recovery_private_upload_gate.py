"""M63: isolated Pi recovery PRIVATE-upload lease and verified preview ledger.

No PUBLIC operation, no modification to the ordinary M26 uploader or to the
original BLOCKED episode. Owner M26 standing policy, M62 independent review,
original scene receipts and final M61 master SHA are rechecked on every gate.
Never auto-retry a possibly delivered YouTube upload.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from .recovery_final_qa import RecoveryFinalQA, READY as AI_READY, STAGED
from .recovery_lease import RecoveryLeaseError
from .studio_queue import StudioQueue, SAFE_KEY
from .youtube_private_upload import CHANNEL, VIDEO

PID=re.compile(r"^[a-f0-9]{32}$")
SHA=re.compile(r"^[a-f0-9]{64}$")
CAPABILITY="recovery_private_upload"
READY="M63_PRIVATE_UPLOAD_READY_ONE_SHOT"
LEASED="M63_PRIVATE_UPLOAD_LEASED"
PENDING="M63_YOUTUBE_PRIVATE_PROCESSING_PENDING"
VERIFIED="M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING"
FAILED="M63_PRIVATE_UPLOAD_RECONCILIATION_REQUIRED_NO_RETRY"


class RecoveryUploadError(ValueError):
    pass


class RecoveryPrivateUploadGate:
    def __init__(self,queue:StudioQueue):
        self.queue=queue

    def initialize(self)->None:
        with self.queue._connection(write=True) as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                name='studio_recovery_private_handoffs' AND type='table'""").fetchone():
                raise RecoveryUploadError("Initialize M62 before M63.")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_uploads(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_private_handoffs(proposal_id),
                recovery_job_id TEXT NOT NULL UNIQUE,
                master_sha256 TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                policy_revision INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(state IN (
                    'M63_PRIVATE_UPLOAD_READY_ONE_SHOT',
                    'M63_PRIVATE_UPLOAD_LEASED',
                    'M63_YOUTUBE_PRIVATE_PROCESSING_PENDING',
                    'M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING',
                    'M63_PRIVATE_UPLOAD_RECONCILIATION_REQUIRED_NO_RETRY')),
                worker_id TEXT,
                generation INTEGER NOT NULL DEFAULT 0,
                lease_expires REAL,
                video_id TEXT UNIQUE,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_owner_feedback(
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id TEXT NOT NULL REFERENCES
                    studio_recovery_uploads(proposal_id),
                category TEXT NOT NULL,
                second INTEGER,
                note TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('COMMENT','DECISION')),
                decision TEXT,
                created_at REAL NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_owner_decisions(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_uploads(proposal_id),
                video_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL CHECK(state IN (
                    'APPROVED','APPROVED_WITH_NOTES','REVISION_REQUESTED')),
                note TEXT NOT NULL,
                reviewed_at REAL NOT NULL
            )""")

    def _source(self,db:sqlite3.Connection,pid:str)->dict[str,Any]:
        if not isinstance(pid,str) or not PID.fullmatch(pid):
            raise RecoveryUploadError("M63 exact proposal required.")
        try:
            lease,pins=RecoveryFinalQA(self.queue)._source(db,pid)
        except (ValueError,sqlite3.Error,OSError,KeyError) as exc:
            raise RecoveryUploadError("M63 current M61 scene/plan not eligible.") from exc
        qa=db.execute("""SELECT * FROM studio_recovery_final_qa
            WHERE proposal_id=?""",(pid,)).fetchone()
        handoff=db.execute("""SELECT * FROM studio_recovery_private_handoffs
            WHERE proposal_id=?""",(pid,)).fetchone()
        metadata=db.execute("""SELECT i.series_id,i.ordinal,e.state episode_state,
            s.state series_state FROM studio_recovery_intents i
            JOIN studio_episodes e ON (e.series_id=i.series_id AND e.ordinal=i.ordinal)
            JOIN studio_series s ON s.series_id=i.series_id
            WHERE i.proposal_id=?""",(pid,)).fetchone()
        policy=(db.execute("""SELECT * FROM studio_youtube_private_policies
            WHERE series_id=?""",(metadata["series_id"],)).fetchone()
            if metadata else None)
        paused=db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()
        if (not lease or not qa or not handoff or not metadata or not policy or
            not paused or paused["paused"] or
            metadata["series_state"]!="ACTIVE" or
            metadata["episode_state"]!="BLOCKED" or
            qa["state"]!=AI_READY or handoff["state"]!=STAGED or
            qa["recovery_job_id"]!=lease["reserved_job_id"] or
            handoff["recovery_job_id"]!=lease["reserved_job_id"] or
            qa["master_sha256"]!=lease["result_sha256"] or
            handoff["master_sha256"]!=lease["result_sha256"] or
            qa["script_sha256"]!=pins["script_sha256"] or
            qa["review_bundle_sha256"]!=handoff["review_bundle_sha256"] or
            policy["state"]!="ENABLED" or
            policy["revision"]!=handoff["policy_revision"] or
            policy["channel_id"]!=handoff["channel_id"] or
            bool(policy["allowed_made_for_kids"])!=
                bool(handoff["made_for_kids"]) or
            bool(policy["allowed_synthetic_media"])!=
                bool(handoff["contains_synthetic_media"])):
            raise RecoveryUploadError("M63 current owner policy/AI/private handoff revoked.")
        return {
            "proposal_id":pid,"job_id":lease["reserved_job_id"],
            "series_id":metadata["series_id"],
            "episode_number":metadata["ordinal"],
            "original_job_id":pins["original_job_id"],
            "master_sha256":lease["result_sha256"],
            "script_sha256":pins["script_sha256"],
            "review_bundle_sha256":qa["review_bundle_sha256"],
            "tech_report_sha256":qa["tech_report_sha256"],
            "channel_id":handoff["channel_id"],
            "policy_revision":handoff["policy_revision"],
            "made_for_kids":bool(handoff["made_for_kids"]),
            "contains_synthetic_media":bool(handoff["contains_synthetic_media"]),
        }

    def _audit(self,db,pid,event):
        original=db.execute("""SELECT original_job_id FROM
            studio_recovery_reservations WHERE proposal_id=?""",(pid,)).fetchone()
        if original:self.queue._event(db,original["original_job_id"],event,
                                       {"proposal_id":pid})

    def activate(self,proposal_id:str)->dict:
        """Pi-local owner-policy activation; remote worker cannot self-enable."""
        with self.queue._connection(write=True) as db:
            proof=self._source(db,proposal_id)
            if db.execute("""SELECT 1 FROM studio_recovery_uploads
                    WHERE proposal_id=? OR recovery_job_id=?""",
                    (proposal_id,proof["job_id"])).fetchone():
                raise RecoveryUploadError("M63 private upload already activated.")
            # A standing policy budget applies to BOTH ordinary and recovered
            # uploads and cannot be bypassed by moving to a new job namespace.
            policy=db.execute("""SELECT max_uploads_24h FROM
                studio_youtube_private_policies WHERE series_id=?""",
                (proof["series_id"],)).fetchone()
            count=db.execute("""SELECT COUNT(*) FROM jobs WHERE
                kind='youtube_private_upload' AND created_at>=?
                AND json_extract(payload,'$.series_id')=?""",
                (self.queue.clock()-86400,proof["series_id"])).fetchone()[0]
            count+=db.execute("""SELECT COUNT(*) FROM studio_recovery_uploads u
                JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                WHERE i.series_id=? AND u.created_at>=?""",
                (proof["series_id"],self.queue.clock()-86400)).fetchone()[0]
            if count>=policy["max_uploads_24h"]:
                raise RecoveryUploadError("M63 owner daily private budget exhausted.")
            in_flight=db.execute("""SELECT 1 FROM studio_recovery_uploads u
                JOIN studio_recovery_intents i ON i.proposal_id=u.proposal_id
                WHERE i.series_id=? AND u.state IN (?,?)""",
                (proof["series_id"],READY,LEASED)).fetchone()
            ordinary=db.execute("""SELECT 1 FROM jobs WHERE
                kind='youtube_private_upload' AND state IN ('QUEUED','LEASED')
                AND json_extract(payload,'$.series_id')=?""",
                (proof["series_id"],)).fetchone()
            if in_flight or ordinary:
                raise RecoveryUploadError("M63 only one outstanding private upload per series.")
            now=self.queue.clock()
            db.execute("""INSERT INTO studio_recovery_uploads(
                proposal_id,recovery_job_id,master_sha256,channel_id,
                policy_revision,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""",(
                proposal_id,proof["job_id"],proof["master_sha256"],
                proof["channel_id"],proof["policy_revision"],
                READY,now,now))
            self._audit(db,proposal_id,"M63_PRIVATE_UPLOAD_READY_NO_NETWORK")
        return {"status":READY,"proposal_id":proposal_id,
                "youtube_upload_performed":False,
                "public_release_authorized":False}

    def _revoke(self,db,row,reason):
        db.execute("""UPDATE studio_recovery_uploads
            SET state=?,worker_id=NULL,lease_expires=NULL,updated_at=?
            WHERE proposal_id=? AND state IN (?,?)""",
            (FAILED,self.queue.clock(),row["proposal_id"],READY,LEASED))
        self._audit(db,row["proposal_id"],reason)

    def claim(self,*,proposal_id:str,worker_id:str,capability:str,
              lease_seconds:int=120)->dict|None:
        if (capability!=CAPABILITY or
            not isinstance(worker_id,str) or not SAFE_KEY.fullmatch(worker_id) or
            type(lease_seconds) is not int or not 30<=lease_seconds<=3600):
            raise RecoveryUploadError("M63 explicit scoped uploader lease required.")
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT * FROM studio_recovery_uploads
                WHERE proposal_id=?""",(proposal_id,)).fetchone()
            if not row or row["state"]!=READY:return None
            try:proof=self._source(db,proposal_id)
            except RecoveryUploadError:
                self._revoke(db,row,"M63_PRIVATE_CLAIM_SOURCE_REVOKED")
                return None
            db.execute("""UPDATE studio_recovery_uploads SET
                state=?,worker_id=?,generation=generation+1,
                lease_expires=?,updated_at=? WHERE proposal_id=?""",
                (LEASED,worker_id,self.queue.clock()+lease_seconds,
                 self.queue.clock(),proposal_id))
            self._audit(db,proposal_id,"M63_PRIVATE_UPLOAD_CLAIMED")
            return {**proof,"kind":CAPABILITY,
                    "generation":row["generation"]+1,
                    "public_release_authorized":False}

    def _current(self,db,job_id,worker_id,generation):
        if (not isinstance(job_id,str) or not PID.fullmatch(job_id) or
            not isinstance(worker_id,str) or not SAFE_KEY.fullmatch(worker_id) or
            type(generation) is not int or generation!=1):
            raise RecoveryUploadError("M63 exact lease identity required.")
        row=db.execute("""SELECT * FROM studio_recovery_uploads
            WHERE recovery_job_id=?""",(job_id,)).fetchone()
        if not row or row["state"]!=LEASED or row["worker_id"]!=worker_id or row["generation"]!=generation:
            raise RecoveryUploadError("M63 lease revoked, replayed, or wrong worker.")
        if row["lease_expires"] is None or row["lease_expires"]<=self.queue.clock():
            self._revoke(db,row,"M63_PRIVATE_LEASE_EXPIRED_NO_RETRY")
            return None
        return row

    def check(self,*,job_id:str,worker_id:str,generation:int,
              renew:bool=False)->dict:
        with self.queue._connection(write=True) as db:
            row=self._current(db,job_id,worker_id,generation)
            if row is None:return {"status":"M63_REVOKED_NO_UPLOAD"}
            try:proof=self._source(db,row["proposal_id"])
            except RecoveryUploadError:
                self._revoke(db,row,"M63_PRIVATE_POLICY_REVOKED_NO_RETRY")
                return {"status":"M63_REVOKED_NO_UPLOAD"}
            if (proof["master_sha256"]!=row["master_sha256"] or
                proof["channel_id"]!=row["channel_id"] or
                proof["policy_revision"]!=row["policy_revision"]):
                self._revoke(db,row,"M63_PRIVATE_UPLOAD_PINS_CHANGED")
                return {"status":"M63_REVOKED_NO_UPLOAD"}
            if renew:
                db.execute("""UPDATE studio_recovery_uploads
                    SET lease_expires=?,updated_at=? WHERE proposal_id=?""",
                    (self.queue.clock()+120,self.queue.clock(),
                     row["proposal_id"]))
            return {**proof,"status":"M63_CURRENT_PRIVATE_UPLOAD_LEASE",
                    "generation":generation,
                    "visibility":"private",
                    "public_release_authorized":False}

    def complete(self,*,job_id:str,worker_id:str,generation:int,
                 receipt:dict)->dict:
        required={"status","video_id","channel_id","video_sha256",
                  "youtube_privacy","processing_status",
                  "platform_privacy_verified","ready_for_owner_review",
                  "public_release_authorized"}
        if (not isinstance(receipt,dict) or set(receipt)!=required or
            receipt["status"] not in (
                "YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
                "YOUTUBE_PRIVATE_PROCESSING_PENDING") or
            not isinstance(receipt["video_id"],str) or
            not VIDEO.fullmatch(receipt["video_id"]) or
            receipt["youtube_privacy"]!="private" or
            receipt["platform_privacy_verified"] is not True or
            receipt["public_release_authorized"] is not False or
            receipt["ready_for_owner_review"] is not (
                receipt["status"]=="YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING")):
            raise RecoveryUploadError("M63 verified YouTube PRIVATE-only receipt required.")
        with self.queue._connection(write=True) as db:
            row=self._current(db,job_id,worker_id,generation)
            if row is None:return {"status":FAILED}
            proof=self._source(db,row["proposal_id"])
            if (receipt["channel_id"]!=proof["channel_id"] or
                receipt["video_sha256"]!=proof["master_sha256"] or
                (receipt["status"]=="YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING"
                 and receipt["processing_status"]!="succeeded")):
                raise RecoveryUploadError("M63 video/channel/processing is not current.")
            stage=(VERIFIED if receipt["ready_for_owner_review"] else PENDING)
            db.execute("""UPDATE studio_recovery_uploads SET
                state=?,worker_id=NULL,lease_expires=NULL,video_id=?,updated_at=?
                WHERE proposal_id=?""",(
                stage,receipt["video_id"],self.queue.clock(),row["proposal_id"]))
            self._audit(db,row["proposal_id"],
                "M63_YOUTUBE_PRIVATE_VERIFIED" if stage==VERIFIED
                else "M63_PRIVATE_PROCESSING_PENDING")
            return {"status":stage,"video_id":receipt["video_id"],
                    "owner_review_available":stage==VERIFIED,
                    "public_release_authorized":False}

    def reconcile_processing(self,*,proposal_id:str,receipt:dict)->dict:
        """One existing YouTube ID, no new videos.insert; local owner action."""
        with self.queue._connection(write=True) as db:
            row=db.execute("""SELECT * FROM studio_recovery_uploads WHERE
                proposal_id=?""",(proposal_id,)).fetchone()
            proof=self._source(db,proposal_id)
            if (not row or row["state"]!=PENDING or
                not isinstance(receipt,dict) or
                set(receipt)!={"video_id","channel_id","video_sha256",
                             "youtube_privacy","processing_status",
                             "platform_privacy_verified",
                             "public_release_authorized"} or
                receipt["video_id"]!=row["video_id"] or
                receipt["channel_id"]!=proof["channel_id"] or
                receipt["video_sha256"]!=proof["master_sha256"] or
                receipt["youtube_privacy"]!="private" or
                receipt["processing_status"]!="succeeded" or
                receipt["platform_privacy_verified"] is not True or
                receipt["public_release_authorized"] is not False):
                raise RecoveryUploadError("M63 existing processing upload not verified.")
            db.execute("""UPDATE studio_recovery_uploads SET
                state=?,updated_at=? WHERE proposal_id=?""",
                (VERIFIED,self.queue.clock(),proposal_id))
            self._audit(db,proposal_id,"M63_PRIVATE_EXISTING_VIDEO_VERIFIED")
            return {"status":VERIFIED,"video_id":row["video_id"],
                    "public_release_authorized":False}

    def fail(self,*,job_id:str,worker_id:str,generation:int)->dict:
        with self.queue._connection(write=True) as db:
            row=self._current(db,job_id,worker_id,generation)
            if row is not None:self._revoke(
                db,row,"M63_YOUTUBE_UNCERTAIN_RESULT_NO_AUTO_RETRY")
            return {"status":FAILED,"retry_allowed":False,
                    "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    """Pi-local schema/activation only. Remote workers cannot activate."""
    import argparse,json,sys
    p=argparse.ArgumentParser(prog="studio-recovery-private-upload")
    p.add_argument("--db",required=True)
    grp=p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--initialize",action="store_true")
    grp.add_argument("--activate",action="store_true")
    p.add_argument("--proposal-id")
    args=p.parse_args(argv)
    try:
        gate=RecoveryPrivateUploadGate(StudioQueue(args.db))
        if args.initialize and args.proposal_id is None:
            gate.initialize()
            result={"status":"M63_PRIVATE_UPLOAD_SCHEMA_READY_NO_PERMISSION"}
        elif args.activate and args.proposal_id:
            result=gate.activate(args.proposal_id)
        else:
            raise RecoveryUploadError("Pi-local explicit activation required.")
        print(json.dumps(result,sort_keys=True))
        return 0
    except (RecoveryUploadError,sqlite3.Error,OSError,ValueError):
        print("M63_PRIVATE_UPLOAD_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
