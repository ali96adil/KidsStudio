"""M64 Mac -> local Pi resumable SSH/rsync transfer, NO Google HTTP.

Pi must pre-prepare a private per-job staging directory. This tool never
runs a remote shell command, never authorizes publication, and reports only
bytes handed to the LAN, not approval. Pi must independently hash+accept.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any,Callable

from .recovery_private_uploader import _plan,RecoveryPrivateUploaderError
from .youtube_private_upload import file_sha256,MAX_BYTES

SSH_ACCOUNT=re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
HOST=re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}$")
PATH=re.compile(r"^/[a-zA-Z0-9_./-]{1,900}$")
USER_JOB=re.compile(r"^[a-f0-9]{32}$")


class LANTransferError(ValueError):
    pass


def transfer_master_to_pi(
    *,media:Path,plan_file:Path,pi_host:str,pi_user:str,
    pi_inbox_root:str,ssh_key:Path,
    runner:Callable[...,Any]=subprocess.run,
    rsync_exe:str="rsync",
)->dict:
    """An interrupted transfer can be re-run safely: rsync checks delta.

    Local file hash is checked before/after; a stale or partially sent Pi
    file is not trusted until the independent Pi-side accept gate succeeds.
    """
    if (not isinstance(pi_host,str) or not HOST.fullmatch(pi_host) or
        not isinstance(pi_user,str) or not SSH_ACCOUNT.fullmatch(pi_user) or
        not isinstance(pi_inbox_root,str) or
        not PATH.fullmatch(pi_inbox_root) or
        ".." in pi_inbox_root.split("/") or
        not pi_inbox_root.startswith("/") or
        pi_inbox_root.endswith("/") or
        not isinstance(rsync_exe,str) or
        rsync_exe not in ("rsync","/opt/homebrew/bin/rsync",
                          "/usr/local/bin/rsync")):
        raise LANTransferError("M64 fixed trusted Pi LAN destination required.")
    key=Path(ssh_key).expanduser()
    if (not key.is_absolute() or key.is_symlink() or
        not key.is_file() or key.stat().st_mode & 0o077):
        raise LANTransferError("M64 dedicated private SSH key must be mode 0600.")
    plan,plan_sha=_plan(plan_file)
    source=Path(media).expanduser()
    if (not source.is_absolute() or source.is_symlink() or
        source.name!="episode_qa_master.mp4" or
        source.parent.name!=plan["recovery_job_id"] or
        not source.is_file() or
        not 1000<=source.stat().st_size<=MAX_BYTES or
        file_sha256(source)!=plan["master_sha256"]):
        raise LANTransferError("M64 original approved Mac master SHA invalid.")
    ssh=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
         "-o","ConnectTimeout=15","-o","PasswordAuthentication=no",
         "-i",str(key)]
    # rsync 2.6.9 (macOS built-in) supports --partial --inplace. After
    # interrupted LAN transfer, next execution updates incomplete .part
    # without discarding the bytes already sent to the Pi.
    remote=pi_user+"@"+pi_host+":"
    dest=pi_inbox_root+"/"+plan["recovery_job_id"]
    shell=" ".join(shlex.quote(x) for x in ssh)
    for original,name in (
        (source,"episode_qa_master.mp4.part"),
        (Path(plan_file).expanduser(),"private_upload_plan.json.part")
    ):
        if original.is_symlink():
            raise LANTransferError("M64 source symlink not permitted.")
        # Rsync 2.x uses remote-shell syntax; quote a single whitelisted path.
        # The Pi root/job directory must exist and must be writable only by
        # the dedicated staging account, not arbitrary SSH users.
        target=remote+shlex.quote(dest+"/"+name)
        args=[rsync_exe,"--partial","--inplace","--no-perms",
              "--no-owner","--no-group","-t","-e",shell,
              str(original),target]
        try:
            status=runner(args,check=True,timeout=86400,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except (OSError,subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            raise LANTransferError(
                "M64 Pi local rsync incomplete; safe to resume same .part.") from exc
    if (file_sha256(source)!=plan["master_sha256"] or
        file_sha256(Path(plan_file))!=plan_sha):
        raise LANTransferError("M64 Mac input changed while transferring.")
    return {"status":"M64_MAC_LAN_TRANSFER_SENT_PI_SHA_NOT_YET_CONFIRMED",
            "proposal_id":plan["proposal_id"],
            "recovery_job_id":plan["recovery_job_id"],
            "master_sha256":plan["master_sha256"],
            "master_bytes":source.stat().st_size,
            "pi_must_hash_and_accept":True,
            "mac_youtube_upload_enabled":False,
            "youtube_uploaded":False,
            "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-mac-to-pi")
    p.add_argument("--media",type=Path,required=True)
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--pi-host",required=True)
    p.add_argument("--pi-user",required=True)
    p.add_argument("--pi-inbox-root",required=True)
    p.add_argument("--ssh-key",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({
            "status":"M64_EXPLICIT_LAN_TRANSFER_REQUIRED_NO_NETWORK",
            "mac_youtube_upload_enabled":False,
            "youtube_uploaded":False}))
        return 0
    try:
        result=transfer_master_to_pi(
            media=args.media,plan_file=args.plan,
            pi_host=args.pi_host,pi_user=args.pi_user,
            pi_inbox_root=args.pi_inbox_root,ssh_key=args.ssh_key)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (LANTransferError,RecoveryPrivateUploaderError,
            OSError,ValueError,TypeError):
        print("M64_MAC_TO_PI_TRANSFER_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
