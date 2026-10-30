"""M64 Mac post-production LAN-only watcher.

This polls a private outbox of immutable owner-approved upload plans.
Pi, NOT Mac, decides whether M62/M63 approval is still valid and hashes
received bytes before uploading to YouTube. No Google secrets on Mac.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import time

from .mac_to_pi_transfer import transfer_master_to_pi,LANTransferError
from .recovery_private_uploader import _plan,RecoveryPrivateUploaderError

JOB=re.compile(r"^[a-f0-9]{32}$")


class OutboxError(ValueError):
    pass


class MacToPiOutbox:
    def __init__(self,*,outbox:Path,renders:Path,
                 pi_host:str,pi_user:str,pi_inbox_root:str,
                 ssh_key:Path,transfer=transfer_master_to_pi):
        self.outbox=Path(outbox).expanduser()
        self.renders=Path(renders).expanduser()
        if (not self.outbox.is_absolute() or self.outbox.is_symlink() or
            not self.renders.is_absolute() or self.renders.is_symlink() or
            not self.outbox.is_dir() or not self.renders.is_dir()):
            raise OutboxError("M64 Mac private production outbox/render root required.")
        self.pi_host=pi_host
        self.pi_user=pi_user
        self.pi_inbox_root=pi_inbox_root
        self.ssh_key=Path(ssh_key).expanduser()
        self.transfer=transfer

    def poll_once(self)->dict:
        # A .json file is a draft until the M62 AI/rights process commits
        # its final, validated proposal as a .ready.json. Pi remains the
        # authoritative gate and may reject stale/forged plans.
        for file in sorted(self.outbox.glob("*.ready.json"))[:30]:
            if file.is_symlink() or not file.is_file():
                continue
            marker=self.outbox/(file.name+".sent")
            if marker.exists() or marker.is_symlink():
                continue
            try:
                plan,_=_plan(file)
                if not JOB.fullmatch(plan["recovery_job_id"]):
                    continue
                source=self.renders/plan["recovery_job_id"]/"episode_qa_master.mp4"
                result=self.transfer(
                    media=source,plan_file=file,
                    pi_host=self.pi_host,pi_user=self.pi_user,
                    pi_inbox_root=self.pi_inbox_root,ssh_key=self.ssh_key)
                # This only means rsync finished, NOT Pi media accepted.
                fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,"w") as out:
                    out.write(json.dumps({
                        "status":"M64_SENT_PI_HASH_STILL_REQUIRED",
                        "recovery_job_id":plan["recovery_job_id"],
                        "master_sha256":plan["master_sha256"],
                    },sort_keys=True)+"\n")
                    out.flush();os.fsync(out.fileno())
                return {**result,"outbox_recorded":True}
            except (RecoveryPrivateUploaderError,LANTransferError,
                    OutboxError,ValueError,OSError):
                # Safe retry of incomplete .part at the NEXT poll; no
                # local media regeneration or Google network invocation.
                continue
        return {"status":"M64_MAC_OUTBOX_IDLE_NO_LAN_TRANSFER",
                "mac_google_upload_enabled":False}

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-mac-outbox-to-pi")
    p.add_argument("--outbox",type=Path,required=True)
    p.add_argument("--renders",type=Path,required=True)
    p.add_argument("--pi-host",required=True)
    p.add_argument("--pi-user",required=True)
    p.add_argument("--pi-inbox-root",required=True)
    p.add_argument("--ssh-key",type=Path,required=True)
    p.add_argument("--poll-seconds",type=int,default=30)
    p.add_argument("--loop",action="store_true")
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"M64_MAC_OUTBOX_DRY_RUN_NO_NETWORK",
            "youtube_uploaded":False}))
        return 0
    if not 10<=args.poll_seconds<=3600:
        p.error("M64 poll cadence must be 10..3600 seconds.")
    try:
        runner=MacToPiOutbox(
            outbox=args.outbox,renders=args.renders,
            pi_host=args.pi_host,pi_user=args.pi_user,
            pi_inbox_root=args.pi_inbox_root,ssh_key=args.ssh_key)
        while True:
            print(json.dumps(runner.poll_once(),sort_keys=True),flush=True)
            if not args.loop:break
            time.sleep(args.poll_seconds)
        return 0
    except (OutboxError,OSError,ValueError,TypeError):
        print("M64_MAC_LAN_OUTBOX_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
