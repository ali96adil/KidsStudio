"""M26 outbound-only Mac PRIVATE uploader agent (one job per invocation).

An owner installs a standing policy on the Pi once; when an approved final
master appears in the Mac's private ready-file catalogue, the agent asks Pi
to enqueue one exact-SHA PRIVATE job, claims it with a separate TLS worker
identity, checks the currently leased/approved policy twice (second check
*after* durable local upload reservation), then invokes the M25 uploader.

No public publishing endpoints, no arbitrary file execution, no blind retry
after uncertain HTTP failures. Source catalogue is local private metadata,
not a Git repository. A processing-pending upload has no automatic new
videos.insert request. M25 OAuth access token is read from Mac env only.
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
from typing import Any, Callable

from .episode_assembly import _ensure_private
from .remote_worker import RemoteClient, RemoteWorkerError
from .youtube_private_upload import (
    UploadJournal, YouTubePrivateError, file_sha256, private_upload,
    validate_plan, GoogleYouTubeTransport,
)

HEX=re.compile(r"^[a-f0-9]{64}$")
JOB=re.compile(r"^[a-f0-9]{32}$")
EXPECTED=frozenset({
    "series_id","episode_number","render_job_id","master_sha256",
    "plan_sha256","readiness_sha256","channel_id","made_for_kids",
    "contains_synthetic_media","policy_revision",
})


class PrivateAgentError(ValueError):
    pass


class PrivateCatalogue:
    """Owner-approved local catalogue maintained by the Mac production line."""
    def __init__(self, file: str | Path):
        original=Path(file).expanduser()
        if not original.is_absolute() or original.is_symlink():
            raise PrivateAgentError("Catalogue must be an absolute private JSON.")
        self.path=original.resolve()
        _ensure_private(self.path.parent)
        if (not self.path.is_file() or self.path.suffix!=".json" or
                not 0<self.path.stat().st_size<=60_000):
            raise PrivateAgentError("Missing/oversized private upload catalogue.")
        try: document=json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise PrivateAgentError("Malformed private catalogue.") from exc
        if (not isinstance(document,dict) or
            set(document)!={"schema_version","private_root","entries"} or
            document["schema_version"]!=1 or
            not isinstance(document["entries"],list) or
            not 1<=len(document["entries"])<=100):
            raise PrivateAgentError("Invalid private catalogue schema.")
        root=Path(document["private_root"]).expanduser()
        if not root.is_absolute() or root.is_symlink():
            raise PrivateAgentError("Private asset root must be absolute.")
        self.root=_ensure_private(root.resolve())
        if not self.root.is_dir() or not self.path.is_relative_to(self.root):
            raise PrivateAgentError("Catalogue must be under the private asset root.")
        self.entries=[]
        for item in document["entries"]:
            if (not isinstance(item,dict) or
                set(item)!={"plan","media","readiness","readiness_sha256"} or
                not isinstance(item["readiness_sha256"],str) or
                not HEX.fullmatch(item["readiness_sha256"])):
                raise PrivateAgentError("Every local entry needs exact files/M8 hash.")
            paths={}
            for name in ("plan","media","readiness"):
                raw=Path(item[name]).expanduser()
                if not raw.is_absolute() or raw.is_symlink():
                    raise PrivateAgentError("Private media paths must be absolute non-symlink.")
                resolved=raw.resolve()
                if not resolved.is_relative_to(self.root) or not resolved.is_file():
                    raise PrivateAgentError("Catalogue path escaped private asset root.")
                paths[name]=resolved
            if paths["plan"].suffix!=".json":
                raise PrivateAgentError("Pinned plan must be JSON.")
            try:
                plan=json.loads(paths["plan"].read_text(encoding="utf-8"))
            except (OSError,ValueError) as exc:
                raise PrivateAgentError("Invalid pinned plan file.") from exc
            check=validate_plan(plan,paths["media"],paths["readiness"],
                                item["readiness_sha256"])
            self.entries.append({"plan":plan,"paths":paths,
                                 "plan_sha256":file_sha256(paths["plan"]),
                                 "readiness_sha256":item["readiness_sha256"],
                                 "check":check})
        pairs=[(e["plan"]["series_id"],e["plan"]["episode_number"],
                e["plan"]["render_job_id"]) for e in self.entries]
        if len(set(pairs))!=len(pairs):
            raise PrivateAgentError("Duplicate pending episode/master in catalogue.")

    def matching(self, payload:dict)->dict:
        if not isinstance(payload,dict) or set(payload)!=EXPECTED:
            raise PrivateAgentError("Pi upload payload has unexpected fields.")
        matches=[]
        for entry in self.entries:
            plan=entry["plan"]
            if (entry["plan_sha256"]==payload["plan_sha256"] and
                entry["readiness_sha256"]==payload["readiness_sha256"] and
                plan["render_job_id"]==payload["render_job_id"] and
                plan["master_sha256"]==payload["master_sha256"] and
                plan["series_id"]==payload["series_id"] and
                plan["episode_number"]==payload["episode_number"] and
                plan["target_channel_id"]==payload["channel_id"] and
                plan["made_for_kids"] is payload["made_for_kids"] and
                plan["contains_synthetic_media"] is payload["contains_synthetic_media"]):
                matches.append(entry)
        if len(matches)!=1:
            raise PrivateAgentError("Current leased job has no exact private Mac catalogue match.")
        entry=matches[0]
        if (file_sha256(entry["paths"]["plan"])!=entry["plan_sha256"] or
            file_sha256(entry["paths"]["readiness"])!=entry["readiness_sha256"]):
            raise PrivateAgentError("Pinned upload plan or M8 proof was modified.")
        validate_plan(entry["plan"],entry["paths"]["media"],
                      entry["paths"]["readiness"],entry["readiness_sha256"])
        return entry


class PrivateUploadAgent:
    def __init__(self, pi:Any, catalogue:PrivateCatalogue,
                 journal:UploadJournal, token:str, *,
                 transport:Any|None=None):
        self.pi=pi
        self.catalogue=catalogue
        self.journal=journal
        self.token=token
        self.transport=transport if transport is not None else GoogleYouTubeTransport()

    @staticmethod
    def _proof(proof:dict,job_id:str,generation:int,payload:dict)->None:
        if (not isinstance(proof,dict) or
            proof.get("status")!="CURRENT_PRIVATE_UPLOAD_LEASE_NOT_EXECUTED" or
            proof.get("job_id")!=job_id or proof.get("generation")!=generation or
            proof.get("plan_sha256")!=payload["plan_sha256"] or
            proof.get("master_sha256")!=payload["master_sha256"] or
            proof.get("channel_id")!=payload["channel_id"] or
            proof.get("visibility")!="private" or
            proof.get("public_release_authorized") is not False):
            raise PrivateAgentError("Pi private-only lease attestation rejected.")

    def run_once(self, *, discover:bool=True)->dict:
        # The agent may ask Pi to queue private uploads without repeated
        # per-video owner prompts, but ONLY under the owner's narrow standing
        # series/channel/budget permission and after final QA. No HTTP to
        # Google occurs while discovering candidates.
        requests=0
        if discover:
            for entry in self.catalogue.entries:
                plan=entry["plan"]
                if self.journal.status(plan["render_job_id"]) is not None:
                    continue
                request={
                    "series_id":plan["series_id"],
                    "episode_number":plan["episode_number"],
                    "render_job_id":plan["render_job_id"],
                    "master_sha256":plan["master_sha256"],
                    "plan_sha256":entry["plan_sha256"],
                    "readiness_sha256":entry["readiness_sha256"],
                    "channel_id":plan["target_channel_id"],
                    "made_for_kids":plan["made_for_kids"],
                    "contains_synthetic_media":plan["contains_synthetic_media"],
                }
                try:
                    response=self.pi.call("request-private-upload",request)
                    if response.get("status")=="PRIVATE_UPLOAD_QUEUED_NOT_RUN":
                        requests+=1
                except RemoteWorkerError:
                    # Could be already queued, owner policy disabled,
                    # budget reached or Pi temporarily disconnected.
                    # Do not create an uploader attempt from an error.
                    pass
        response=self.pi.call("claim",{})
        job=response.get("job")
        if job is None:
            return {"status":"NO_ELIGIBLE_PRIVATE_UPLOAD_JOB",
                    "new_jobs":requests,"public_release_authorized":False}
        if (not isinstance(job,dict) or
            job.get("kind")!="youtube_private_upload" or
            not isinstance(job.get("job_id"),str) or
            not JOB.fullmatch(job["job_id"]) or
            type(job.get("generation")) is not int or job["generation"]<1):
            raise PrivateAgentError("Dedicated upload worker received invalid Pi claim.")
        job_id,generation=job["job_id"],job["generation"]
        payload=job.get("payload")
        try:
            entry=self.catalogue.matching(payload)
        except (PrivateAgentError,YouTubePrivateError,OSError,TypeError):
            self._fail(job_id,generation,"MEDIA_CONFIGURATION_REJECTED")
            return {"status":"UPLOAD_CONFIG_REJECTED","job_id":job_id}
        request={"job_id":job_id,"generation":generation,"payload":payload}
        try:
            proof=self.pi.call("private-upload-lease-check",request)
            self._proof(proof,job_id,generation,payload)
        except (RemoteWorkerError,PrivateAgentError,TypeError):
            self._fail(job_id,generation,"MEDIA_CONFIGURATION_REJECTED")
            return {"status":"UPLOAD_LEASE_REJECTED","job_id":job_id}
        stop=threading.Event()
        lost=[]
        def heartbeat():
            while not stop.wait(45):
                try:self.pi.call("heartbeat",{"job_id":job_id,"generation":generation})
                except (RemoteWorkerError,Exception):
                    lost.append(True)
                    return
        thread=threading.Thread(target=heartbeat,daemon=True)
        thread.start()
        try:
            def final_pi_check():
                if lost:
                    raise PrivateAgentError("Private uploader lost its Pi lease.")
                fresh=self.pi.call("private-upload-lease-check",request)
                self._proof(fresh,job_id,generation,payload)
            # The second Pi gate runs *after* M25 persists STARTED and
            # immediately before the first videos.insert network call.
            report=private_upload(
                entry["plan"],entry["paths"]["media"],
                entry["paths"]["readiness"],entry["readiness_sha256"],
                self.journal,self.token,transport=self.transport,
                before_network=final_pi_check)
            if lost:
                raise PrivateAgentError("Lease heartbeat failed during private upload.")
            ack=self.pi.call("complete-private-upload",{
                "job_id":job_id,"generation":generation,"result":report})
            if (ack.get("status")!="PRIVATE_UPLOAD_RECEIPT_RECORDED_NOT_PUBLIC" or
                ack.get("public_release_authorized") is not False):
                raise PrivateAgentError("Pi did not acknowledge private-only receipt.")
            return {"status":report["status"],"job_id":job_id,
                    "video_id":report["video_id"],
                    "owner_review_queued":ack.get("owner_review_queued") is True,
                    "public_release_authorized":False}
        except (PrivateAgentError,YouTubePrivateError,RemoteWorkerError,
                OSError,ValueError,TypeError):
            # Failure after M25 STARTED is never automatically retried.
            # An upload may have reached YouTube despite lost Pi ACK;
            # manual reconciliation must inspect the journal and channel.
            self._fail(job_id,generation,"MEDIA_RECONCILIATION_REQUIRED")
            return {"status":"UPLOAD_MANUAL_RECONCILIATION_REQUIRED",
                    "job_id":job_id,"public_release_authorized":False}
        finally:
            stop.set()
            thread.join(timeout=5)

    def _fail(self,job_id,generation,code):
        try:self.pi.call("fail",{
            "job_id":job_id,"generation":generation,"error_code":code})
        except RemoteWorkerError:pass


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-private-upload-agent",
        description="Opt-in Mac worker for owner-permitted YouTube PRIVATE only.")
    p.add_argument("--pi",required=True)
    p.add_argument("--worker-id",required=True)
    p.add_argument("--ca-file")
    p.add_argument("--catalogue",type=Path,required=True)
    p.add_argument("--journal",type=Path,required=True)
    p.add_argument("--pi-token-env",default="KIDS_STUDIO_PRIVATE_UPLOAD_PI_TOKEN")
    p.add_argument("--youtube-token-env",default="KIDS_STUDIO_YOUTUBE_OAUTH_ACCESS_TOKEN")
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    try:
        if (not re.fullmatch(r"[A-Z][A-Z0-9_]{4,90}",args.pi_token_env) or
            not re.fullmatch(r"[A-Z][A-Z0-9_]{4,90}",args.youtube_token_env)):
            raise PrivateAgentError("Token environment names are invalid.")
        catalogue=PrivateCatalogue(args.catalogue)
        if not args.execute:
            print(json.dumps({
                "status":"PRIVATE_AGENT_PREFLIGHT_ONLY_NOT_RUN",
                "available_local_plans":len(catalogue.entries),
                "youtube_api_called":False,"pi_jobs_claimed":False,
                "public_release_authorized":False
            },ensure_ascii=False))
            return 0
        pi=RemoteClient(args.pi,worker_id=args.worker_id,
             token=os.environ.get(args.pi_token_env,""),
             ca_file=args.ca_file)
        worker=PrivateUploadAgent(pi,catalogue,UploadJournal(args.journal),
                                  os.environ.get(args.youtube_token_env,""))
        print(json.dumps(worker.run_once(),ensure_ascii=False))
        return 0
    except (PrivateAgentError,YouTubePrivateError,RemoteWorkerError,
            OSError,ValueError,TypeError) as exc:
        print("PRIVATE_UPLOAD_AGENT_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
