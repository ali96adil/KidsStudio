"""M65 Pi always-on LAN staging intake, independent of long Google upload.

This Pi service prepares and SHA-verifies new ordinary/recovery masters
while a SEPARATE Pi upload service may be busy uploading for hours.
No Google/OAuth access required. It cannot authorize PUBLIC or upload.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time

from .studio_queue import StudioQueue
from .pi_media_inbox import PiMediaInbox,InboxError
from .pi_ordinary_inbox import PiOrdinaryInbox,OrdinaryInboxError
from .recovery_private_upload_gate import RecoveryUploadError


class PiInboxReceiver:
    def __init__(self,queue:StudioQueue,root:Path):
        self.queue=queue
        self.ordinary=PiOrdinaryInbox(queue,root)
        self.recovery=PiMediaInbox(queue,root)

    def poll_once(self)->dict:
        with self.queue._connection() as db:
            regular=db.execute("""SELECT e.render_job_id FROM studio_episodes e
                JOIN studio_series s ON s.series_id=e.series_id
                WHERE e.state='EPISODE_APPROVED' AND s.state='ACTIVE'
                AND e.render_job_id IS NOT NULL
                ORDER BY e.render_job_id LIMIT 100""").fetchall()
            has_recovery=bool(db.execute("""SELECT 1 FROM sqlite_master WHERE
                type='table' AND name='studio_recovery_private_handoffs'""").fetchone())
            proposals=(db.execute("""SELECT proposal_id FROM
                studio_recovery_private_handoffs
                ORDER BY created_at LIMIT 100""").fetchall()
                if has_recovery else [])
        received=0
        prepared=0
        for row in regular:
            job=row["render_job_id"]
            try:
                self.ordinary.verify(job,full_sha=False)
                continue
            except (OrdinaryInboxError,OSError,ValueError,sqlite3.Error):
                pass
            try:
                self.ordinary.prepare(job)
                prepared+=1
            except (OrdinaryInboxError,OSError,ValueError,sqlite3.Error):
                continue
            try:
                accepted=self.ordinary.accept(job)
                if accepted["status"]=="M65_PI_ORDINARY_MEDIA_VERIFIED_PRIVATE_ONLY":
                    received+=1
            except (OrdinaryInboxError,OSError,ValueError,sqlite3.Error):
                # Part-file incomplete: safe to retry later. No upload action.
                pass
        for row in proposals:
            pid=row["proposal_id"]
            try:
                self.recovery.verify(pid,full_sha=False)
                continue
            except (InboxError,RecoveryUploadError,OSError,ValueError,sqlite3.Error):
                pass
            try:
                self.recovery.prepare(pid)
                prepared+=1
            except (InboxError,RecoveryUploadError,OSError,ValueError,sqlite3.Error):
                continue
            try:
                accepted=self.recovery.accept(pid)
                if accepted["status"]=="M64_PI_MEDIA_VERIFIED_PRIVATE_ONLY":
                    received+=1
            except (InboxError,RecoveryUploadError,OSError,
                    ValueError,sqlite3.Error):
                pass
        return {"status":"M65_PI_LAN_INBOX_POLLED_NO_GOOGLE",
                "new_folders_prepared":prepared,
                "new_media_sha_verified":received,
                "parallel_pi_google_upload_unaffected":True,
                "mac_google_upload_disabled":True,
                "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-pi-lan-receiver")
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--inbox-root",type=Path,required=True)
    p.add_argument("--poll-seconds",type=int,default=20)
    p.add_argument("--loop",action="store_true")
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"M65_PI_LAN_RECEIVER_DRY_RUN",
            "network_used":False,"youtube_uploaded":False}))
        return 0
    if not 5<=args.poll_seconds<=3600:
        p.error("M65 bounded Pi intake interval required.")
    try:
        service=PiInboxReceiver(StudioQueue(args.db),args.inbox_root)
        while True:
            print(json.dumps(service.poll_once(),sort_keys=True),flush=True)
            if not args.loop:break
            time.sleep(args.poll_seconds)
        return 0
    except (InboxError,OrdinaryInboxError,RecoveryUploadError,
            sqlite3.Error,ValueError,OSError,TypeError):
        print("M65_PI_INBOX_RECEIVER_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
