"""M63 Mac one-shot recovered-video uploader; separate from ordinary M25/M26.

A scoped Pi recovery_private_upload lease and M62 QA are rechecked directly
before the FIRST Google videos.insert call. Uses M25's hardened transport and
durable UploadJournal but never forges an ordinary M8 readiness report.
No retry after unknown network outcomes. No public/schedule API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
from typing import Any,Callable

from .episode_assembly import _ensure_private
from .remote_worker import RemoteClient,RemoteWorkerError
from .youtube_private_upload import (
    UploadJournal,GoogleYouTubeTransport,YouTubePrivateError,
    file_sha256,CHUNK,CHANNEL,VIDEO,MAX_BYTES,
)

PID=re.compile(r"^[a-f0-9]{32}$")
SHA=re.compile(r"^[a-f0-9]{64}$")
FIELDS={"schema_version","series_id","episode_number","proposal_id",
        "recovery_job_id","master_sha256","target_channel_id",
        "title","description","category_id","made_for_kids",
        "contains_synthetic_media"}


class RecoveryPrivateUploaderError(ValueError):
    pass


def _plan(path:Path,*,allow_partial:bool=False)->tuple[dict,str]:
    p=Path(path).expanduser()
    if (not p.is_absolute() or p.is_symlink() or
        not (p.name.endswith(".json") or
             allow_partial and p.name.endswith(".json.part")) or
        not p.is_file() or
        not 0<p.stat().st_size<=15_000):
        raise RecoveryPrivateUploaderError("M63 private upload plan unavailable.")
    _ensure_private(p.parent)
    try:doc=json.loads(p.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError) as exc:
        raise RecoveryPrivateUploaderError("M63 private metadata malformed.") from exc
    if (not isinstance(doc,dict) or set(doc)!=FIELDS or
        doc["schema_version"]!=1 or
        not isinstance(doc["series_id"],str) or
        not re.fullmatch(r"[a-z][a-z0-9_-]{1,47}",doc["series_id"]) or
        type(doc["episode_number"]) is not int or
        not 1<=doc["episode_number"]<=120 or
        any(not isinstance(doc[x],str) or not PID.fullmatch(doc[x])
            for x in ("proposal_id","recovery_job_id")) or
        doc["proposal_id"]==doc["recovery_job_id"] or
        not isinstance(doc["master_sha256"],str) or
        not SHA.fullmatch(doc["master_sha256"]) or
        not isinstance(doc["target_channel_id"],str) or
        not CHANNEL.fullmatch(doc["target_channel_id"]) or
        not isinstance(doc["title"],str) or
        not 1<=len(doc["title"].strip())<=100 or
        not isinstance(doc["description"],str) or
        len(doc["description"])>4800 or
        not isinstance(doc["category_id"],str) or
        not re.fullmatch(r"[0-9]{1,3}",doc["category_id"]) or
        type(doc["made_for_kids"]) is not bool or
        type(doc["contains_synthetic_media"]) is not bool):
        raise RecoveryPrivateUploaderError("M63 exact owner video metadata required.")
    return doc,file_sha256(p)


class RecoveryPrivateUploader:
    def __init__(self,pi:Any, *,plan_file:Path,media_file:Path,
                 journal:UploadJournal,token:str,transport:Any|None=None,
                 heartbeat_seconds:float=15.0,
                 token_provider:Callable[[],str]|None=None):
        self.plan,self.plan_sha=_plan(plan_file)
        path=Path(media_file).expanduser()
        if (not path.is_absolute() or path.is_symlink() or
            path.name!="episode_qa_master.mp4" or
            path.parent.name!=self.plan["recovery_job_id"]):
            raise RecoveryPrivateUploaderError("M63 exact new M61 master path required.")
        path=path.resolve()
        _ensure_private(path.parent)
        if (not path.is_file() or
            not 1000<=path.stat().st_size<=MAX_BYTES or
            file_sha256(path)!=self.plan["master_sha256"]):
            raise RecoveryPrivateUploaderError("M63 local final master SHA/bytes changed.")
        if (not isinstance(token,str) or len(token)<30 or
            any(ch.isspace() for ch in token)):
            raise RecoveryPrivateUploaderError("M63 private YouTube OAuth token required.")
        if (type(heartbeat_seconds) not in (int,float) or
            not .05<=heartbeat_seconds<=60):
            raise RecoveryPrivateUploaderError("M63 invalid heartbeat period.")
        self.pi=pi
        self.media=path
        self.journal=journal
        self.token=token
        self.token_provider=token_provider
        self.original_stat=(path.stat().st_size,path.stat().st_mtime_ns,
                            path.stat().st_ino)
        self.transport=transport or GoogleYouTubeTransport()
        self.heartbeat_seconds=heartbeat_seconds

    def _oauth(self)->str:
        value=self.token_provider() if self.token_provider else self.token
        if (not isinstance(value,str) or len(value)<30 or
            any(ch.isspace() for ch in value)):
            raise RecoveryPrivateUploaderError("M64 Pi OAuth token unavailable.")
        return value

    def _media_unchanged(self,*,full_sha:bool=False)->None:
        current=(self.media.stat().st_size,self.media.stat().st_mtime_ns,
                 self.media.stat().st_ino)
        if (current!=self.original_stat or self.media.is_symlink() or
            (full_sha and file_sha256(self.media)!=self.plan["master_sha256"])):
            raise RecoveryPrivateUploaderError("M64 approved Pi media changed.")

    def _proof(self,result:dict,job:str,generation:int)->None:
        p=self.plan
        if (not isinstance(result,dict) or
            result.get("status")!="M63_CURRENT_PRIVATE_UPLOAD_LEASE" or
            result.get("job_id")!=job or
            result.get("generation")!=generation or
            result.get("proposal_id")!=p["proposal_id"] or
            result.get("master_sha256")!=p["master_sha256"] or
            result.get("channel_id")!=p["target_channel_id"] or
            result.get("series_id")!=p["series_id"] or
            result.get("episode_number")!=p["episode_number"] or
            result.get("made_for_kids") is not p["made_for_kids"] or
            result.get("contains_synthetic_media") is not p["contains_synthetic_media"] or
            result.get("visibility")!="private" or
            result.get("public_release_authorized") is not False):
            raise RecoveryPrivateUploaderError("M63 Pi standing policy/lease source mismatch.")

    def run_once(self)->dict:
        p=self.plan
        response=self.pi.call("recovery-private-claim",
                              {"proposal_id":p["proposal_id"]})
        claim=response.get("job")
        if claim is None:return {"status":"M63_NO_PRIVATE_UPLOAD_READY"}
        job,generation=claim.get("job_id"),claim.get("generation")
        if (claim.get("kind")!="recovery_private_upload" or
            job!=p["recovery_job_id"] or type(generation) is not int or
            generation!=1 or claim.get("master_sha256")!=p["master_sha256"] or
            claim.get("channel_id")!=p["target_channel_id"] or
            claim.get("proposal_id")!=p["proposal_id"] or
            claim.get("public_release_authorized") is not False):
            raise RecoveryPrivateUploaderError("M63 claim not exact current master.")
        params={"job_id":job,"generation":generation}
        failed=False
        def fail():
            nonlocal failed
            if failed:return
            failed=True
            try:self.pi.call("recovery-private-fail",params)
            except (RemoteWorkerError,OSError,ValueError):pass
        stop=threading.Event()
        aborted=threading.Event()
        def pulse():
            while not stop.wait(self.heartbeat_seconds):
                try:
                    result=self.pi.call("recovery-private-heartbeat",params)
                    if result.get("ok") is not True:raise RecoveryPrivateUploaderError("lease lost")
                except Exception:
                    aborted.set();return
        def check(*,full_sha:bool=False):
            if aborted.is_set():raise RecoveryPrivateUploaderError("M64 Pi lease lost.")
            proof=self.pi.call("recovery-private-check",params)
            self._proof(proof,job,generation)
            # M64: avoid re-hashing multi-GB media on EVERY 8MiB chunk.
            # Rehash at the trust boundaries and use stat guards during upload.
            self._media_unchanged(full_sha=full_sha)
        try:
            # Pre-reservation local proof: cannot call Google unless Pi is
            # current and the existing Mac upload journal has no attempt.
            check(full_sha=True)
            self.journal.reserve(job,p["master_sha256"],self.plan_sha)
        except (RecoveryPrivateUploaderError,YouTubePrivateError,
                RemoteWorkerError,OSError,ValueError):
            fail()
            return {"status":"M63_PRIVATE_UPLOAD_BLOCKED_NO_RETRY",
                    "public_release_authorized":False}
        beat=threading.Thread(target=pulse,daemon=True)
        beat.start()
        try:
            # Critical: the second Pi check occurs AFTER durable STARTED and
            # IMMEDIATELY BEFORE the first network videos.insert operation.
            check(full_sha=True)
            meta={"snippet":{
                    "title":p["title"].strip(),
                    "description":p["description"],
                    "categoryId":p["category_id"],
                 },"status":{
                    "privacyStatus":"private",
                    "selfDeclaredMadeForKids":p["made_for_kids"],
                    "containsSyntheticMedia":p["contains_synthetic_media"],
                 }}
            size=self.media.stat().st_size
            session=self.transport.start(self._oauth(),meta,size)
            offset=0
            video=None
            with self.media.open("rb") as source:
                while offset<size:
                    check()
                    source.seek(offset)
                    chunk=source.read(min(CHUNK,size-offset))
                    if not chunk:raise RecoveryPrivateUploaderError("M63 media truncated.")
                    status,next_pos=self.transport.put_chunk(
                        self._oauth(),session,chunk,offset,size)
                    if status in (200,201):
                        if (not isinstance(next_pos,str) or
                            not VIDEO.fullmatch(next_pos)):
                            raise RecoveryPrivateUploaderError("M63 invalid YouTube receipt.")
                        video=next_pos
                        break
                    if status!=308 or type(next_pos) is not int or next_pos!=offset+len(chunk):
                        raise RecoveryPrivateUploaderError("M63 upload range uncertain.")
                    offset=next_pos
            if not video:raise RecoveryPrivateUploaderError("M63 no YouTube video id.")
            self._media_unchanged(full_sha=True)
            self.journal.record_uploaded(job,video)
            verified=self.transport.verify(self._oauth(),video,p["target_channel_id"])
            if (verified.get("video_id")!=video or
                verified.get("channel_id")!=p["target_channel_id"] or
                verified.get("privacy_status")!="private" or
                verified.get("verified_using_authenticated_youtube_api") is not True):
                raise RecoveryPrivateUploaderError("M63 Google privacy/channel verification failed.")
            ready=verified.get("processing_status")=="succeeded"
            if ready:self.journal.record_verified(job,video)
            receipt={
                "status":("YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING"
                          if ready else "YOUTUBE_PRIVATE_PROCESSING_PENDING"),
                "video_id":video,"channel_id":p["target_channel_id"],
                "video_sha256":p["master_sha256"],
                "youtube_privacy":"private",
                "processing_status":verified.get("processing_status"),
                "platform_privacy_verified":True,
                "ready_for_owner_review":ready,
                "public_release_authorized":False,
            }
            check()
            if aborted.is_set():raise RecoveryPrivateUploaderError("M63 heartbeat lost.")
            reply=self.pi.call("recovery-private-complete",
                               {**params,"receipt":receipt})
            if reply.get("status") not in (
                "M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
                "M63_YOUTUBE_PRIVATE_PROCESSING_PENDING"):
                raise RecoveryPrivateUploaderError("M63 Pi private upload ACK invalid.")
            return {"status":reply["status"],"video_id":video,
                    "owner_review_available":ready,
                    "youtube_visibility":"private",
                    "public_release_authorized":False}
        except Exception:
            fail()
            return {"status":"M63_PRIVATE_UPLOAD_RECONCILIATION_REQUIRED_NO_RETRY",
                    "public_release_authorized":False}
        finally:
            stop.set()
            beat.join(timeout=5)


    def reverify_existing(self)->dict:
        """GET-ONLY YouTube status; cannot issue a second videos.insert."""
        p=self.plan
        row=self.journal.status(p["recovery_job_id"])
        if (not row or row["state"]!="UPLOADED_UNVERIFIED" or
            row["plan_sha256"]!=self.plan_sha or
            row["master_sha256"]!=p["master_sha256"] or
            not isinstance(row["video_id"],str) or
            not VIDEO.fullmatch(row["video_id"]) or
            file_sha256(self.media)!=p["master_sha256"]):
            raise RecoveryPrivateUploaderError(
                "M63 existing private upload needs immutable local journal.")
        proof=self.transport.verify(
            self._oauth(),row["video_id"],p["target_channel_id"])
        if (proof.get("video_id")!=row["video_id"] or
            proof.get("channel_id")!=p["target_channel_id"] or
            proof.get("privacy_status")!="private" or
            proof.get("verified_using_authenticated_youtube_api") is not True):
            raise RecoveryPrivateUploaderError("M63 existing video privacy changed.")
        if proof.get("processing_status")!="succeeded":
            return {"status":"M63_YOUTUBE_PRIVATE_PROCESSING_PENDING",
                    "video_id":row["video_id"],
                    "owner_review_available":False,
                    "public_release_authorized":False}
        receipt={"video_id":row["video_id"],
                 "channel_id":p["target_channel_id"],
                 "video_sha256":p["master_sha256"],
                 "youtube_privacy":"private",
                 "processing_status":"succeeded",
                 "platform_privacy_verified":True,
                 "public_release_authorized":False}
        # Save the independently authenticated YouTube proof locally, but
        # NEVER issue videos.insert again if Pi ACK gets lost.
        self.journal.record_verified(p["recovery_job_id"],row["video_id"])
        try:
            result=self.pi.call("recovery-private-reverify",{
                "proposal_id":p["proposal_id"],"receipt":receipt})
        except (RemoteWorkerError,ValueError,OSError,TypeError):
            return {"status":"M63_REVERIFY_PENDING_PI_ACK_NO_REUPLOAD",
                    "video_id":row["video_id"],
                    "public_release_authorized":False}
        if result.get("status")!="M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING":
            raise RecoveryPrivateUploaderError("M63 Pi private reverify state rejected.")
        return {"status":result["status"],"video_id":row["video_id"],
                "owner_review_available":True,
                "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-recovery-private-uploader")
    p.add_argument("--pi-url",required=True)
    p.add_argument("--worker-id",required=True)
    p.add_argument("--ca-file")
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--media",type=Path,required=True)
    p.add_argument("--journal",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--verify-existing",action="store_true",
                   help="Only GET existing video; never start another upload.")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"M63_EXPLICIT_EXECUTE_REQUIRED_NO_NETWORK",
            "youtube_uploaded":False,"public_release_authorized":False}))
        return 0
    try:
        pi=RemoteClient(args.pi_url,worker_id=args.worker_id,
            token=os.environ.get("KIDSSTUDIO_WORKER_TOKEN",""),
            ca_file=args.ca_file)
        w=RecoveryPrivateUploader(pi,plan_file=args.plan,media_file=args.media,
            journal=UploadJournal(args.journal),
            token=os.environ.get("KIDSSTUDIO_YOUTUBE_ACCESS_TOKEN",""))
        result=(w.reverify_existing() if args.verify_existing else w.run_once())
        print(json.dumps(result,sort_keys=True))
        return 0 if result["status"] in (
            "M63_YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
            "M63_YOUTUBE_PRIVATE_PROCESSING_PENDING",
            "M63_NO_PRIVATE_UPLOAD_READY") else 2
    except (RecoveryPrivateUploaderError,YouTubePrivateError,
            RemoteWorkerError,OSError,ValueError,TypeError):
        print("M63_PRIVATE_UPLOAD_WORKER_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
