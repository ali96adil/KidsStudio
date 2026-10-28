"""M8 immutable private episode archive: SHA-pinned source copies + verification.

No sync, web, public upload, Git LFS or external services. Intended for
owner-initiated OFFLINE archiving after technical and editorial review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from .episode_assembly import digest, _ensure_private

SHA=re.compile(r"^[a-f0-9]{64}$")
SID=re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
RUN=re.compile(r"^[a-z0-9][a-z0-9_-]{5,63}$")
ROLES={"episode_master","approved_script","voice_master","a2v_master",
       "technical_qa","owner_qa","agent_qa","scene_manifest","thumbnail","subtitles",
       "coloring_page","production_notes"}
REQUIRED={"episode_master","approved_script","technical_qa"}
MAX_ITEMS=32
MAX_ITEM_BYTES=20_000_000_000


class ArchiveError(ValueError):
    """Archive preflight, integrity or immutable storage violation."""


def _schema(file: str | Path) -> tuple[dict[str, Any],Path,str]:
    file=Path(file).expanduser()
    if not file.is_absolute() or file.is_symlink():
        raise ArchiveError("Archive plan must be an absolute non-symlink JSON file.")
    file=file.resolve()
    if not file.is_file() or not 0<file.stat().st_size<=100_000:
        raise ArchiveError("Archive plan missing or oversized.")
    _ensure_private(file.parent)
    try:
        body=json.loads(file.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise ArchiveError("Archive plan must be valid JSON.") from exc
    expected={"schema_version","series_id","episode_number","archive_id",
              "private_root","archive_root","items"}
    if not isinstance(body,dict) or set(body)!=expected or body["schema_version"]!=1:
        raise ArchiveError("Archive plan schema mismatch.")
    if not isinstance(body["series_id"],str) or not SID.fullmatch(body["series_id"]):
        raise ArchiveError("Invalid series ID.")
    if type(body["episode_number"]) is not int or not 1<=body["episode_number"]<=120:
        raise ArchiveError("Invalid episode number.")
    if not isinstance(body["archive_id"],str) or not RUN.fullmatch(body["archive_id"]):
        raise ArchiveError("Archive ID must be stable and uniquely assigned.")
    root=_ensure_private(Path(body["private_root"]))
    archive_root=_ensure_private(Path(body["archive_root"]))
    if (not root.is_dir() or archive_root==root
            or not archive_root.is_relative_to(root)):
        raise ArchiveError("Archive must be a distinct directory under private root.")
    if not isinstance(body["items"],list) or not 4<=len(body["items"])<=MAX_ITEMS:
        raise ArchiveError("Expected bounded archive files.")
    roles=set()
    origins=set()
    size=0
    for item in body["items"]:
        if not isinstance(item,dict) or set(item)!={"role","path","sha256"}:
            raise ArchiveError("Every archive source needs role/path/SHA256.")
        role=item["role"]
        source_name=item["path"]
        sha=item["sha256"]
        if role not in ROLES or role in roles:
            raise ArchiveError("Unknown or duplicate archive role.")
        if (not isinstance(source_name,str) or not source_name.startswith("/")
                or not isinstance(sha,str) or not SHA.fullmatch(sha)):
            raise ArchiveError("Archive needs absolute sources with exact SHA256.")
        source=Path(source_name)
        if source.is_symlink():
            raise ArchiveError("Source symlinks are forbidden.")
        source=source.resolve()
        if (not source.is_relative_to(root) or source.is_relative_to(archive_root)
                or not source.is_file() or source in origins
                or not 0<source.stat().st_size<=MAX_ITEM_BYTES):
            raise ArchiveError("Source unavailable, duplicate, outside root or oversized.")
        if role=="episode_master" and source.suffix.lower()!=".mp4":
            raise ArchiveError("Episode master must be an MP4.")
        if digest(source)!=sha:
            raise ArchiveError("Source differs from its recorded owner-approved SHA256.")
        roles.add(role)
        origins.add(source)
        size+=source.stat().st_size
    if (not REQUIRED.issubset(roles) or
        ("owner_qa" in roles)==("agent_qa" in roles)):
        raise ArchiveError("Master, script, technical QA and exactly one owner/agent QA required.")
    return body,archive_root,digest(file)


def preflight(plan: str | Path) -> dict[str, Any]:
    body,archive_root,plan_sha=_schema(plan)
    target=(archive_root/body["series_id"]/
            f"ep{body['episode_number']:03d}"/body["archive_id"])
    if target.exists() or target.is_symlink():
        raise ArchiveError("Archive run ID exists; never overwrite.")
    bytes_needed=sum(Path(x["path"]).stat().st_size for x in body["items"])
    ancestor=archive_root
    while not ancestor.exists():
        ancestor=ancestor.parent
    available=shutil.disk_usage(ancestor).free
    if available < bytes_needed + 100*1024**2:
        raise ArchiveError("Insufficient free disk for archive with safety margin.")
    return {
        "status":"ARCHIVE_PREFLIGHT_READY_NOT_COPIED",
        "series_id":body["series_id"],"episode_number":body["episode_number"],
        "archive_id":body["archive_id"],"source_count":len(body["items"]),
        "total_bytes":bytes_needed,"plan_sha256":plan_sha,
        "publishing_approved":False,
    }


def archive(plan: str | Path) -> dict[str, Any]:
    checked=preflight(plan)
    body,archive_root,_=_schema(plan)
    target=(archive_root/body["series_id"]/
            f"ep{body['episode_number']:03d}"/body["archive_id"])
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    target.mkdir(mode=0o700)
    files=[]
    try:
        for i,item in enumerate(body["items"],1):
            source=Path(item["path"]).resolve()
            # Recheck immediately before copying; a changed source must fail.
            if digest(source)!=item["sha256"]:
                raise ArchiveError("Source mutated during archive operation.")
            suffix=source.suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,8}",suffix):
                suffix=".bin"
            name=f"{i:02d}_{item['role']}{suffix}"
            dest=target/name
            with source.open("rb") as inp, dest.open("xb") as out:
                os.chmod(dest,0o600)
                shutil.copyfileobj(inp,out,length=1024*1024)
                out.flush()
                os.fsync(out.fileno())
            if (digest(dest)!=item["sha256"] or
                    digest(source)!=item["sha256"]):
                raise ArchiveError("Archive copy/source integrity mismatch.")
            files.append({"role":item["role"],"file":name,
                          "sha256":item["sha256"],
                          "bytes":dest.stat().st_size})
        manifest={
            "schema_version":1,"series_id":body["series_id"],
            "episode_number":body["episode_number"],
            "archive_id":body["archive_id"],
            "created_at":datetime.now(timezone.utc).isoformat(),
            "source_plan_sha256":checked["plan_sha256"],
            "files":files,"publication_approved":False
        }
        with (target/"archive_manifest.json").open("x",encoding="utf-8") as out:
            json.dump(manifest,out,indent=2,ensure_ascii=False)
            out.write("\n")
            out.flush();os.fsync(out.fileno())
        return verify_archive(target)
    except BaseException:
        # Leave run folder for manual inspection. Never remove archive
        # artifacts following partial copying, and do not silently retry.
        raise


def verify_archive(directory: str | Path) -> dict[str, Any]:
    target=Path(directory).expanduser()
    if not target.is_absolute() or target.is_symlink():
        raise ArchiveError("Archive location must be absolute and not a symlink.")
    target=target.resolve()
    if any((p/".git").exists() for p in (target,*target.parents)):
        raise ArchiveError("Private archive cannot be in a Git checkout.")
    f=target/"archive_manifest.json"
    if f.is_symlink() or not f.is_file() or f.stat().st_size>100_000:
        raise ArchiveError("Missing or invalid finalized archive manifest.")
    try:
        manifest=json.loads(f.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise ArchiveError("Archive manifest corrupted.") from exc
    required={"schema_version","series_id","episode_number","archive_id",
              "created_at","source_plan_sha256","files","publication_approved"}
    if not isinstance(manifest,dict) or set(manifest)!=required or (
            manifest["schema_version"]!=1 or manifest["publication_approved"] is not False):
        raise ArchiveError("Archive is not a private owner-controlled snapshot.")
    if (not isinstance(manifest["series_id"],str) or not SID.fullmatch(manifest["series_id"])
        or type(manifest["episode_number"]) is not int
        or not 1<=manifest["episode_number"]<=120
        or not isinstance(manifest["archive_id"],str) or not RUN.fullmatch(manifest["archive_id"])
        or not isinstance(manifest["source_plan_sha256"],str)
        or not SHA.fullmatch(manifest["source_plan_sha256"])):
        raise ArchiveError("Archive identity or plan digest invalid.")
    if (target.name!=manifest["archive_id"] or
        target.parent.name!=f"ep{manifest['episode_number']:03d}" or
        target.parent.parent.name!=manifest["series_id"]):
        raise ArchiveError("Manifest archive identity/path mismatch.")
    entries=manifest["files"]
    if not isinstance(entries,list) or not 4<=len(entries)<=MAX_ITEMS:
        raise ArchiveError("Invalid archive entry count.")
    roles=set()
    names=set()
    bytes_total=0
    for item in entries:
        if not isinstance(item,dict) or set(item)!={"role","file","sha256","bytes"}:
            raise ArchiveError("Invalid archived item schema.")
        role,name,sha,expected_size=item["role"],item["file"],item["sha256"],item["bytes"]
        if (role not in ROLES or role in roles or not isinstance(name,str)
             or name in names or not re.fullmatch(
                 r"[0-9]{2}_[a-z_]+\.[a-z0-9]{1,8}",name)
             or not isinstance(sha,str) or not SHA.fullmatch(sha)
             or type(expected_size) is not int or expected_size<=0):
            raise ArchiveError("Unsafe archive entry.")
        file=target/name
        if (file.is_symlink() or not file.is_file() or file.stat().st_size!=expected_size
                or digest(file)!=sha):
            raise ArchiveError("Archived bytes missing, changed or substituted.")
        roles.add(role); names.add(name)
        bytes_total+=expected_size
    if (not REQUIRED.issubset(roles) or
        ("owner_qa" in roles)==("agent_qa" in roles)):
        raise ArchiveError("Master, script, technical QA and exactly one owner/agent QA required.")
    if {x.name for x in target.iterdir()} != names|{"archive_manifest.json"}:
        raise ArchiveError("Unexpected or incomplete archive contents.")
    return {
        "status":"ARCHIVE_VERIFIED_NOT_PUBLISHED",
        "series_id":manifest["series_id"],
        "episode_number":manifest["episode_number"],
        "archive_id":manifest["archive_id"],
        "archive_manifest_sha256":digest(f),
        "file_count":len(entries),"total_bytes":bytes_total,
        "files":[{"role":x["role"],"sha256":x["sha256"]} for x in entries],
        "publishing_approved":False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog="studio-archive")
    p.add_argument("--plan",type=Path)
    p.add_argument("--verify",type=Path)
    p.add_argument("--create",action="store_true")
    args=p.parse_args(argv)
    if bool(args.plan)==bool(args.verify) or (args.create and not args.plan):
        p.error("Use --verify PATH or --plan PLAN [--create].")
    try:
        result=(verify_archive(args.verify) if args.verify else
                archive(args.plan) if args.create else preflight(args.plan))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ArchiveError,OSError,ValueError) as exc:
        print("STUDIO_ARCHIVE_ERROR: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
