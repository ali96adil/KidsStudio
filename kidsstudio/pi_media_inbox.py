"""M64: transfer-frozen Mac masters into a Pi-owned local PRIVATE inbox.

SSH/rsync is LAN transport only; Pi rehashes bytes and pins M61/M62/M63
source and owner channel policy in SQLite before ANY YouTube upload.
A remote transfer cannot self-authorize an upload or write the Pi DB.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any

from .studio_queue import StudioQueue
from .recovery_private_upload_gate import RecoveryPrivateUploadGate,RecoveryUploadError
from .recovery_private_uploader import _plan
from .youtube_private_upload import file_sha256,MAX_BYTES

PID=re.compile(r"^[a-f0-9]{32}$")
READY="M64_PI_MEDIA_VERIFIED_PRIVATE_ONLY"


class InboxError(ValueError):
    pass


def _safe_root(root:Path)->Path:
    path=Path(root).expanduser()
    if (not path.is_absolute() or path.is_symlink()
        or any((p/".git").exists() for p in (path,*path.parents))):
        raise InboxError("Pi inbox must be an absolute private non-Git location.")
    return path.resolve()


class PiMediaInbox:
    def __init__(self,queue:StudioQueue,root:str|Path):
        self.queue=queue
        self.root=_safe_root(Path(root))

    def initialize(self)->None:
        if self.root.exists():
            if self.root.is_symlink() or not self.root.is_dir():
                raise InboxError("Pi inbox root invalid.")
        else:
            self.root.mkdir(parents=True,mode=0o700)
        os.chmod(self.root,0o700)
        with self.queue._connection(write=True) as db:
            if not db.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                AND name='studio_recovery_private_handoffs'""").fetchone():
                raise InboxError("Pi M62 independent QA must be initialized.")
            db.execute("""CREATE TABLE IF NOT EXISTS studio_recovery_pi_media(
                proposal_id TEXT PRIMARY KEY REFERENCES
                    studio_recovery_private_handoffs(proposal_id),
                recovery_job_id TEXT NOT NULL UNIQUE,
                master_sha256 TEXT NOT NULL,
                media_bytes INTEGER NOT NULL,
                plan_sha256 TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(
                    state='M64_PI_MEDIA_VERIFIED_PRIVATE_ONLY'),
                created_at REAL NOT NULL
            )""")

    def _directory(self,job_id:str)->Path:
        if not isinstance(job_id,str) or not PID.fullmatch(job_id):
            raise InboxError("Pi exact recovery job ID required.")
        root=self.root
        if not root.is_dir() or root.is_symlink():
            raise InboxError("Pi inbox root missing.")
        dest=root/job_id
        if dest.is_symlink():
            raise InboxError("Pi staged directory symlink forbidden.")
        return dest

    def prepare(self,proposal_id:str)->dict:
        """Pi-local action before rsync. No upload work starts."""
        with self.queue._connection(write=True) as db:
            proof=RecoveryPrivateUploadGate(self.queue)._source(db,proposal_id)
            if db.execute("""SELECT 1 FROM studio_recovery_pi_media
                WHERE proposal_id=?""",(proposal_id,)).fetchone():
                raise InboxError("Pi accepted media cannot be overwritten.")
            target=self._directory(proof["job_id"])
            if target.exists():
                if not target.is_dir() or target.is_symlink():
                    raise InboxError("Pi transfer target not a real directory.")
            else:
                target.mkdir(mode=0o700)
            os.chmod(target,0o700)
        return {"status":"M64_PI_LOCAL_INBOX_PREPARED_NO_UPLOAD",
                "proposal_id":proposal_id,
                "recovery_job_id":proof["job_id"],
                "media_received":False,
                "youtube_upload_performed":False}

    def _files(self,job_id:str,*,partial:bool)->tuple[Path,Path]:
        path=self._directory(job_id)
        if not path.is_dir():raise InboxError("Pi transfer folder absent.")
        ext=".part" if partial else ""
        return path/("episode_qa_master.mp4"+ext),path/("private_upload_plan.json"+ext)

    @staticmethod
    def _validate_file(file:Path,lower:int,upper:int)->None:
        if (file.is_symlink() or not file.is_file() or
            not lower<=file.stat().st_size<=upper or
            file.stat().st_nlink!=1):
            raise InboxError("Pi transferred data is absent, linked or oversized.")

    def accept(self,proposal_id:str)->dict:
        """Full Pi-side SHA, fsync then atomic rename, immutable one-shot DB."""
        with self.queue._connection(write=True) as db:
            proof=RecoveryPrivateUploadGate(self.queue)._source(db,proposal_id)
            if db.execute("""SELECT 1 FROM studio_recovery_pi_media WHERE
                proposal_id=?""",(proposal_id,)).fetchone():
                raise InboxError("Pi media already accepted.")
            target=self._directory(proof["job_id"])
            source,metadata=self._files(proof["job_id"],partial=True)
            final_video,final_plan=self._files(proof["job_id"],partial=False)
            if final_video.exists() or final_plan.exists():
                raise InboxError("Pi existing finalized file: manual reconciliation.")
            self._validate_file(source,1000,MAX_BYTES)
            self._validate_file(metadata,20,15_000)
            plan,plan_sha=_plan(metadata,allow_partial=True)
            if (plan["proposal_id"]!=proposal_id or
                plan["recovery_job_id"]!=proof["job_id"] or
                plan["series_id"]!=proof["series_id"] or
                plan["episode_number"]!=proof["episode_number"] or
                plan["master_sha256"]!=proof["master_sha256"] or
                plan["target_channel_id"]!=proof["channel_id"] or
                plan["made_for_kids"] is not proof["made_for_kids"] or
                plan["contains_synthetic_media"] is not
                    proof["contains_synthetic_media"]):
                raise InboxError("Pi owner M62 media plan and channel mismatch.")
            if file_sha256(source)!=proof["master_sha256"]:
                raise InboxError("Pi SHA-256 mismatch; do not accept partial file.")
            # Rechecked immediately before replace: only trusted Pi-local
            # operation may promote received data. Never overwrite.
            with source.open("rb") as fd:os.fsync(fd.fileno())
            with metadata.open("rb") as fd:os.fsync(fd.fileno())
            os.replace(source,final_video)
            os.replace(metadata,final_plan)
            os.chmod(final_video,0o400)
            os.chmod(final_plan,0o400)
            dfd=os.open(str(target),os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(dfd)
            finally:os.close(dfd)
            db.execute("""INSERT INTO studio_recovery_pi_media
                VALUES(?,?,?,?,?,?,?,?)""",
                (proposal_id,proof["job_id"],proof["master_sha256"],
                 final_video.stat().st_size,plan_sha,proof["channel_id"],
                 READY,self.queue.clock()))
            self.queue._event(db,proof["original_job_id"],
                "M64_PI_LAN_MEDIA_SHA_VERIFIED",{"proposal_id":proposal_id})
        return {"status":READY,"proposal_id":proposal_id,
                "recovery_job_id":proof["job_id"],
                "media_sha256":proof["master_sha256"],
                "media_bytes":final_video.stat().st_size,
                "mac_required_for_upload":False,
                "youtube_uploaded":False,
                "public_release_authorized":False}

    def verify(self,proposal_id:str,*,full_sha:bool=False)->dict:
        with self.queue._connection() as db:
            proof=RecoveryPrivateUploadGate(self.queue)._source(db,proposal_id)
            row=db.execute("""SELECT * FROM studio_recovery_pi_media
                WHERE proposal_id=?""",(proposal_id,)).fetchone()
            if (not row or row["state"]!=READY or
                row["recovery_job_id"]!=proof["job_id"] or
                row["master_sha256"]!=proof["master_sha256"] or
                row["channel_id"]!=proof["channel_id"]):
                raise InboxError("Pi inbox has no matching accepted M62 master.")
            video,plan_file=self._files(proof["job_id"],partial=False)
            self._validate_file(video,1000,MAX_BYTES)
            self._validate_file(plan_file,20,15_000)
            plan,plan_sha=_plan(plan_file)
            if (video.stat().st_size!=row["media_bytes"] or
                plan_sha!=row["plan_sha256"] or
                plan["proposal_id"]!=proposal_id or
                plan["recovery_job_id"]!=proof["job_id"] or
                plan["master_sha256"]!=proof["master_sha256"] or
                plan["target_channel_id"]!=proof["channel_id"] or
                plan["series_id"]!=proof["series_id"] or
                plan["episode_number"]!=proof["episode_number"] or
                plan["made_for_kids"] is not proof["made_for_kids"] or
                plan["contains_synthetic_media"] is not
                    proof["contains_synthetic_media"] or
                (full_sha and file_sha256(video)!=row["master_sha256"])):
                raise InboxError("Pi accepted master/plan changed after transfer.")
            return {"status":READY,"proposal_id":proposal_id,
                    "master_sha256":row["master_sha256"],
                    "video":video,"plan":plan_file,
                    "master_bytes":row["media_bytes"],
                    "channel_id":row["channel_id"]}


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="studio-pi-media-inbox")
    parser.add_argument("--db",required=True)
    parser.add_argument("--root",type=Path,required=True)
    cmd=parser.add_mutually_exclusive_group(required=True)
    cmd.add_argument("--initialize",action="store_true")
    cmd.add_argument("--prepare",action="store_true")
    cmd.add_argument("--accept",action="store_true")
    cmd.add_argument("--verify",action="store_true")
    parser.add_argument("--proposal-id")
    args=parser.parse_args(argv)
    try:
        inbox=PiMediaInbox(StudioQueue(args.db),args.root)
        if args.initialize:
            inbox.initialize()
            result={"status":"M64_PI_INBOX_READY_NO_UPLOAD"}
        elif not args.proposal_id:
            raise InboxError("Pi exact proposal ID required.")
        elif args.prepare:
            result=inbox.prepare(args.proposal_id)
        elif args.accept:
            result=inbox.accept(args.proposal_id)
        else:
            result=inbox.verify(args.proposal_id,full_sha=True)
            result={k:v for k,v in result.items()
                    if k not in ("video","plan")}
        print(json.dumps(result,ensure_ascii=False,default=str,sort_keys=True))
        return 0
    except (InboxError,RecoveryUploadError,ValueError,
            TypeError,KeyError,OSError,sqlite3.Error):
        print("M64_PI_INBOX_BLOCKED",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
