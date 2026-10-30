"""M64 Pi-owned always-on PRIVATE uploader; Mac has zero Google duties.

All media bytes and OAuth refresh credentials remain on Raspberry Pi. A
local SQLite policy gate checks M62/M63 every upload chunk and heartbeat.
No duplicate videos.insert after an uncertain outcome. The Pi can run under
systemd independently after the Mac-to-Pi LAN transfer has completed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import ssl
import sqlite3
import sys
import threading
import time
from urllib import request,error,parse
from typing import Any,Callable

from .pi_media_inbox import PiMediaInbox,InboxError,READY as MEDIA_READY
from .recovery_private_upload_gate import (
    RecoveryPrivateUploadGate,RecoveryUploadError,
    READY as UPLOAD_READY, CAPABILITY
)
from .recovery_private_uploader import (
    RecoveryPrivateUploader,RecoveryPrivateUploaderError
)
from .studio_queue import StudioQueue
from .youtube_private_upload import UploadJournal,GoogleYouTubeTransport


class PiUploaderError(ValueError):
    pass


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class GoogleOAuthRefresh:
    """Private Pi-only refresh-token grant; no browser/account credentials on Mac."""
    def __init__(self,client_id:str,client_secret:str,refresh_token:str,
                 opener:Any|None=None,clock:Callable[[],float]=time.monotonic):
        if (not all(isinstance(x,str) and len(x)>=12 and
                    not any(c.isspace() for c in x)
                    for x in (client_id,client_secret,refresh_token))):
            raise PiUploaderError("M64 Pi OAuth client/refresh configuration missing.")
        self.client_id=client_id
        self.client_secret=client_secret
        self.refresh_token=refresh_token
        self.clock=clock
        self.access_token=""
        self.refresh_at=0.0
        self.opener=opener or request.build_opener(
            request.ProxyHandler({}),NoRedirect(),
            request.HTTPSHandler(context=ssl.create_default_context()))
        self.lock=threading.Lock()

    def token(self)->str:
        with self.lock:
            if self.access_token and self.clock()<self.refresh_at:
                return self.access_token
            payload=parse.urlencode({
                "grant_type":"refresh_token",
                "client_id":self.client_id,
                "client_secret":self.client_secret,
                "refresh_token":self.refresh_token,
            }).encode("ascii")
            req=request.Request("https://oauth2.googleapis.com/token",
                data=payload,method="POST",
                headers={"Content-Type":"application/x-www-form-urlencoded"})
            try:
                with self.opener.open(req,timeout=30) as reply:
                    if reply.geturl()!="https://oauth2.googleapis.com/token":
                        raise PiUploaderError("OAuth redirect forbidden.")
                    raw=reply.read(8193)
            except (error.URLError,error.HTTPError,OSError,
                    TimeoutError) as exc:
                raise PiUploaderError("M64 Pi-only OAuth refresh failed.") from exc
            if len(raw)>8192:
                raise PiUploaderError("M64 OAuth response too large.")
            try:answer=json.loads(raw)
            except ValueError as exc:
                raise PiUploaderError("M64 OAuth response invalid.") from exc
            access=answer.get("access_token")
            expiry=answer.get("expires_in")
            if (not isinstance(access,str) or len(access)<30 or
                any(c.isspace() for c in access) or
                type(expiry) not in (float,int) or not 180<=expiry<=86400 or
                answer.get("token_type","Bearer")!="Bearer"):
                raise PiUploaderError("M64 OAuth token type/expiry invalid.")
            self.access_token=access
            self.refresh_at=self.clock()+max(30,expiry-120)
            return access


class PiLocalPrivateClient:
    """The Pi worker talks to its local verified DB, never loops back over TLS."""
    def __init__(self,gate:RecoveryPrivateUploadGate,
                 inbox:PiMediaInbox,proposal_id:str,
                 worker_id:str="pi-private-uploader"):
        self.gate=gate
        self.inbox=inbox
        self.proposal_id=proposal_id
        self.worker_id=worker_id

    def call(self,action:str,body:dict)->dict:
        if action=="recovery-private-claim":
            if body!={"proposal_id":self.proposal_id}:
                raise PiUploaderError("M64 wrong local Pi proposal.")
            self.inbox.verify(self.proposal_id,full_sha=True)
            return {"job":self.gate.claim(
                proposal_id=self.proposal_id,worker_id=self.worker_id,
                capability=CAPABILITY,lease_seconds=120)}
        if set(body)!={"job_id","generation"} and not (
            action=="recovery-private-complete" and
            set(body)=={"job_id","generation","receipt"}):
            raise PiUploaderError("M64 local lease request malformed.")
        params=dict(job_id=body["job_id"],worker_id=self.worker_id,
                    generation=body["generation"])
        if action=="recovery-private-check":
            self.inbox.verify(self.proposal_id,full_sha=False)
            return self.gate.check(**params)
        if action=="recovery-private-heartbeat":
            self.inbox.verify(self.proposal_id,full_sha=False)
            proof=self.gate.check(**params,renew=True)
            return {"ok":proof.get("status")=="M63_CURRENT_PRIVATE_UPLOAD_LEASE"}
        if action=="recovery-private-complete":
            self.inbox.verify(self.proposal_id,full_sha=True)
            return self.gate.complete(**params,receipt=body["receipt"])
        if action=="recovery-private-fail":
            return self.gate.fail(**params)
        if action=="recovery-private-reverify":
            # This local client intentionally does not provide an
            # unauthorized replay/renewal bypass.
            raise PiUploaderError("Use explicit same-video local reverify.")
        raise PiUploaderError("M64 unexpected Pi local action.")


class PiPrivateUploadService:
    def __init__(self,queue:StudioQueue,inbox:PiMediaInbox,
                 oauth:GoogleOAuthRefresh,*,journal:UploadJournal,
                 transport:Any|None=None):
        self.queue=queue
        self.inbox=inbox
        self.oauth=oauth
        self.journal=journal
        self.transport=transport or GoogleYouTubeTransport()
        self.gate=RecoveryPrivateUploadGate(queue)

    def poll_once(self)->dict:
        """One bounded polling cycle; only accepted Pi media can upload."""
        with self.queue._connection() as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_recovery_private_handoffs'""").fetchone():
                raise PiUploaderError("M62 private handoff schema absent.")
            available=db.execute("""SELECT proposal_id FROM
                studio_recovery_private_handoffs ORDER BY created_at
                LIMIT 30""").fetchall()
        for item in available:
            pid=item["proposal_id"]
            try:
                with self.queue._connection() as db:
                    current=db.execute("""SELECT state FROM
                        studio_recovery_uploads WHERE proposal_id=?""",
                        (pid,)).fetchone()
                if current:
                    if current["state"]!=UPLOAD_READY:
                        continue
                else:
                    # No premature activation. Transfer bytes must already
                    # have been verified by Pi itself, independent of Mac.
                    try:self.inbox.verify(pid,full_sha=True)
                    except (InboxError,RecoveryUploadError,ValueError,OSError):
                        try:
                            self.inbox.prepare(pid)
                            self.inbox.accept(pid)
                        except (InboxError,RecoveryUploadError,ValueError,OSError,
                                sqlite3.Error):
                            continue
                    self.inbox.verify(pid,full_sha=True)
                    # Pi refresh OAuth BEFORE reserving a one-shot upload.
                    self.oauth.token()
                    self.gate.activate(pid)
                trusted=self.inbox.verify(pid,full_sha=True)
                pi=PiLocalPrivateClient(self.gate,self.inbox,pid)
                worker=RecoveryPrivateUploader(
                    pi,plan_file=trusted["plan"],media_file=trusted["video"],
                    journal=self.journal,token=self.oauth.token(),
                    token_provider=self.oauth.token,transport=self.transport,
                    heartbeat_seconds=15)
                result=worker.run_once()
                return {**result,"uploader_device":"RASPBERRY_PI",
                        "mac_required_for_upload":False}
            except (RecoveryUploadError,InboxError,
                    RecoveryPrivateUploaderError,PiUploaderError,
                    OSError,ValueError,sqlite3.Error):
                # Fail closed; after an unknown Google outcome the local
                # STARTED upload journal blocks any second videos.insert.
                continue
        return {"status":"M64_PI_UPLOAD_IDLE_NO_ELIGIBLE_PRIVATE_MEDIA",
                "mac_required_for_upload":False,
                "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-pi-private-uploader")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--inbox-root",type=Path,required=True)
    p.add_argument("--journal",type=Path,required=True)
    p.add_argument("--loop",action="store_true")
    p.add_argument("--poll-seconds",type=int,default=30)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"M64_PI_UPLOADER_DRY_RUN_NO_GOOGLE",
            "mac_required_for_upload":False,
            "youtube_uploaded":False,"public_release_authorized":False}))
        return 0
    if not 10<=args.poll_seconds<=3600:
        p.error("Private polling interval must be 10..3600 seconds.")
    try:
        refresh=GoogleOAuthRefresh(
            os.environ.get("KIDSSTUDIO_PI_YT_CLIENT_ID",""),
            os.environ.get("KIDSSTUDIO_PI_YT_CLIENT_SECRET",""),
            os.environ.get("KIDSSTUDIO_PI_YT_REFRESH_TOKEN",""))
        queue=StudioQueue(args.db)
        inbox=PiMediaInbox(queue,args.inbox_root)
        service=PiPrivateUploadService(queue,inbox,refresh,
            journal=UploadJournal(args.journal))
        while True:
            result=service.poll_once()
            print(json.dumps(result,sort_keys=True),flush=True)
            if not args.loop:break
            time.sleep(args.poll_seconds)
        return 0
    except (PiUploaderError,InboxError,ValueError,OSError,
            TypeError,sqlite3.Error):
        print("M64_PI_UPLOADER_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
