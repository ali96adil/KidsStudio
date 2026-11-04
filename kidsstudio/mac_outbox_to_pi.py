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
from .mac_ordinary_to_pi import transfer_ordinary_to_pi
from .mac_stage_ordinary_outbox import (
    stage_approved_ordinary_outbox,OrdinaryOutboxError
)
from .private_upload_agent import PrivateCatalogue,PrivateAgentError
from .recovery_private_uploader import _plan,RecoveryPrivateUploaderError

JOB=re.compile(r"^[a-f0-9]{32}$")


class OutboxError(ValueError):
    pass


class MacToPiOutbox:
    def __init__(self,*,outbox:Path,renders:Path,
                 pi_host:str,pi_user:str,pi_inbox_root:str,
                 ssh_key:Path,transfer=transfer_master_to_pi,
                 ordinary_transfer=transfer_ordinary_to_pi,
                 ordinary_catalogue:Path|None=None):
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
        self.ordinary_transfer=ordinary_transfer
        self.ordinary_catalogue=(Path(ordinary_catalogue).expanduser()
                                if ordinary_catalogue else None)
        self._catalogue_stamp=None

    def poll_once(self)->dict:
        # Watch the approved M25 ordinary catalogue once per file revision;
        # avoids repeatedly SHA-hashing multi-GB videos every 30 seconds.
        if self.ordinary_catalogue is not None:
            source=self.ordinary_catalogue
            if not source.is_file() or source.is_symlink():
                raise OutboxError("M65 ordinary approved catalogue missing.")
            stamp=(source.stat().st_size,source.stat().st_mtime_ns)
            if stamp!=self._catalogue_stamp:
                try:
                    stage_approved_ordinary_outbox(
                        PrivateCatalogue(source),self.outbox)
                except (OrdinaryOutboxError,PrivateAgentError,
                        ValueError,OSError) as exc:
                    raise OutboxError("M65 ordinary catalogue QA rejected.") from exc
                self._catalogue_stamp=stamp
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
                if file.name.endswith(".ordinary.ready.json"):
                    plan=json.loads(file.read_bytes())
                    if not isinstance(plan,dict) or not isinstance(
                        plan.get("render_job_id"),str) or not JOB.fullmatch(
                            plan["render_job_id"]):
                        continue
                    job=plan["render_job_id"]
                    readiness=self.outbox/(job+".ordinary.m8.json")
                    source=self.renders/job/"episode_qa_master.mp4"
                    result=self.ordinary_transfer(
                        media=source,plan_file=file,readiness_file=readiness,
                        pi_host=self.pi_host,pi_user=self.pi_user,
                        pi_inbox_root=self.pi_inbox_root,ssh_key=self.ssh_key)
                    identifier=job
                    expected_sha=plan["master_sha256"]
                else:
                    plan,_=_plan(file)
                    if not JOB.fullmatch(plan["recovery_job_id"]):
                        continue
                    job=plan["recovery_job_id"]
                    source=self.renders/job/"episode_qa_master.mp4"
                    result=self.transfer(
                        media=source,plan_file=file,
                        pi_host=self.pi_host,pi_user=self.pi_user,
                        pi_inbox_root=self.pi_inbox_root,ssh_key=self.ssh_key)
                    identifier=job
                    expected_sha=plan["master_sha256"]
                # This only means rsync finished, NOT Pi media accepted.
                fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                with os.fdopen(fd,"w") as out:
                    out.write(json.dumps({
                        "status":"M64_SENT_PI_HASH_STILL_REQUIRED",
                        "render_or_recovery_job_id":identifier,
                        "master_sha256":expected_sha,
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
    p.add_argument("--ordinary-catalogue",type=Path)
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
            pi_inbox_root=args.pi_inbox_root,ssh_key=args.ssh_key,
            ordinary_catalogue=args.ordinary_catalogue)
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
