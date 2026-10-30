"""M65: Pi local master inbox for ordinary APPROVED episodes (M25/M26).

Shares the private LAN root with M64 recovery jobs but NEVER imports
recovery media as an ordinary approved episode. Pi checks actual M8
readiness, MP4 SHA, episode current M26 provenance and owner policy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3

from .studio_queue import StudioQueue
from .private_upload_policy import PrivateUploadPolicy,PrivatePolicyError
from .pi_media_inbox import _safe_root,InboxError
from .youtube_private_upload import (
    validate_plan,YouTubePrivateError,file_sha256,MAX_BYTES,CHANNEL,JOB
)

READY="M65_PI_ORDINARY_MEDIA_VERIFIED_PRIVATE_ONLY"


class OrdinaryInboxError(ValueError):
    pass


class PiOrdinaryInbox:
    def __init__(self,queue:StudioQueue,root:str|Path):
        self.queue=queue
        self.root=_safe_root(Path(root))

    def initialize(self):
        if not self.root.is_dir() or self.root.is_symlink():
            raise OrdinaryInboxError("Initialize Pi M64 persistent root first.")
        with self.queue._connection(write=True) as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                name='studio_youtube_private_policies' AND type='table'""").fetchone():
                raise OrdinaryInboxError("M26 owner policy is required.")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_pi_ordinary_media(
                render_job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                series_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                master_sha256 TEXT NOT NULL UNIQUE,
                master_bytes INTEGER NOT NULL,
                plan_sha256 TEXT NOT NULL,
                readiness_sha256 TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                policy_revision INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(
                    state='M65_PI_ORDINARY_MEDIA_VERIFIED_PRIVATE_ONLY'),
                created_at REAL NOT NULL
            )""")

    def _dir(self,job_id:str)->Path:
        if not isinstance(job_id,str) or not JOB.fullmatch(job_id):
            raise OrdinaryInboxError("M65 current original render job required.")
        dest=self.root/job_id
        if dest.is_symlink():raise OrdinaryInboxError("Pi ordinary folder symlink.")
        return dest

    def _policy(self,db,job_id:str,plan:dict|None=None):
        row=db.execute("""SELECT series_id,ordinal FROM studio_episodes
            WHERE render_job_id=? AND state='EPISODE_APPROVED'""",
            (job_id,)).fetchone()
        if not row:raise OrdinaryInboxError("M65 original approved episode missing.")
        current=db.execute("""SELECT kind,state,result_json FROM jobs
            WHERE job_id=?""",(job_id,)).fetchone()
        try:result=json.loads(current["result_json"]) if current else {}
        except (ValueError,TypeError):result={}
        master=result.get("artifact_sha256")
        if not isinstance(master,str) or not re.fullmatch(r"[0-9a-f]{64}",master):
            raise OrdinaryInboxError("M65 completed original render receipt absent.")
        try:
            PrivateUploadPolicy._approved(db,row["series_id"],row["ordinal"],
                                          job_id,master)
        except (PrivatePolicyError,sqlite3.Error) as exc:
            raise OrdinaryInboxError("M65 original M7/AI owner QA revoked.") from exc
        policy=db.execute("""SELECT * FROM studio_youtube_private_policies
            WHERE series_id=?""",(row["series_id"],)).fetchone()
        if not policy or policy["state"]!="ENABLED":
            raise OrdinaryInboxError("M65 approved owner channel unavailable.")
        if plan is not None and (
            plan["series_id"]!=row["series_id"] or
            plan["episode_number"]!=row["ordinal"] or
            plan["render_job_id"]!=job_id or
            plan["master_sha256"]!=master or
            plan["target_channel_id"]!=policy["channel_id"] or
            plan["made_for_kids"] is not bool(policy["allowed_made_for_kids"]) or
            plan["contains_synthetic_media"] is not
                 bool(policy["allowed_synthetic_media"])):
            raise OrdinaryInboxError("M65 original approved media/channel changed.")
        return row,policy,master

    def prepare(self,render_job_id:str)->dict:
        with self.queue._connection(write=True) as db:
            self._policy(db,render_job_id)
            if db.execute("""SELECT 1 FROM studio_pi_ordinary_media
                WHERE render_job_id=?""",(render_job_id,)).fetchone():
                raise OrdinaryInboxError("M65 ordinary source already accepted.")
            target=self._dir(render_job_id)
            if target.exists():
                if target.is_symlink() or not target.is_dir():
                    raise OrdinaryInboxError("Pi staged ordinary folder invalid.")
            else:target.mkdir(mode=0o700)
            os.chmod(target,0o700)
        return {"status":"M65_PI_ORDINARY_STAGE_READY_NO_UPLOAD",
                "render_job_id":render_job_id,
                "youtube_uploaded":False}

    def _files(self,job_id:str,partial:bool):
        dest=self._dir(job_id)
        suffix=".part" if partial else ""
        return (
            dest/("episode_qa_master.mp4"+suffix),
            dest/("private_upload_plan.json"+suffix),
            dest/("m8_readiness.json"+suffix),
        )

    @staticmethod
    def _file(path:Path,*,min_bytes:int,max_bytes:int):
        if (path.is_symlink() or not path.is_file() or
            not min_bytes<=path.stat().st_size<=max_bytes or
            path.stat().st_nlink!=1):
            raise OrdinaryInboxError("M65 staged Pi file incomplete or unsafe.")

    def accept(self,job_id:str)->dict:
        with self.queue._connection(write=True) as db:
            if db.execute("""SELECT 1 FROM studio_pi_ordinary_media
                WHERE render_job_id=?""",(job_id,)).fetchone():
                raise OrdinaryInboxError("M65 original media cannot be overwritten.")
            src,meta,ready=self._files(job_id,True)
            final,final_meta,final_ready=self._files(job_id,False)
            if any(x.exists() or x.is_symlink()
                   for x in (final,final_meta,final_ready)):
                raise OrdinaryInboxError("M65 finalized files already exist.")
            self._file(src,min_bytes=1000,max_bytes=MAX_BYTES)
            self._file(meta,min_bytes=20,max_bytes=15_000)
            self._file(ready,min_bytes=20,max_bytes=30_000)
            try:plan=json.loads(meta.read_bytes())
            except (OSError,ValueError) as exc:
                raise OrdinaryInboxError("M65 original plan JSON invalid.") from exc
            if not isinstance(plan,dict):
                raise OrdinaryInboxError("M65 original plan required.")
            report_sha=file_sha256(ready)
            try:
                validated=validate_plan(plan,src,ready,report_sha,
                                        allow_partial=True)
            except (YouTubePrivateError,KeyError,ValueError) as exc:
                raise OrdinaryInboxError("M65 M8 + final master validation failed.") from exc
            original,policy,master=self._policy(db,job_id,plan)
            if validated["master_sha256"]!=master:
                raise OrdinaryInboxError("M65 Pi master SHA differs.")
            plan_sha=file_sha256(meta)
            for path in (src,meta,ready):
                with path.open("rb") as stream:os.fsync(stream.fileno())
            for start,end in ((src,final),(meta,final_meta),
                              (ready,final_ready)):
                os.replace(start,end)
                os.chmod(end,0o400)
            root=self._dir(job_id)
            catalog=root/"private_catalogue.json"
            document={
                "schema_version":1,"private_root":str(self.root),
                "entries":[{"plan":str(final_meta),
                            "media":str(final),
                            "readiness":str(final_ready),
                            "readiness_sha256":report_sha}]
            }
            fd=os.open(catalog,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o400)
            with os.fdopen(fd,"w") as stream:
                stream.write(json.dumps(document,sort_keys=True)+"\n")
                stream.flush();os.fsync(stream.fileno())
            with os.fdopen(os.open(root,os.O_RDONLY|os.O_DIRECTORY)) as dfd:
                os.fsync(dfd.fileno())
            db.execute("""INSERT INTO studio_pi_ordinary_media
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
                job_id,original["series_id"],original["ordinal"],
                master,final.stat().st_size,plan_sha,report_sha,
                policy["channel_id"],policy["revision"],
                READY,self.queue.clock()))
            self.queue._event(db,job_id,
                "M65_PI_ORDINARY_SHA_VALIDATED_NO_UPLOAD",{})
        return {"status":READY,"render_job_id":job_id,
                "master_sha256":master,
                "mac_required_for_upload":False,
                "youtube_uploaded":False,
                "public_release_authorized":False}

    def verify(self,job_id:str,*,full_sha:bool=False)->dict:
        with self.queue._connection() as db:
            row=db.execute("""SELECT * FROM studio_pi_ordinary_media
                WHERE render_job_id=?""",(job_id,)).fetchone()
            if not row or row["state"]!=READY:
                raise OrdinaryInboxError("M65 Pi ordinary media not yet accepted.")
            media,plan_file,readiness=self._files(job_id,False)
            for path,minimum,maximum in (
                (media,1000,MAX_BYTES),(plan_file,20,15_000),
                (readiness,20,30_000)):
                self._file(path,min_bytes=minimum,max_bytes=maximum)
            try:plan=json.loads(plan_file.read_bytes())
            except (OSError,ValueError) as exc:
                raise OrdinaryInboxError("M65 original plan unreadable.") from exc
            original,policy,master=self._policy(db,job_id,plan)
            if (master!=row["master_sha256"] or
                policy["revision"]!=row["policy_revision"] or
                media.stat().st_size!=row["master_bytes"] or
                file_sha256(plan_file)!=row["plan_sha256"] or
                file_sha256(readiness)!=row["readiness_sha256"] or
                (full_sha and file_sha256(media)!=master)):
                raise OrdinaryInboxError("M65 accepted Pi media or owner policy changed.")
            return {"status":READY,"job_id":job_id,
                    "master_sha256":master,
                    "catalogue":self._dir(job_id)/"private_catalogue.json",
                    "media":media}
