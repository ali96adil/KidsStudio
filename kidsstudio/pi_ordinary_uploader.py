"""M65: run the existing M26 ordinary PRIVATE upload flow ON PI, not Mac.

Pi-only persistent original MP4, M8, M25 plan, independent Pi SHA and
one-shot UploadJournal. Refresh Google OAuth access tokens from the Pi.
Never use a Mac network client for YouTube or loosen M26 source policy.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .studio_queue import StudioQueue
from .private_upload_policy import PrivateUploadPolicy,PrivatePolicyError
from .private_upload_agent import (
    PrivateCatalogue,PrivateUploadAgent,PrivateAgentError
)
from .pi_ordinary_inbox import PiOrdinaryInbox,OrdinaryInboxError
from .pi_recovery_uploader import GoogleOAuthRefresh
from .youtube_private_upload import UploadJournal,GoogleYouTubeTransport


class OrdinaryPiUploaderError(ValueError):
    pass


class PiOrdinaryLocalClient:
    """M26 endpoint-equivalent local Pi actions, with targeted atomic claim."""
    def __init__(self,queue:StudioQueue,inbox:PiOrdinaryInbox,
                 render_job_id:str,worker_id:str="pi-ordinary-uploader"):
        self.queue=queue
        self.inbox=inbox
        self.render_job_id=render_job_id
        self.worker_id=worker_id
        self.policy=PrivateUploadPolicy(queue)

    def call(self,action:str,body:dict)->dict:
        if action=="request-private-upload":
            if (body.get("render_job_id")!=self.render_job_id or
                set(body)!={"series_id","episode_number","render_job_id",
                             "master_sha256","plan_sha256","readiness_sha256",
                             "channel_id","made_for_kids",
                             "contains_synthetic_media"}):
                raise OrdinaryPiUploaderError("M65 request differs from accepted Pi media.")
            current=self.inbox.verify(self.render_job_id,full_sha=True)
            if body["master_sha256"]!=current["master_sha256"]:
                raise OrdinaryPiUploaderError("M65 original master SHA mismatch.")
            return self.policy.enqueue_private(
                body["series_id"],body["episode_number"],
                render_job_id=self.render_job_id,
                master_sha256=body["master_sha256"],
                plan_sha256=body["plan_sha256"],
                readiness_sha256=body["readiness_sha256"],
                channel_id=body["channel_id"],
                made_for_kids=body["made_for_kids"],
                contains_synthetic_media=body["contains_synthetic_media"])
        if action=="claim":
            if body:raise OrdinaryPiUploaderError("M65 claim accepts no paths.")
            self.inbox.verify(self.render_job_id,full_sha=True)
            with self.queue._connection(write=True) as db:
                now=self.queue.clock()
                if db.execute("SELECT paused FROM settings WHERE slot=1").fetchone()[0]:
                    return {"job":None}
                # Claim only the exact accepted original episode. Never
                # accidentally claim another queued M26 upload and fail it.
                row=db.execute("""SELECT * FROM jobs
                    WHERE kind='youtube_private_upload' AND state='QUEUED'
                    AND json_extract(payload,'$.render_job_id')=?
                    AND available_at<=?
                    ORDER BY created_at LIMIT 1""",
                    (self.render_job_id,now)).fetchone()
                if row is None:return {"job":None}
                if row["attempts"]>=row["max_attempts"]:
                    raise OrdinaryPiUploaderError("M65 exhausted one-shot upload.")
                try:
                    metadata=json.loads(row["payload"])
                except ValueError as exc:
                    raise OrdinaryPiUploaderError("M65 Pi queue payload malformed.") from exc
                if metadata.get("render_job_id")!=self.render_job_id:
                    raise OrdinaryPiUploaderError("M65 exact job selection failed.")
                db.execute("""UPDATE jobs SET state='LEASED',worker_id=?,
                    attempts=attempts+1,generation=generation+1,
                    lease_expires=?,updated_at=? WHERE job_id=? AND state='QUEUED'""",
                    (self.worker_id,now+600,now,row["job_id"]))
                self.queue._event(db,row["job_id"],"CLAIMED",
                    {"worker":self.worker_id,"attempt":row["attempts"]+1})
                return {"job":{"kind":"youtube_private_upload",
                    "job_id":row["job_id"],
                    "generation":row["generation"]+1,
                    "payload":metadata}}
        if action in ("private-upload-lease-check","heartbeat",
                      "complete-private-upload","fail"):
            if action=="private-upload-lease-check":
                if set(body)!={"job_id","generation","payload"}:
                    raise OrdinaryPiUploaderError("M65 Pi lease proof invalid.")
                self.inbox.verify(self.render_job_id,full_sha=False)
                return self.policy.check_lease(
                    body["job_id"],body["generation"],self.worker_id,
                    body["payload"])
            if action=="heartbeat":
                if set(body)!={"job_id","generation"}:
                    raise OrdinaryPiUploaderError("M65 Pi heartbeat invalid.")
                self.inbox.verify(self.render_job_id,full_sha=False)
                row=self.queue.heartbeat(
                    job_id=body["job_id"],worker_id=self.worker_id,
                    generation=body["generation"],lease_seconds=600)
                return {"ok":row["state"]=="LEASED"}
            if action=="complete-private-upload":
                if set(body)!={"job_id","generation","result"}:
                    raise OrdinaryPiUploaderError("M65 Pi completion malformed.")
                self.inbox.verify(self.render_job_id,full_sha=True)
                return self.policy.complete(
                    body["job_id"],body["generation"],self.worker_id,
                    body["result"])
            if action=="fail":
                if set(body)!={"job_id","generation","error_code"}:
                    raise OrdinaryPiUploaderError("M65 Pi failure malformed.")
                result=self.queue.fail(
                    job_id=body["job_id"],worker_id=self.worker_id,
                    generation=body["generation"],
                    error_code=body["error_code"])
                return {"status":result["state"]}
        raise OrdinaryPiUploaderError("M65 unrecognized ordinary Pi upload action.")


class PiOrdinaryUploadService:
    def __init__(self,queue:StudioQueue,inbox:PiOrdinaryInbox,
                 oauth:GoogleOAuthRefresh,*,journal:UploadJournal,
                 transport:Any|None=None):
        self.queue=queue
        self.inbox=inbox
        self.oauth=oauth
        self.journal=journal
        self.transport=transport or GoogleYouTubeTransport()

    def poll_once(self)->dict:
        with self.queue._connection() as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                name='studio_pi_ordinary_media' AND type='table'""").fetchone():
                raise OrdinaryPiUploaderError("M65 inbox schema missing.")
            jobs=db.execute("""SELECT DISTINCT e.render_job_id
                FROM studio_episodes e JOIN studio_series s
                  ON s.series_id=e.series_id
                WHERE e.state='EPISODE_APPROVED' AND s.state='ACTIVE'
                AND e.render_job_id IS NOT NULL
                ORDER BY e.render_job_id LIMIT 30""").fetchall()
        for item in jobs:
            job=item["render_job_id"]
            try:
                try:self.inbox.verify(job,full_sha=True)
                except (OrdinaryInboxError,ValueError,OSError):
                    try:
                        self.inbox.prepare(job)
                        self.inbox.accept(job)
                    except (OrdinaryInboxError,ValueError,OSError,
                            sqlite3.Error):
                        continue
                current=self.inbox.verify(job,full_sha=True)
                if self.journal.status(job):
                    # A previous M25 STARTED is irreversible without
                    # explicit reconciliation; never enqueue/reupload.
                    continue
                # The Pi refreshes Google credentials before admission.
                token=self.oauth.token()
                catalogue=PrivateCatalogue(current["catalogue"])
                local=PiOrdinaryLocalClient(self.queue,self.inbox,job)
                worker=PrivateUploadAgent(
                    local,catalogue,self.journal,token,
                    transport=self.transport,token_provider=self.oauth.token)
                result=worker.run_once()
                return {**result,"uploader_device":"RASPBERRY_PI",
                        "mac_required_for_upload":False,
                        "public_release_authorized":False}
            except (OrdinaryInboxError,PrivatePolicyError,
                    OrdinaryPiUploaderError,PrivateAgentError,
                    ValueError,OSError,sqlite3.Error):
                continue
        return {"status":"M65_PI_ORDINARY_UPLOAD_IDLE",
                "mac_required_for_upload":False,
                "public_release_authorized":False}
