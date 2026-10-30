"""M25 opt-in PRIVATE-only YouTube Data API upload and exact video check.

Explicit owner invocation required. No OAuth browser flow or token refresh; a
fresh owner-provided OAuth bearer token is read from a private environment
variable. Every network request is made through TLS to a fixed Google API
hostname; no redirects, arbitrary URL, cloud model, or videos.update.
An on-disk STARTED attempt is durable before the first network call; failures
are quarantined and never automatically re-upload the same master.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import sys
import time
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit

from .episode_assembly import _ensure_private

SHA=re.compile(r"^[0-9a-f]{64}$")
JOB=re.compile(r"^[0-9a-f]{32}$")
VIDEO=re.compile(r"^[A-Za-z0-9_-]{11}$")
CHANNEL=re.compile(r"^UC[A-Za-z0-9_-]{22}$")
ENV=re.compile(r"^[A-Z][A-Z0-9_]{4,90}$")
INIT_URL="https://www.googleapis.com/upload/youtube/v3/videos"
GET_URL="https://www.googleapis.com/youtube/v3/videos"
CHUNK=8*1024*1024
MAX_BYTES=10*1024**3


class YouTubePrivateError(ValueError):
    """Cannot safely start/continue a private-only upload."""


def file_sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda:source.read(4*1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def _json(data: bytes) -> dict:
    if len(data)>1_000_000:
        raise YouTubePrivateError("Oversized YouTube response.")
    try:
        value=json.loads(data)
    except (TypeError,ValueError) as exc:
        raise YouTubePrivateError("Malformed YouTube response.") from exc
    if not isinstance(value,dict):
        raise YouTubePrivateError("Invalid YouTube response object.")
    return value


def _session(url: str) -> None:
    parsed=urlsplit(url)
    params=parse_qs(parsed.query,keep_blank_values=True)
    if (parsed.scheme!="https" or parsed.hostname!="www.googleapis.com"
        or parsed.port is not None or parsed.username or parsed.password
        or parsed.fragment or parsed.path!="/upload/youtube/v3/videos"
        or params.get("uploadType")!=["resumable"]
        or len(params.get("upload_id",[]))!=1
        or not params["upload_id"][0]
        or len(url)>2048):
        raise YouTubePrivateError("Unexpected resumable upload destination.")


def validate_plan(plan: dict, media: str | Path, readiness: str | Path,
                  expected_readiness_sha256: str, *,
                  allow_partial:bool=False) -> dict:
    required={"schema_version","series_id","episode_number",
              "render_job_id","master_sha256","target_channel_id",
              "title","description","category_id","made_for_kids",
              "contains_synthetic_media"}
    if not isinstance(plan,dict) or set(plan)!=required or plan["schema_version"]!=1:
        raise YouTubePrivateError("Explicit reviewed private-upload plan required.")
    sid=plan["series_id"]
    ordinal=plan["episode_number"]
    if (not isinstance(sid,str) or
        not re.fullmatch(r"[a-z][a-z0-9_-]{1,47}",sid) or
        type(ordinal) is not int or not 1<=ordinal<=120 or
        not isinstance(plan["render_job_id"],str) or
        not JOB.fullmatch(plan["render_job_id"]) or
        not isinstance(plan["master_sha256"],str) or
        not SHA.fullmatch(plan["master_sha256"]) or
        not isinstance(plan["target_channel_id"],str) or
        not CHANNEL.fullmatch(plan["target_channel_id"]) or
        not isinstance(plan["title"],str) or
        not 1<=len(plan["title"].strip())<=100 or
        not isinstance(plan["description"],str) or
        len(plan["description"])>4800 or
        not isinstance(plan["category_id"],str) or
        not re.fullmatch(r"[0-9]{1,3}",plan["category_id"]) or
        type(plan["made_for_kids"]) is not bool or
        type(plan["contains_synthetic_media"]) is not bool):
        raise YouTubePrivateError("Owner upload metadata invalid.")
    if not isinstance(expected_readiness_sha256,str) or not SHA.fullmatch(expected_readiness_sha256):
        raise YouTubePrivateError("Exact SHA of current M8 readiness report required.")
    path=Path(media).expanduser()
    gate=Path(readiness).expanduser()
    if (not path.is_absolute() or path.is_symlink() or
        not (path.suffix.lower()==".mp4" or
            allow_partial and path.name.endswith(".mp4.part"))
        or not gate.is_absolute() or gate.is_symlink() or
        not (gate.suffix.lower()==".json" or
            allow_partial and gate.name.endswith(".json.part"))):
        raise YouTubePrivateError("Private absolute non-symlink MP4 and M8 report required.")
    path=path.resolve();gate=gate.resolve()
    _ensure_private(path.parent);_ensure_private(gate.parent)
    if not gate.is_file() or not 0<gate.stat().st_size<=30000:
        raise YouTubePrivateError("Missing or oversized M8 readiness report.")
    if file_sha256(gate)!=expected_readiness_sha256:
        raise YouTubePrivateError("M8 readiness report bytes changed.")
    report=_json(gate.read_bytes())
    required_gate={"status","series_id","episode_number","render_job_id",
                   "video_sha256","owner_final_qa","upload_performed",
                   "public_release_authorized"}
    if (not required_gate.issubset(report)
        or report.get("schema_version")!=1
        or report["status"]!="READY_FOR_MANUAL_PRIVATE_PREVIEW_NOT_UPLOADED"
        or (report["series_id"],report["episode_number"],report["render_job_id"],
            report["video_sha256"])!=
           (sid,ordinal,plan["render_job_id"],plan["master_sha256"])
        or not (
            report["owner_final_qa"] is True and
            report.get("ai_internal_review_approved",False) is False
            or report["owner_final_qa"] is False and
            report.get("ai_internal_review_approved") is True)
        or report["upload_performed"] is not False
        or report["public_release_authorized"] is not False):
        raise YouTubePrivateError("Current owner-pinned M8 archive readiness mismatch.")
    if not path.is_file() or not 1000<=path.stat().st_size<=MAX_BYTES:
        raise YouTubePrivateError("Owner master MP4 missing or size outside safe bounds.")
    current=file_sha256(path)
    if current!=plan["master_sha256"]:
        raise YouTubePrivateError("MP4 differs from owner-approved final master SHA.")
    return {
        "status":"OWNER_PINNED_PRIVATE_UPLOAD_NOT_EXECUTED",
        "series_id":sid,"episode_number":ordinal,
        "render_job_id":plan["render_job_id"],
        "master_sha256":current,"master_bytes":path.stat().st_size,
        "target_channel_id":plan["target_channel_id"],
        "youtube_visibility":"PRIVATE",
        "made_for_kids":plan["made_for_kids"],
        "contains_synthetic_media":plan["contains_synthetic_media"],
        "video_uploaded":False,"public_release_authorized":False,
    }


class UploadJournal:
    """Single-start receipt, isolated on Mac, never stored in Git checkout."""
    def __init__(self,file: str | Path):
        self.path=Path(file).expanduser().resolve()
        if self.path.suffix!=".sqlite":
            raise YouTubePrivateError("Private upload journal must be .sqlite.")
        if any((p/".git").exists() for p in (self.path,*self.path.parents)):
            raise YouTubePrivateError("Upload journal may not live inside Git.")
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if not self.path.exists():
            fd=os.open(str(self.path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(fd)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS attempts (
                render_job_id TEXT PRIMARY KEY, master_sha256 TEXT NOT NULL UNIQUE,
                plan_sha256 TEXT NOT NULL, state TEXT NOT NULL,
                video_id TEXT, created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")
            db.execute("PRAGMA synchronous=FULL")

    def reserve(self,job: str,sha: str,plan_sha: str)->None:
        with sqlite3.connect(self.path,timeout=10,isolation_level=None) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM attempts WHERE render_job_id=?",
                          (job,)).fetchone():
                raise YouTubePrivateError("This render already has an upload attempt. Manual reconciliation required.")
            now=time.time()
            try:
                db.execute("""INSERT INTO attempts VALUES (?,?,?,'STARTED',NULL,?,?)""",
                           (job,sha,plan_sha,now,now))
            except sqlite3.IntegrityError as exc:
                raise YouTubePrivateError("Master SHA already uploaded or reserved. Manual reconciliation required.") from exc
            db.execute("COMMIT")

    def record_uploaded(self,job: str,video_id: str)->None:
        if not VIDEO.fullmatch(video_id):
            raise YouTubePrivateError("Invalid YouTube video ID.")
        with sqlite3.connect(self.path) as db:
            cur=db.execute("""UPDATE attempts SET state='UPLOADED_UNVERIFIED',
                video_id=?,updated_at=? WHERE render_job_id=? AND state='STARTED'""",
                (video_id,time.time(),job))
            if cur.rowcount!=1:
                raise YouTubePrivateError("Journal state conflicts with uploaded video.")

    def record_verified(self,job: str,video_id: str)->None:
        with sqlite3.connect(self.path) as db:
            cur=db.execute("""UPDATE attempts SET state='PRIVATE_VERIFIED',
                updated_at=? WHERE render_job_id=? AND state='UPLOADED_UNVERIFIED'
                AND video_id=?""",(time.time(),job,video_id))
            if cur.rowcount!=1:
                raise YouTubePrivateError("No matching uploaded video to verify.")

    def status(self,job: str)->dict|None:
        with sqlite3.connect(self.path) as db:
            db.row_factory=sqlite3.Row
            row=db.execute("SELECT * FROM attempts WHERE render_job_id=?",(job,)).fetchone()
            return dict(row) if row else None


class GoogleYouTubeTransport:
    """HTTPS only, no proxies, no redirect following, bounded responses."""
    def _request(self,method: str,url: str,token: str,body:bytes=b"",
                 headers:dict|None=None)->tuple[int,dict[str,str],bytes]:
        parsed=urlsplit(url)
        if parsed.scheme!="https" or parsed.hostname!="www.googleapis.com" or parsed.port:
            raise YouTubePrivateError("Only Google HTTPS API origin is allowed.")
        if parsed.path not in ("/upload/youtube/v3/videos","/youtube/v3/videos"):
            raise YouTubePrivateError("Unexpected Google API path.")
        endpoint=parsed.path+("?"+parsed.query if parsed.query else "")
        conn=http.client.HTTPSConnection("www.googleapis.com",timeout=120,
                                        context=ssl.create_default_context())
        try:
            h={"Authorization":"Bearer "+token,"Accept":"application/json",
               "Connection":"close",**(headers or {})}
            conn.request(method,endpoint,body=body,headers=h)
            response=conn.getresponse()
            if int(response.getheader("Content-Length") or "0")>1_000_000:
                raise YouTubePrivateError("Oversized API response.")
            content=response.read(1_000_001)
            if len(content)>1_000_000:
                raise YouTubePrivateError("Oversized API response.")
            return response.status,{k.lower():v for k,v in response.getheaders()},content
        except (OSError,TimeoutError,http.client.HTTPException) as exc:
            raise YouTubePrivateError("Google HTTPS call failed; never auto-retry.") from exc
        finally:conn.close()

    def start(self,token:str,metadata:dict,size:int)->str:
        body=json.dumps(metadata,separators=(",",":"),ensure_ascii=False).encode()
        query=urlencode({"uploadType":"resumable","part":"snippet,status",
                         "notifySubscribers":"false"})
        code,headers,_=self._request("POST",INIT_URL+"?"+query,token,body,{
            "Content-Type":"application/json; charset=UTF-8",
            "X-Upload-Content-Length":str(size),
            "X-Upload-Content-Type":"video/mp4",
        })
        if code not in (200,201):
            raise YouTubePrivateError("YouTube rejected private upload initiation.")
        session=headers.get("location","")
        _session(session)
        return session

    def put_chunk(self,token:str,session:str,data:bytes,
                  offset:int,total:int)->tuple[int,int|str]:
        _session(session)
        if not data or len(data)>CHUNK or offset<0 or offset+len(data)>total:
            raise YouTubePrivateError("Unsafe resumable upload chunk.")
        head={"Content-Type":"video/mp4",
              "Content-Range":f"bytes {offset}-{offset+len(data)-1}/{total}"}
        status,headers,body=self._request("PUT",session,token,data,head)
        if status in (200,201):
            video=_json(body)
            vid=video.get("id")
            if not isinstance(vid,str) or not VIDEO.fullmatch(vid):
                raise YouTubePrivateError("Upload acknowledged without valid video ID.")
            if offset+len(data)!=total:
                raise YouTubePrivateError("Premature upload completion response.")
            return status,vid
        if status==308:
            expected=f"bytes=0-{offset+len(data)-1}"
            if headers.get("range")!=expected:
                raise YouTubePrivateError("Unexpected YouTube resumable range; manual recovery.")
            return status,offset+len(data)
        raise YouTubePrivateError("YouTube chunk rejected; manual recovery only.")

    def verify(self,token:str,video_id:str,channel_id:str)->dict:
        if not VIDEO.fullmatch(video_id) or not CHANNEL.fullmatch(channel_id):
            raise YouTubePrivateError("Invalid owner verification identifiers.")
        query=urlencode({"part":"snippet,status,processingDetails","id":video_id,
                         "fields":"items(id,snippet/channelId,status/privacyStatus,"
                                  "status/uploadStatus,processingDetails/processingStatus)"})
        status,_,body=self._request("GET",GET_URL+"?"+query,token)
        if status!=200:raise YouTubePrivateError("Cannot check owner video privacy.")
        data=_json(body)
        items=data.get("items")
        if not isinstance(items,list) or len(items)!=1:
            raise YouTubePrivateError("Uploaded video not visible to authenticated owner.")
        item=items[0]
        if (not isinstance(item,dict) or item.get("id")!=video_id or
            not isinstance(item.get("snippet"),dict) or
            item["snippet"].get("channelId")!=channel_id or
            not isinstance(item.get("status"),dict) or
            item["status"].get("privacyStatus")!="private"):
            raise YouTubePrivateError("Video/channel/private visibility mismatch; never publish.")
        processing=item.get("processingDetails",{})
        if not isinstance(processing,dict):
            raise YouTubePrivateError("Malformed owner processing status.")
        return {
            "video_id":video_id,"channel_id":channel_id,
            "privacy_status":"private",
            "processing_status":processing.get("processingStatus","UNKNOWN"),
            "verified_using_authenticated_youtube_api":True,
        }


def private_upload(plan:dict,media:Path,readiness:Path,readiness_sha:str,
                   journal:UploadJournal,token:str, *,
                   transport:Any|None=None,
                   before_network:Callable[[],None]|None=None,
                   token_provider:Callable[[],str]|None=None)->dict:
    """Never auto-retry. A pending/failed POST or PUT requires manual recovery."""
    safe=validate_plan(plan,media,readiness,readiness_sha)
    if not isinstance(token,str) or len(token)<30 or any(ch.isspace() for ch in token):
        raise YouTubePrivateError("Fresh OAuth bearer required from private environment.")
    metadata={"snippet":{
        "title":plan["title"].strip(),
        "description":plan["description"],
        "categoryId":plan["category_id"],
    },"status":{
        "privacyStatus":"private",
        "selfDeclaredMadeForKids":plan["made_for_kids"],
        "containsSyntheticMedia":plan["contains_synthetic_media"],
    }}
    transport=transport if transport is not None else GoogleYouTubeTransport()
    def current_token()->str:
        fresh=token_provider() if token_provider else token
        if not isinstance(fresh,str) or len(fresh)<30 or any(c.isspace() for c in fresh):
            raise YouTubePrivateError("Pi fresh OAuth token unavailable during upload.")
        return fresh
    plan_sha=hashlib.sha256(json.dumps(plan,sort_keys=True,
                separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    # This is the LAST step before network: persist the single attempt.
    journal.reserve(plan["render_job_id"],safe["master_sha256"],plan_sha)
    try:
        if before_network is not None:
            before_network()
        session=transport.start(current_token(),metadata,safe["master_bytes"])
        offset=0
        with Path(media).open("rb") as stream:
            while offset<safe["master_bytes"]:
                stream.seek(offset)
                block=stream.read(min(CHUNK,safe["master_bytes"]-offset))
                if not block:
                    raise YouTubePrivateError("Approved MP4 truncated during upload.")
                status,next_position=transport.put_chunk(
                    current_token(),session,block,offset,safe["master_bytes"])
                if status in (200,201):
                    video_id=next_position
                    if not isinstance(video_id,str) or not VIDEO.fullmatch(video_id):
                        raise YouTubePrivateError("Invalid final upload receipt.")
                    if file_sha256(Path(media))!=safe["master_sha256"]:
                        raise YouTubePrivateError("MP4 modified during upload; manual reconciliation.")
                    journal.record_uploaded(plan["render_job_id"],video_id)
                    result=transport.verify(current_token(),video_id,plan["target_channel_id"])
                    if (result.get("video_id")!=video_id or
                        result.get("channel_id")!=plan["target_channel_id"] or
                        result.get("privacy_status")!="private" or
                        result.get("verified_using_authenticated_youtube_api") is not True):
                        raise YouTubePrivateError("Privacy proof missing/invalid.")
                    if result.get("processing_status")!="succeeded":
                        # No owner review until processing actually succeeds.
                        # The recorded upload ID can be re-verified without
                        # another videos.insert call or duplicate upload.
                        return {
                            "schema_version":1,
                            "schema_version":1,
                            "status":"YOUTUBE_PRIVATE_PROCESSING_PENDING",
                            "series_id":safe["series_id"],
                            "episode_number":safe["episode_number"],
                            "video_id":video_id,"render_job_id":plan["render_job_id"],
                            "video_sha256":safe["master_sha256"],
                            "channel_id":plan["target_channel_id"],
                            "youtube_privacy":"private",
                            "processing_status":result.get("processing_status"),
                            "platform_privacy_verified":True,
                            "ready_for_owner_review":False,
                            "public_release_authorized":False,
                        }
                    journal.record_verified(plan["render_job_id"],video_id)
                    return {
                        "schema_version":1,
                        "status":"YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
                        "series_id":safe["series_id"],
                        "episode_number":safe["episode_number"],
                        "render_job_id":plan["render_job_id"],
                        "video_sha256":safe["master_sha256"],
                        "video_id":video_id,
                        "channel_id":plan["target_channel_id"],
                        "youtube_privacy":"private",
                        "processing_status":result.get("processing_status"),
                        "platform_privacy_verified":True,
                        "ready_for_owner_review":True,
                        "public_release_authorized":False,
                    }
                if status!=308 or type(next_position) is not int or next_position!=offset+len(block):
                    raise YouTubePrivateError("Invalid YouTube partial acknowledgment.")
                offset=next_position
        raise YouTubePrivateError("Upload exhausted without final video ID.")
    except Exception:
        # Deliberate STARTED/UPLOADED_UNVERIFIED quarantine: no retry.
        # Never print token, uploader URL or original media path.
        raise


def verify_existing(plan:dict,media:Path,readiness:Path,
                    readiness_sha:str,journal:UploadJournal,token:str,*,
                    transport:Any|None=None)->dict:
    """Read-only YouTube verification of prior completed upload, NO insert."""
    safe=validate_plan(plan,media,readiness,readiness_sha)
    if not isinstance(token,str) or len(token)<30 or any(ch.isspace() for ch in token):
        raise YouTubePrivateError("Fresh OAuth bearer required.")
    existing=journal.status(plan["render_job_id"])
    plan_sha=hashlib.sha256(json.dumps(plan,sort_keys=True,
                separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    if (not existing or existing["state"] not in (
            "UPLOADED_UNVERIFIED","PRIVATE_VERIFIED") or
            existing["plan_sha256"]!=plan_sha or
            existing["master_sha256"]!=safe["master_sha256"] or
            not isinstance(existing["video_id"],str) or
            not VIDEO.fullmatch(existing["video_id"])):
        raise YouTubePrivateError("No completed upload ID available for safe verification.")
    transport=transport if transport is not None else GoogleYouTubeTransport()
    result=transport.verify(token,existing["video_id"],plan["target_channel_id"])
    if (result.get("video_id")!=existing["video_id"] or
        result.get("channel_id")!=plan["target_channel_id"] or
        result.get("privacy_status")!="private" or
        result.get("verified_using_authenticated_youtube_api") is not True):
        raise YouTubePrivateError("Authenticated private video proof differs.")
    if result.get("processing_status")!="succeeded":
        return {"schema_version":1,
                "status":"YOUTUBE_PRIVATE_PROCESSING_PENDING",
                "series_id":safe["series_id"],
                "episode_number":safe["episode_number"],
                "render_job_id":plan["render_job_id"],
                "video_sha256":safe["master_sha256"],
                "video_id":existing["video_id"],
                "channel_id":plan["target_channel_id"],
                "youtube_privacy":"private",
                "processing_status":result.get("processing_status"),
                "platform_privacy_verified":True,
                "ready_for_owner_review":False,
                "public_release_authorized":False}
    if existing["state"]=="UPLOADED_UNVERIFIED":
        journal.record_verified(plan["render_job_id"],existing["video_id"])
    return {"schema_version":1,
            "status":"YOUTUBE_PRIVATE_VERIFIED_OWNER_REVIEW_PENDING",
            "series_id":safe["series_id"],
            "episode_number":safe["episode_number"],
            "render_job_id":plan["render_job_id"],
            "video_sha256":safe["master_sha256"],
            "video_id":existing["video_id"],
            "channel_id":plan["target_channel_id"],
            "youtube_privacy":"private",
            "processing_status":"succeeded",
            "platform_privacy_verified":True,
            "ready_for_owner_review":True,
            "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-youtube-private-upload",
        description="Strict private-only resumable upload; explicit --execute.")
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--media",type=Path,required=True)
    p.add_argument("--readiness",type=Path,required=True)
    p.add_argument("--readiness-sha256",required=True)
    p.add_argument("--journal",type=Path)
    p.add_argument("--token-env",default="KIDS_STUDIO_YOUTUBE_OAUTH_ACCESS_TOKEN")
    p.add_argument("--execute",action="store_true")
    p.add_argument("--verify-existing",action="store_true",
                   help="Check a prior upload ID without starting another upload")
    args=p.parse_args(argv)
    try:
        if not args.plan.is_absolute() or args.plan.is_symlink():
            raise YouTubePrivateError("Private absolute upload-plan JSON required.")
        _ensure_private(args.plan.parent.resolve())
        if not args.plan.is_file() or not 0<args.plan.stat().st_size<=16000:
            raise YouTubePrivateError("Owner upload plan missing/oversized.")
        plan=_json(args.plan.read_bytes())
        report=validate_plan(plan,args.media,args.readiness,args.readiness_sha256)
        if args.verify_existing and not args.execute:
            raise YouTubePrivateError("Verify-existing needs explicit --execute.")
        if not args.execute:
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return 0
        if args.journal is None or not ENV.fullmatch(args.token_env):
            raise YouTubePrivateError("Explicit private journal and allowed token env required.")
        if args.verify_existing:
            result=verify_existing(plan,args.media,args.readiness,
                args.readiness_sha256,UploadJournal(args.journal),
                os.environ.get(args.token_env,""))
        else:
            result=private_upload(plan,args.media,args.readiness,args.readiness_sha256,
                UploadJournal(args.journal),
                os.environ.get(args.token_env,""))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (YouTubePrivateError,OSError,ValueError,KeyError,TypeError,
            sqlite3.DatabaseError) as exc:
        print("PRIVATE_UPLOAD_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
