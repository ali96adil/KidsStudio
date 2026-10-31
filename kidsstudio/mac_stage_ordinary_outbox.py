"""M65: auto-populate Mac LAN outbox from existing approved M25 catalogue.

No Pi network request and no Google OAuth. Readiness/AI/rights and exact
private media must already have passed M25's existing local validation.
Pi independently checks current M26 approvals again after LAN transfer.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
from typing import Any

from .private_upload_agent import PrivateCatalogue,PrivateAgentError
from .youtube_private_upload import file_sha256


class OrdinaryOutboxError(ValueError):
    pass


def _write_or_verify(source:Path,dest:Path,checksum:str)->bool:
    if dest.is_symlink():
        raise OrdinaryOutboxError("M65 outbox symlink forbidden.")
    if dest.exists():
        if not dest.is_file() or file_sha256(dest)!=checksum:
            raise OrdinaryOutboxError("M65 outbox existing plan differs.")
        return False
    fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,"wb") as output,source.open("rb") as stream:
            shutil.copyfileobj(stream,output,1024*1024)
            output.flush();os.fsync(output.fileno())
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if file_sha256(dest)!=checksum:
        raise OrdinaryOutboxError("M65 staged outbox bytes mismatch.")
    return True


def stage_approved_ordinary_outbox(
    catalogue:PrivateCatalogue,outbox:Path)->dict[str,Any]:
    root=Path(outbox).expanduser()
    if not root.is_absolute() or root.is_symlink():
        raise OrdinaryOutboxError("M65 private Mac outbox must be absolute.")
    if any((p/".git").exists() for p in (root,*root.parents)):
        raise OrdinaryOutboxError("M65 private outbox cannot be a Git directory.")
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(root,0o700)
    prepared=0
    for entry in catalogue.entries:
        plan=entry["plan"]
        job=plan["render_job_id"]
        if entry["check"]["master_sha256"]!=plan["master_sha256"]:
            raise OrdinaryOutboxError("M65 current M25 media no longer matches.")
        source_plan=entry["paths"]["plan"]
        source_readiness=entry["paths"]["readiness"]
        # Write M8 first and the *.ordinary.ready.json FINAL signal last.
        ready_dest=root/(job+".ordinary.m8.json")
        plan_dest=root/(job+".ordinary.ready.json")
        _write_or_verify(source_readiness,ready_dest,
                         entry["readiness_sha256"])
        created=_write_or_verify(source_plan,plan_dest,
                                 entry["plan_sha256"])
        if created:prepared+=1
    return {"status":"M65_MAC_ORDINARY_LAN_OUTBOX_STAGED_NO_UPLOAD",
            "new_plans":prepared,"network_used":False,
            "youtube_uploaded":False,
            "public_release_authorized":False}
