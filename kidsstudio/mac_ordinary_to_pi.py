"""M65 LAN transfer of ordinary M25 approved episode to Pi; no Google.

Same strict local SSH/rsync transport as recovery M64, with an additional
independent M8 readiness JSON copied for Pi-side technical verification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any,Callable

from .mac_to_pi_transfer import (
    HOST,SSH_ACCOUNT,PATH,LANTransferError
)
from .youtube_private_upload import validate_plan,file_sha256,YouTubePrivateError


def transfer_ordinary_to_pi(
    *,media:Path,plan_file:Path,readiness_file:Path,
    pi_host:str,pi_user:str,pi_inbox_root:str,ssh_key:Path,
    runner:Callable[...,Any]=subprocess.run,
)->dict:
    if (not isinstance(pi_host,str) or not HOST.fullmatch(pi_host) or
        not isinstance(pi_user,str) or not SSH_ACCOUNT.fullmatch(pi_user) or
        not isinstance(pi_inbox_root,str) or not PATH.fullmatch(pi_inbox_root) or
        ".." in pi_inbox_root.split("/") or
        pi_inbox_root.endswith("/")):
        raise LANTransferError("M65 Pi local transfer endpoint invalid.")
    key=Path(ssh_key).expanduser()
    if not key.is_absolute() or key.is_symlink() or not key.is_file() or key.stat().st_mode & 0o077:
        raise LANTransferError("M65 transfer SSH key must be private mode 0600.")
    for value in (media,plan_file,readiness_file):
        path=Path(value).expanduser()
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise LANTransferError("M65 original approved Mac source unavailable.")
    try:
        plan=json.loads(Path(plan_file).read_bytes())
        ready_sha=file_sha256(Path(readiness_file))
        checked=validate_plan(plan,media,readiness_file,ready_sha)
    except (OSError,ValueError,TypeError,YouTubePrivateError) as exc:
        raise LANTransferError("M65 current ordinary M8 owner QA invalid.") from exc
    job=plan["render_job_id"]
    if Path(media).name!="episode_qa_master.mp4" or Path(media).parent.name!=job:
        raise LANTransferError("M65 original Mac master not in run directory.")
    original_plan_sha=file_sha256(Path(plan_file))
    ssh=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
         "-o","ConnectTimeout=15","-o","PasswordAuthentication=no",
         "-i",str(key)]
    shell=" ".join(shlex.quote(x) for x in ssh)
    dest=pi_inbox_root+"/"+job
    for local,name in (
        (Path(media),"episode_qa_master.mp4.part"),
        (Path(plan_file),"private_upload_plan.json.part"),
        (Path(readiness_file),"m8_readiness.json.part")):
        args=["rsync","--partial","--inplace","--no-perms",
              "--no-owner","--no-group","-t","-e",shell,
              str(local),pi_user+"@"+pi_host+":"+
              shlex.quote(dest+"/"+name)]
        try:
            runner(args,check=True,timeout=86400,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except (OSError,subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as exc:
            raise LANTransferError(
                "M65 LAN copy incomplete; resume same Pi .part files.") from exc
    if (file_sha256(Path(media))!=plan["master_sha256"] or
        file_sha256(Path(plan_file))!=original_plan_sha or
        file_sha256(Path(readiness_file))!=ready_sha):
        raise LANTransferError("M65 approved Mac video/readiness changed during transfer.")
    return {
        "status":"M65_MAC_ORDINARY_LAN_SENT_PI_HASH_PENDING",
        "render_job_id":job,"master_sha256":checked["master_sha256"],
        "pi_revalidation_required":True,
        "google_called_from_mac":False,
        "youtube_uploaded":False,"public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-mac-ordinary-to-pi")
    p.add_argument("--media",type=Path,required=True)
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--readiness",type=Path,required=True)
    p.add_argument("--pi-host",required=True)
    p.add_argument("--pi-user",required=True)
    p.add_argument("--pi-inbox-root",required=True)
    p.add_argument("--ssh-key",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"M65_MAC_ORDINARY_NO_NETWORK_DRY_RUN",
            "google_called_from_mac":False}))
        return 0
    try:
        result=transfer_ordinary_to_pi(
            media=args.media,plan_file=args.plan,
            readiness_file=args.readiness,
            pi_host=args.pi_host,pi_user=args.pi_user,
            pi_inbox_root=args.pi_inbox_root,ssh_key=args.ssh_key)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (LANTransferError,OSError,ValueError,TypeError):
        print("M65_MAC_ORDINARY_TRANSFER_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
