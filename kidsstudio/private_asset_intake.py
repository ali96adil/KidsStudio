"""M11 owner-opt-in, non-destructive Bunny reference import into Mac worker root.

M10 inventory can reference the original ComfyUI-Shared Bunny image, while
M6 StagePlan allows inputs only within its private_root. This explicitly
copies, verifies and versions the approved original without changing it.
No file is copied until --execute is supplied. No Git/cloud transmission.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from .episode_assembly import _ensure_private, digest

SHA=re.compile(r"^[a-f0-9]{64}$")
ID=re.compile(r"^[a-z][a-z0-9_-]{3,63}$")
PNG_MAGIC=b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES=120_000_000


class IntakeError(ValueError):
    """Imported source, owner approval or immutable copy is invalid."""


def _source_file(source: str | Path, source_root: str | Path,
                 expected_sha: str) -> Path:
    if not isinstance(expected_sha,str) or not SHA.fullmatch(expected_sha):
        raise IntakeError("Explicit original Bunny SHA256 required.")
    original=Path(source).expanduser()
    approved_root=Path(source_root).expanduser()
    if (not original.is_absolute() or original.is_symlink() or
        not approved_root.is_absolute() or approved_root.is_symlink()):
        raise IntakeError("Original and approved source root must be absolute non-symlinks.")
    root=_ensure_private(approved_root)
    original=original.resolve()
    if (not root.is_dir() or not original.is_relative_to(root) or
        not original.is_file() or original.suffix.lower()!=".png" or
        not 8<original.stat().st_size<=MAX_PNG_BYTES):
        raise IntakeError("Original PNG unavailable or outside approved private source.")
    with original.open("rb") as stream:
        if stream.read(8)!=PNG_MAGIC:
            raise IntakeError("Original Bunny reference is not a valid PNG header.")
    if digest(original)!=expected_sha:
        raise IntakeError("Original PNG has changed since owner approved its hash.")
    return original


def _target(primary_root: str | Path, asset_id: str) -> Path:
    if not isinstance(asset_id,str) or not ID.fullmatch(asset_id):
        raise IntakeError("Stable lower-case asset_id required.")
    raw=Path(primary_root).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise IntakeError("Production root must be absolute and not a symlink.")
    root=_ensure_private(raw)
    if not root.is_dir():
        raise IntakeError("Production root does not exist.")
    return root/"assets"/"imports"/asset_id


def preview_import(source: str | Path, *, approved_source_root: str | Path,
                   private_root: str | Path, asset_id: str,
                   original_sha256: str) -> dict[str, Any]:
    original=_source_file(source,approved_source_root,original_sha256)
    target=_target(private_root,asset_id)
    if target.exists() or target.is_symlink() or original.is_relative_to(target):
        raise IntakeError("Import ID already used or collides with source.")
    return {
        "schema_version":1,
        "status":"ORIGINAL_PIN_VALID_IMPORT_NOT_PERFORMED",
        "asset_id":asset_id,"original_sha256":original_sha256,
        "bytes":original.stat().st_size,
        "original_modified":False,"import_performed":False,
        "publication_authorized":False,
    }


def import_bunny(source: str | Path, *, approved_source_root: str | Path,
                 private_root: str | Path, asset_id: str,
                 original_sha256: str) -> dict[str, Any]:
    preview_import(source,approved_source_root=approved_source_root,
                   private_root=private_root,asset_id=asset_id,
                   original_sha256=original_sha256)
    src=_source_file(source,approved_source_root,original_sha256)
    target=_target(private_root,asset_id)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    target.mkdir(mode=0o700)  # never overwrite another asset revision
    dest=target/"bunny_reference.png"
    with src.open("rb") as inp, dest.open("xb") as out:
        os.chmod(dest,0o600)
        shutil.copyfileobj(inp,out,length=1024*1024)
        out.flush()
        os.fsync(out.fileno())
    if digest(dest)!=original_sha256 or digest(src)!=original_sha256:
        raise IntakeError("Original or imported PNG changed while copying.")
    record={
        "schema_version":1,"asset_id":asset_id,
        "original_sha256":original_sha256,"imported_sha256":digest(dest),
        "bytes":dest.stat().st_size,
        "source_modified":False,"publication_authorized":False,
    }
    with (target/"intake_receipt.json").open("x",encoding="utf-8") as out:
        json.dump(record,out,indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    return {**record,
            "status":"ORIGINAL_COPY_VERIFIED_PRIVATE_ONLY",
            "import_performed":True}


def verify_import(private_root: str | Path,asset_id: str,
                  expected_sha256: str) -> dict[str, Any]:
    target=_target(private_root,asset_id)
    if not isinstance(expected_sha256,str) or not SHA.fullmatch(expected_sha256):
        raise IntakeError("Exact approved import digest required.")
    dest=target/"bunny_reference.png"
    receipt=target/"intake_receipt.json"
    if (dest.is_symlink() or receipt.is_symlink() or not dest.is_file()
        or not receipt.is_file() or
        {item.name for item in target.iterdir()}!={"bunny_reference.png","intake_receipt.json"}):
        raise IntakeError("Incomplete or modified import directory.")
    try:
        record=json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise IntakeError("Original import receipt corrupted.") from exc
    fields={"schema_version","asset_id","original_sha256","imported_sha256",
            "bytes","source_modified","publication_authorized"}
    if (not isinstance(record,dict) or set(record)!=fields
        or record["schema_version"]!=1 or record["asset_id"]!=asset_id
        or record["original_sha256"]!=expected_sha256
        or record["imported_sha256"]!=expected_sha256
        or record["source_modified"] is not False
        or record["publication_authorized"] is not False
        or record["bytes"]!=dest.stat().st_size
        or digest(dest)!=expected_sha256):
        raise IntakeError("Private Bunny reference import failed its integrity proof.")
    return {"status":"PRIVATE_REFERENCE_COPY_VERIFIED",
            "asset_id":asset_id,"sha256":expected_sha256,
            "bytes":dest.stat().st_size,
            "source_modified":False,"publication_authorized":False}


def main(argv=None):
    p=argparse.ArgumentParser(prog="studio-import-bunny")
    p.add_argument("--source",type=Path)
    p.add_argument("--approved-source-root",type=Path)
    p.add_argument("--private-root",type=Path,required=True)
    p.add_argument("--asset-id",required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--execute",action="store_true")
    p.add_argument("--verify",action="store_true")
    args=p.parse_args(argv)
    if args.verify and (args.execute or args.source or args.approved_source_root):
        p.error("Verify only accepts --private-root, --asset-id and --sha256.")
    if not args.verify and (args.source is None or args.approved_source_root is None):
        p.error("Source and approved source root required for preflight/import.")
    try:
        if args.verify:
            result=verify_import(args.private_root,args.asset_id,args.sha256)
        else:
            call=import_bunny if args.execute else preview_import
            result=call(args.source,approved_source_root=args.approved_source_root,
                        private_root=args.private_root,asset_id=args.asset_id,
                        original_sha256=args.sha256)
    except (IntakeError,OSError,ValueError) as exc:
        print("PRIVATE_ASSET_INTAKE_ERROR: "+str(exc),file=sys.stderr)
        return 2
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
