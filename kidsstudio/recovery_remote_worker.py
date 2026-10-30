"""M61 Mac-only recovery_assemble worker over the authenticated Pi TLS API.

One configured proposal, original job and original payload. Never accepts
Pi-provided file paths or schema-2 recipes as executable inputs. A durable
at-most-one-start Mac journal blocks accidental retry after ambiguous failure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Any

from .media_worker import MediaJournal,MediaRecipes,MediaError
from .montage_recovery import RecoveryJournal
from .remote_worker import RemoteClient,RemoteWorkerError
from .recovery_render import render_private_recovery_master,RecoveryRenderError

JOB=re.compile(r"^[a-f0-9]{32}$")
SHA=re.compile(r"^[a-f0-9]{64}$")


class RecoveryWorkerError(ValueError):
    pass


class RemoteRecoveryWorker:
    def __init__(
        self,pi:RemoteClient,recipes:MediaRecipes,journal:MediaJournal,
        *,original_job_id:str,proposal_id:str,original_payload_file:Path,
        heartbeat_seconds:float=10.0,executor=None,
    ):
        if (not isinstance(original_job_id,str) or
            not JOB.fullmatch(original_job_id) or
            not isinstance(proposal_id,str) or
            not JOB.fullmatch(proposal_id) or
            original_job_id==proposal_id or
            type(heartbeat_seconds) not in (int,float) or
            not .05<=heartbeat_seconds<=60):
            raise RecoveryWorkerError("Bounded M61 recovery worker configuration required.")
        file=Path(original_payload_file).expanduser()
        if (not file.is_absolute() or file.is_symlink() or
            not file.is_file() or not 0<file.stat().st_size<=4096):
            raise RecoveryWorkerError("M61 requires original Mac-private job payload.")
        try:payload=json.loads(file.read_text(encoding="utf-8"))
        except (OSError,ValueError,UnicodeError) as exc:
            raise RecoveryWorkerError("M61 original payload not readable.") from exc
        if (not isinstance(payload,dict) or
            set(payload)!={"recipe_id","script_sha256","catalogue_sha256"} or
            not isinstance(payload["recipe_id"],str) or
            any(not isinstance(payload[k],str) or not SHA.fullmatch(payload[k])
                for k in ("script_sha256","catalogue_sha256"))):
            raise RecoveryWorkerError("M61 exact original multi-scene payload required.")
        self.pi=pi
        self.recipes=recipes
        self.journal=journal
        self.original_job_id=original_job_id
        self.proposal_id=proposal_id
        self.payload=payload
        self.heartbeat_seconds=heartbeat_seconds
        self.executor=executor or render_private_recovery_master

    def run_once(self)->dict[str,Any]:
        response=self.pi.call("recovery-claim",{"proposal_id":self.proposal_id})
        claim=response.get("job")
        if claim is None:return {"status":"NO_ELIGIBLE_RECOVERY"}
        if (not isinstance(claim,dict) or
            claim.get("kind")!="recovery_assemble" or
            claim.get("proposal_id")!=self.proposal_id or
            claim.get("original_job_id")!=self.original_job_id or
            not isinstance(claim.get("job_id"),str) or
            not JOB.fullmatch(claim["job_id"]) or
            claim["job_id"] in (self.original_job_id,self.proposal_id) or
            type(claim.get("generation")) is not int or
            claim["generation"]!=1 or
            not isinstance(claim.get("recipe_sha256"),str) or
            not SHA.fullmatch(claim["recipe_sha256"])):
            raise RecoveryWorkerError("M61 Pi recovery claim is not exact configured intent.")
        job_id,generation=claim["job_id"],claim["generation"]
        params={"job_id":job_id,"generation":generation}
        key=hashlib.sha256(json.dumps({
            "kind":"recovery_assemble",
            "original_job_id":self.original_job_id,
            "proposal_id":self.proposal_id,
            "recipe_sha256":claim["recipe_sha256"],
        },sort_keys=True).encode("utf-8")).hexdigest()
        def failure():
            try:self.pi.call("recovery-fail",params)
            except (RemoteWorkerError,OSError,ValueError):
                pass
        try:
            state,_=self.journal.begin(
                job_id,key,"recovery_assemble","recovery_"+self.proposal_id)
        except (MediaError,OSError,ValueError):
            failure()
            return {"status":"M61_MAC_JOURNAL_BLOCKED_NO_RETRY","job_id":job_id}
        if state!="NEW":
            failure()
            return {"status":"M61_MAC_REPLAY_BLOCKED_NO_RETRY","job_id":job_id}
        abort=threading.Event()
        stop=threading.Event()
        def beat():
            while not stop.wait(self.heartbeat_seconds):
                try:
                    result=self.pi.call("recovery-heartbeat",params)
                    if result.get("ok") is not True:
                        raise RemoteWorkerError("Pi rejected M61 recovery heartbeat.")
                except (RemoteWorkerError,OSError,ValueError,TypeError):
                    abort.set()
                    return
        task=threading.Thread(target=beat,daemon=True)
        task.start()
        def live():
            proof=self.pi.call("recovery-pre-execution-check",params)
            if proof.get("status")!="M61_CURRENT_PRIVATE_RECOVERY_LEASE":
                raise RemoteWorkerError("M61 current recovery proof revoked.")
            return proof
        try:
            result=self.executor(
                self.recipes,RecoveryJournal(self.journal.path),
                original_job_id=self.original_job_id,
                payload=self.payload,proposal_id=self.proposal_id,
                job_id=job_id,generation=generation,
                lease_check=live,abort_event=abort)
            if abort.is_set():
                raise RecoveryRenderError("M61 network/lease lost during FFmpeg.")
            if (not isinstance(result,dict) or
                result.get("status")!=
                "M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW" or
                result.get("publication_approved") is not False or
                result.get("final_m7_full_decode_passed") is not True):
                raise RecoveryRenderError("M61 recovery worker returned unverified master.")
            self.journal.done(job_id,result)
        except Exception:
            abort.set();stop.set();task.join(timeout=5)
            failure()
            return {"status":"M61_BLOCKED_RECONCILIATION_NO_RETRY",
                    "job_id":job_id}
        stop.set();task.join(timeout=5)
        if abort.is_set():
            return {"status":"M61_PENDING_ACK_LEASE_UNCERTAIN",
                    "job_id":job_id}
        try:
            ack=self.pi.call("recovery-complete",{**params,"result":result})
            if (ack.get("status") !=
                "M61_RENDERED_PENDING_FINAL_M7_OWNER_REVIEW"):
                raise RemoteWorkerError("M61 Pi did not confirm private review status.")
            return {"status":"M61_COMPLETED_PRIVATE_REVIEW_REQUIRED",
                    "job_id":job_id,
                    "public_release_authorized":False}
        except (RemoteWorkerError,OSError,ValueError,TypeError):
            # No replay/rerender; requires explicit manual reconciliation.
            return {"status":"M61_PENDING_ACK_NO_AUTO_RETRY",
                    "job_id":job_id}
