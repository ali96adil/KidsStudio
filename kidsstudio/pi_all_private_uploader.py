"""M65 one always-on Pi service for BOTH ordinary and recovery PRIVATE videos.

Mac is a producer/SSH LAN sender only. The Pi keeps all media, owner
policy/QA receipts, Google OAuth refresh grant and durable upload journal.
Nothing publishes videos; PRIVATE processing precedes owner review.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

from .studio_queue import StudioQueue
from .pi_media_inbox import PiMediaInbox,InboxError
from .pi_ordinary_inbox import PiOrdinaryInbox,OrdinaryInboxError
from .pi_recovery_uploader import (
    PiPrivateUploadService,GoogleOAuthRefresh,PiUploaderError
)
from .pi_ordinary_uploader import PiOrdinaryUploadService,OrdinaryPiUploaderError
from .recovery_private_upload_gate import (
    RecoveryPrivateUploadGate,RecoveryUploadError
)
from .youtube_private_upload import UploadJournal

class PiAllUploadError(ValueError):
    pass


class PiAllPrivateUploadService:
    def __init__(self,queue:StudioQueue,*,root:Path,
                 journal:UploadJournal,oauth:GoogleOAuthRefresh,
                 transport=None):
        self.queue=queue
        self.root=root
        self.recovery_inbox=PiMediaInbox(queue,root)
        self.ordinary_inbox=PiOrdinaryInbox(queue,root)
        self.recovery=PiPrivateUploadService(
            queue,self.recovery_inbox,oauth,
            journal=journal,transport=transport)
        self.ordinary=PiOrdinaryUploadService(
            queue,self.ordinary_inbox,oauth,
            journal=journal,transport=transport)

    def initialize(self)->dict:
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        os.chmod(self.root,0o700)
        self.ordinary_inbox.initialize()
        with self.queue._connection() as db:
            recovery_ready=bool(db.execute("""SELECT 1 FROM sqlite_master
                WHERE type='table' AND
                name='studio_recovery_private_handoffs'""").fetchone())
        if recovery_ready:
            self.recovery_inbox.initialize()
            RecoveryPrivateUploadGate(self.queue).initialize()
        return {"status":"M65_PI_BOTH_PRIVATE_INBOXES_READY",
                "youtube_uploaded":False,
                "mac_required_for_upload":False}

    def poll_once(self)->dict:
        # Fairness: if recovery has already processed a video, ordinary
        # resumes on the next pass. Neither branch can exceed M26's
        # shared per-series daily budget.
        with self.queue._connection() as db:
            recovery_ready=bool(db.execute("""SELECT 1 FROM sqlite_master
                WHERE name='studio_recovery_private_handoffs'
                AND type='table'""").fetchone())
        recovered=(self.recovery.poll_once() if recovery_ready else
                   {"status":"M64_PI_UPLOAD_IDLE_NO_ELIGIBLE_PRIVATE_MEDIA"})
        if recovered.get("status")!=(
            "M64_PI_UPLOAD_IDLE_NO_ELIGIBLE_PRIVATE_MEDIA"):
            return {**recovered,"pi_uploader_scope":"RECOVERY"}
        regular=self.ordinary.poll_once()
        return {**regular,"pi_uploader_scope":"ORDINARY"}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-pi-all-private-upload")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--inbox-root",type=Path,required=True)
    p.add_argument("--journal",type=Path,required=True)
    group=p.add_mutually_exclusive_group()
    group.add_argument("--initialize",action="store_true")
    group.add_argument("--execute",action="store_true")
    p.add_argument("--loop",action="store_true")
    p.add_argument("--poll-seconds",type=int,default=30)
    args=p.parse_args(argv)
    if not args.initialize and not args.execute:
        print(json.dumps({"status":"M65_PI_PRIVATE_UPLOADER_DRY_RUN",
            "mac_youtube_upload_enabled":False,
            "network_used":False,"public_release_authorized":False}))
        return 0
    if not 10<=args.poll_seconds<=3600:
        p.error("M65 Pi polling cadence must be 10..3600 seconds.")
    try:
        brain=StudioQueue(args.db)
        if args.initialize:
            # No Google OAuth refresh credentials or HTTP at schema creation.
            trusted_root=PiMediaInbox(brain,args.inbox_root).root
            trusted_root.mkdir(mode=0o700,parents=True,exist_ok=True)
            os.chmod(trusted_root,0o700)
            PiOrdinaryInbox(brain,trusted_root).initialize()
            with brain._connection() as db:
                has_recovery=bool(db.execute("""SELECT 1 FROM sqlite_master
                    WHERE name='studio_recovery_private_handoffs'
                    AND type='table'""").fetchone())
            if has_recovery:
                PiMediaInbox(brain,trusted_root).initialize()
                RecoveryPrivateUploadGate(brain).initialize()
            result={"status":"M65_PI_BOTH_PRIVATE_INBOXES_READY",
                "ordinary_inbox_initialized":True,
                "recovery_inbox_initialized":has_recovery,
                "youtube_uploaded":False,
                "mac_required_for_upload":False}
            print(json.dumps(result,sort_keys=True))
            return 0
        oauth=GoogleOAuthRefresh(
            os.environ.get("KIDSSTUDIO_PI_YT_CLIENT_ID",""),
            os.environ.get("KIDSSTUDIO_PI_YT_CLIENT_SECRET",""),
            os.environ.get("KIDSSTUDIO_PI_YT_REFRESH_TOKEN",""))
        service=PiAllPrivateUploadService(
            brain,root=args.inbox_root,
            journal=UploadJournal(args.journal),oauth=oauth)
        while True:
            result=service.poll_once()
            print(json.dumps(result,sort_keys=True),flush=True)
            if not args.loop:break
            time.sleep(args.poll_seconds)
        return 0
    except (InboxError,OrdinaryInboxError,PiUploaderError,
            OrdinaryPiUploaderError,RecoveryUploadError,
            PiAllUploadError,OSError,ValueError,TypeError,sqlite3.Error):
        print("M65_PI_PRIVATE_UPLOAD_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
