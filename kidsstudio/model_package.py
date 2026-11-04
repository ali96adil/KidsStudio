"""M41 pinned multi-file model checkpoint packages, offline and read-only.

Real HF/MLX checkpoints are commonly directory trees, not one .gguf file.
The model package's SHA is the SHA256 of its exact *model_files.json* bytes,
but acceptance requires rehashing EVERY registered file and rejecting all
unlisted files, symlinks and path traversal on EVERY verification.
A manifest digest alone is never model-byte integrity proof.

This attests only byte identity and bounded local layout; no model is
installed, downloaded, executed, licensed or considered capable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

from .episode_assembly import _ensure_private, digest

SHA=re.compile(r"^[a-f0-9]{64}$")
PACKAGE_NAME="model_files.json"
PACKAGE_FORMAT="kidsstudio_sharded_model_v1"
MAX_FILES=128
MAX_MANIFEST_BYTES=100_000
MAX_PACKAGE_BYTES=35_000_000_000
MAX_FILE_BYTES=7_000_000_000
EXTENSIONS=frozenset({
    ".safetensors",".gguf",".bin",".json",".txt",".model",
    ".vocab",".tiktoken",".merges"
})
SINGLE_FILE_EXTENSIONS=frozenset({".bin",".gguf",".safetensors"})


class ModelPackageError(ValueError):
    """A checkpoint package is not a complete, unchanged local artifact."""


def _path(file:str|Path,*,private_root:Path|str|None=None)->Path:
    raw=Path(file).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise ModelPackageError("Checkpoint must be an absolute, non-symlink source.")
    p=raw.resolve()
    _ensure_private(p if p.is_dir() else p.parent)
    if p.is_dir() and (p.stat().st_mode & 0o022):
        raise ModelPackageError("Checkpoint directory cannot be writable by others.")
    if private_root is not None:
        root=Path(private_root).expanduser()
        if not root.is_absolute() or root.is_symlink() or not p.is_relative_to(
                root.resolve()):
            raise ModelPackageError("Checkpoint outside approved private root.")
    return p


def _layout(root:Path)->tuple[dict,bytes]:
    manifest=root/PACKAGE_NAME
    if (not manifest.is_file() or manifest.is_symlink()
        or not 100<=manifest.stat().st_size<=MAX_MANIFEST_BYTES or
        (manifest.stat().st_mode & 0o022)):
        raise ModelPackageError("Pinned model-files.json is absent or oversized.")
    raw=manifest.read_bytes()
    try:doc=json.loads(raw.decode("utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise ModelPackageError("Invalid model package JSON.") from exc
    if (not isinstance(doc,dict) or set(doc)!={"schema_version","format",
           "files","inference_qualified","public_release_authorized"} or
        doc["schema_version"]!=1 or doc["format"]!=PACKAGE_FORMAT or
        doc["inference_qualified"] is not False or
        doc["public_release_authorized"] is not False or
        not isinstance(doc["files"],list) or
        not 2<=len(doc["files"])<=MAX_FILES):
        raise ModelPackageError("Model package requires full explicit file list.")
    listed=set()
    total=0
    has_model=False
    for row in doc["files"]:
        if not isinstance(row,dict) or set(row)!={"path","sha256","bytes"}:
            raise ModelPackageError("Each model file must bind path, bytes and SHA.")
        name=row["path"]
        if (not isinstance(name,str) or not 1<=len(name)<=200 or
            "\\" in name or "\x00" in name):
            raise ModelPackageError("Untrusted package filename.")
        part=PurePosixPath(name)
        if (part.is_absolute() or any(segment in ("",".","..")
             or segment.startswith(".") for segment in part.parts) or
            name in listed or part.as_posix()!=name or name==PACKAGE_NAME or
            part.suffix.lower() not in EXTENSIONS):
            raise ModelPackageError("Duplicate, executable or escaping model path.")
        if (not isinstance(row["sha256"],str) or
            not SHA.fullmatch(row["sha256"]) or
            type(row["bytes"]) is not int or
            not 0<row["bytes"]<=MAX_FILE_BYTES):
            raise ModelPackageError("Invalid package member SHA/size.")
        candidate=root.joinpath(*part.parts)
        if (not candidate.is_file() or candidate.is_symlink()
            or not candidate.resolve().is_relative_to(root) or
            candidate.stat().st_size!=row["bytes"] or
            (candidate.stat().st_mode & 0o022) or
            digest(candidate)!=row["sha256"]):
            raise ModelPackageError("A model member is missing, mutated or symlinked.")
        listed.add(name)
        total+=row["bytes"]
        if total>MAX_PACKAGE_BYTES:
            raise ModelPackageError("Model package exceeds bounded offline limit.")
        has_model|=part.suffix.lower() in SINGLE_FILE_EXTENSIONS
    if not has_model:
        raise ModelPackageError("Tokenizer/config alone is not a model checkpoint.")
    discovered=set()
    for base,folders,files in os.walk(root,followlinks=False):
        current=Path(base)
        for folder in folders:
            path=current/folder
            if path.is_symlink() or not path.is_dir():
                raise ModelPackageError("Untrusted symlink or directory in checkpoint.")
        for fname in files:
            source=current/fname
            relative=source.relative_to(root).as_posix()
            if source.is_symlink() or not source.is_file():
                raise ModelPackageError("Package contains non-regular or symlinked file.")
            if relative!=PACKAGE_NAME:
                discovered.add(relative)
    if discovered!=listed:
        raise ModelPackageError("Unlisted or missing model checkpoint contents.")
    if digest(manifest)!=hashlib.sha256(raw).hexdigest():
        raise ModelPackageError("Package manifest changed during inspection.")
    return doc,raw


def verify_checkpoint(file:str|Path,expected_sha256:str, *,
                      private_root:Path|str|None=None,
                      allow_directory:bool=True)->Path:
    """Rehash a single checkpoint or an entire explicitly pinned directory."""
    if (not isinstance(expected_sha256,str) or
        not SHA.fullmatch(expected_sha256)):
        raise ModelPackageError("Exact checkpoint/package SHA256 required.")
    p=_path(file,private_root=private_root)
    if p.is_file():
        if (p.suffix.lower() not in SINGLE_FILE_EXTENSIONS or
            not 100<=p.stat().st_size<=MAX_FILE_BYTES or
            digest(p)!=expected_sha256):
            raise ModelPackageError("Single-file checkpoint changed or unsupported.")
    elif p.is_dir() and allow_directory:
        _,raw=_layout(p)
        if hashlib.sha256(raw).hexdigest()!=expected_sha256:
            raise ModelPackageError("Package manifest differs from pinned digest.")
    else:
        raise ModelPackageError("Checkpoint file or pinned model directory missing.")
    return p


def checkpoint_digest(file:str|Path)->str:
    """Recheck package content before returning its reproducible SHA.

    Unlike Path.read_bytes on a directory, this works for sharded models.
    A changed member raises, not merely a new fingerprint.
    """
    p=_path(file)
    if p.is_file():
        if p.suffix.lower() not in SINGLE_FILE_EXTENSIONS or not (
                100<=p.stat().st_size<=MAX_FILE_BYTES):
            raise ModelPackageError("Unapproved checkpoint file.")
        return digest(p)
    if p.is_dir():
        _,raw=_layout(p)
        return hashlib.sha256(raw).hexdigest()
    raise ModelPackageError("Checkpoint vanished.")


def freeze_model_directory(directory:str|Path,*,execute:bool=False)->dict:
    """One-time private manifest creation. Default computes without writing.

    File extensions are a data-only allowlist; no .py or executable model
    plugins are imported or trusted. A freeze is a byte pin, not a license
    review or a model evaluation.
    """
    if type(execute) is not bool:
        raise ModelPackageError("Explicit execute boolean required.")
    root=_path(directory)
    if not root.is_dir() or (root.stat().st_mode & 0o022):
        raise ModelPackageError("Owner model directory must be private and writable only by owner.")
    manifest=root/PACKAGE_NAME
    if manifest.exists() or manifest.is_symlink():
        raise ModelPackageError("Previously frozen model package cannot be replaced.")
    names=[]
    for base,dirs,files in os.walk(root,followlinks=False):
        parent=Path(base)
        for folder in dirs:
            p=parent/folder
            if p.is_symlink() or folder.startswith("."):
                raise ModelPackageError("Hidden or symlinked directories not permitted.")
        for name in files:
            source=parent/name
            relative=source.relative_to(root).as_posix()
            part=PurePosixPath(relative)
            if (source.is_symlink() or not source.is_file() or
                any(x.startswith(".") for x in part.parts) or
                part.suffix.lower() not in EXTENSIONS or
                part.as_posix()!=relative):
                raise ModelPackageError("Executable, hidden or symlinked model member.")
            names.append((relative,source))
            if len(names)>MAX_FILES:
                raise ModelPackageError("Model package has too many member files.")
    if len(names)<2 or not any(
            PurePosixPath(n).suffix.lower() in SINGLE_FILE_EXTENSIONS
            for n,_ in names):
        raise ModelPackageError("Require model weights and accompanying tokenizer/config.")
    items=[]
    total=0
    for name,p in sorted(names):
        size=p.stat().st_size
        if not 0<size<=MAX_FILE_BYTES or (p.stat().st_mode & 0o022):
            raise ModelPackageError("Model member size outside bounded limits.")
        total+=size
        if total>MAX_PACKAGE_BYTES:
            raise ModelPackageError("Model checkpoint exceeds bounded storage.")
        items.append({"path":name,"sha256":digest(p),"bytes":size})
    doc={"schema_version":1,"format":PACKAGE_FORMAT,"files":items,
         "inference_qualified":False,"public_release_authorized":False}
    raw=(json.dumps(doc,sort_keys=True,ensure_ascii=False,
        indent=2,allow_nan=False)+"\n").encode("utf-8")
    if len(raw)>MAX_MANIFEST_BYTES:
        raise ModelPackageError("Manifest exceeds bounded size.")
    frozen_sha=hashlib.sha256(raw).hexdigest()
    result={"schema_version":1,"status":"M41_PACKAGE_PREPARED_NOT_WRITTEN",
            "package_sha256":frozen_sha,"member_count":len(items),
            "total_bytes":total,"model_executed":False,
            "model_quality_qualified":False,"mac_pi_hardware_qualified":False,
            "public_release_authorized":False}
    if not execute:
        return result
    fd=os.open(str(manifest),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    verify_checkpoint(root,frozen_sha)
    return {**result,"status":"M41_IMMUTABLE_PACKAGE_MANIFEST_CREATED",
            "write_performed":True}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-model-package")
    p.add_argument("--directory",type=Path,required=True)
    p.add_argument("--execute",action="store_true",
                   help="Explicitly freeze model_files.json once (no overwrite).")
    x=p.parse_args(argv)
    try:
        result=freeze_model_directory(x.directory,execute=x.execute)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ModelPackageError,OSError,ValueError,TypeError) as exc:
        print("M41_MODEL_PACKAGE_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
