"""M44 offline owner-ATTESTED model origin and license evidence.

A pinned, HMAC-authenticated local receipt binds source claims, model
package bytes and a copied license text. It cannot prove that a claimed
Hugging Face revision was actually downloaded, that all dependencies
are licensed, or that a lawyer approved commercial use. Accordingly
M44 permits only a constrained *local diagnostic*, never a YouTube upload.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys

from .episode_assembly import _ensure_private,digest
from .model_package import verify_checkpoint,ModelPackageError

SHA=re.compile(r"^[a-f0-9]{64}$")
REVISION=re.compile(r"^[0-9a-f]{40}$")
FIELDS=frozenset({
    "schema_version","checkpoint_package_sha256","upstream_provider",
    "upstream_repository","upstream_revision","source_identity",
    "model_variant","license_spdx_claim","license_copy_path",
    "license_copy_sha256","source_reviewed_by_owner",
    "license_reviewed_by_owner","usage_scope","owner_review_note",
    "model_quality_qualified","youtube_private_upload_authorized",
    "public_release_authorized"})
SIGNED_FIELDS=FIELDS|{"owner_hmac_sha256"}


class ModelOriginError(ValueError):
    pass


def _data(raw:bytes)->dict:
    try:obj=json.loads(raw.decode("utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise ModelOriginError("Malformed private model provenance JSON.") from exc
    if not isinstance(obj,dict) or not all(
        isinstance(k,str) for k in obj):
        raise ModelOriginError("Expected private provenance dictionary.")
    return obj


def _canonical(data:dict)->bytes:
    return json.dumps(data,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")


def _private(path:str|Path,*,minimum:int=100,
             maximum:int=100000)->Path:
    p=Path(path).expanduser()
    if not p.is_absolute() or p.is_symlink() or not p.is_file():
        raise ModelOriginError("Existing absolute non-symlink private evidence required.")
    p=p.resolve()
    _ensure_private(p.parent)
    if (not minimum<=p.stat().st_size<=maximum or
        (p.stat().st_mode & 0o022) or
        (p.parent.stat().st_mode & 0o022)):
        raise ModelOriginError("Source/license attestation must be owner-private.")
    return p


def _check_claim(doc:dict,model_sha:str,variant:str)->str:
    if (set(doc)!=FIELDS or doc["schema_version"]!=1 or
        doc["checkpoint_package_sha256"]!=model_sha or
        doc["upstream_provider"]!="huggingface" or
        doc["upstream_repository"]!="Qwen/Qwen2.5-Omni-7B" or
        not isinstance(doc["upstream_revision"],str) or
        not REVISION.fullmatch(doc["upstream_revision"]) or
        doc["source_identity"]!="official_repository_claim" or
        doc["model_variant"]!="7b" or variant!="7b" or
        doc["license_spdx_claim"]!="Apache-2.0" or
        doc["source_reviewed_by_owner"] is not True or
        doc["license_reviewed_by_owner"] is not True or
        doc["usage_scope"]!="local_diagnostic_only" or
        doc["model_quality_qualified"] is not False or
        doc["youtube_private_upload_authorized"] is not False or
        doc["public_release_authorized"] is not False or
        not isinstance(doc["owner_review_note"],str) or
        not 30<=len(doc["owner_review_note"].strip())<=1000 or
        not isinstance(doc["license_copy_sha256"],str) or
        not SHA.fullmatch(doc["license_copy_sha256"])):
        raise ModelOriginError("Only explicitly reviewed 7B local diagnostic claims accepted.")
    copied=_private(doc["license_copy_path"],minimum=200,maximum=100000)
    if digest(copied)!=doc["license_copy_sha256"]:
        raise ModelOriginError("Pinned license copy changed.")
    contents=copied.read_text(encoding="utf-8",errors="strict")
    if ("Apache License" not in contents or
        "Version 2.0" not in contents or
        "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION"
        not in contents):
        raise ModelOriginError("Attached copy does not resemble Apache 2.0 text.")
    return digest(copied)


def verify_origin(*,model:str|Path,model_sha256:str,
                  receipt:str|Path,receipt_sha256:str,
                  owner_key:bytes,variant:str="7b")->dict:
    if (not isinstance(receipt_sha256,str) or
        not SHA.fullmatch(receipt_sha256) or
        not isinstance(owner_key,bytes) or len(owner_key)<32):
        raise ModelOriginError("Pinned receipt and private owner signer required.")
    verify_checkpoint(model,model_sha256,allow_directory=True)
    path=_private(receipt,minimum=250,maximum=25000)
    if digest(path)!=receipt_sha256:
        raise ModelOriginError("Receipt bytes differ from owner pin.")
    record=_data(path.read_bytes())
    if set(record)!=SIGNED_FIELDS or not isinstance(
            record["owner_hmac_sha256"],str) or not SHA.fullmatch(
            record["owner_hmac_sha256"]):
        raise ModelOriginError("Expected one signed exact owner receipt.")
    unsigned={key:record[key] for key in FIELDS}
    _check_claim(unsigned,model_sha256,variant)
    expected=hmac.new(owner_key,_canonical(unsigned),
                      hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,record["owner_hmac_sha256"]):
        raise ModelOriginError("Model/license claim not signed by owner.")
    return {
        "schema_version":1,
        "status":"M44_OWNER_ATTESTED_ORIGIN_BYTES_NOT_INDEPENDENTLY_VERIFIED",
        "checkpoint_package_sha256":model_sha256,
        "receipt_sha256":receipt_sha256,
        "license_copy_sha256":unsigned["license_copy_sha256"],
        "model_variant":"7b","license_spdx_claim":"Apache-2.0",
        "source_claim":"Qwen/Qwen2.5-Omni-7B",
        "owner_attestation_verified":True,
        "upstream_snapshot_independently_verified":False,
        "license_legally_adjudicated":False,
        "third_party_licenses_verified":False,
        "local_diagnostic_only":True,
        "model_quality_qualified":False,
        "private_upload_permitted":False,
        "public_release_authorized":False,
    }


def sign_origin_draft(*,model:str|Path,model_sha256:str,
                      draft:str|Path,draft_sha256:str,
                      owner_key:bytes,out:str|Path,
                      execute:bool=False)->dict:
    if (type(execute) is not bool or not isinstance(owner_key,bytes) or
        len(owner_key)<32 or not isinstance(draft_sha256,str) or
        not SHA.fullmatch(draft_sha256)):
        raise ModelOriginError("Owner-pinned draft and private signer required.")
    verify_checkpoint(model,model_sha256,allow_directory=True)
    src=_private(draft,minimum=250,maximum=25000)
    if digest(src)!=draft_sha256:
        raise ModelOriginError("Owner draft changed.")
    doc=_data(src.read_bytes())
    _check_claim(doc,model_sha256,"7b")
    target=Path(out).expanduser()
    if (not target.is_absolute() or target.exists() or target.is_symlink()
        or target.suffix.lower()!=".json" or
        not target.parent.is_dir() or target.parent.is_symlink()
        or (target.parent.stat().st_mode & 0o022)):
        raise ModelOriginError("Fresh private signed output path required.")
    _ensure_private(target.parent)
    signature=hmac.new(owner_key,_canonical(doc),
                       hashlib.sha256).hexdigest()
    record={**doc,"owner_hmac_sha256":signature}
    raw=(json.dumps(record,sort_keys=True,ensure_ascii=False,
         indent=2,allow_nan=False)+"\n").encode()
    pin=hashlib.sha256(raw).hexdigest()
    info={"status":"M44_OWNER_DRAFT_INSPECTED_NOT_SIGNED" if not execute
          else "M44_OWNER_LOCAL_ATTESTATION_CREATED",
          "receipt_sha256":pin,"checkpoint_package_sha256":model_sha256,
          "license_copy_sha256":doc["license_copy_sha256"],
          "writes_performed":execute,"local_diagnostic_only":True,
          "source_independently_verified":False,
          "commercial_license_legally_adjudicated":False,
          "public_release_authorized":False}
    if execute:
        fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        verify_origin(model=model,model_sha256=model_sha256,
                      receipt=target,receipt_sha256=pin,
                      owner_key=owner_key)
    return info


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-model-origin")
    p.add_argument("--model",type=Path,required=True)
    p.add_argument("--model-sha256",required=True)
    p.add_argument("--owner-key-env",default="KIDS_STUDIO_MODEL_ORIGIN_KEY")
    sub=p.add_subparsers(dest="action",required=True)
    q=sub.add_parser("inspect")
    q.add_argument("--draft",type=Path,required=True)
    q.add_argument("--draft-sha256",required=True)
    q.add_argument("--out",type=Path,required=True)
    q.add_argument("--execute",action="store_true")
    v=sub.add_parser("verify")
    v.add_argument("--receipt",type=Path,required=True)
    v.add_argument("--receipt-sha256",required=True)
    x=p.parse_args(argv)
    try:
        key=os.environ.get(x.owner_key_env,"").encode()
        if x.action=="inspect":
            result=sign_origin_draft(model=x.model,
                model_sha256=x.model_sha256,draft=x.draft,
                draft_sha256=x.draft_sha256,owner_key=key,
                out=x.out,execute=x.execute)
        else:
            result=verify_origin(model=x.model,
                model_sha256=x.model_sha256,receipt=x.receipt,
                receipt_sha256=x.receipt_sha256,owner_key=key)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ModelOriginError,ModelPackageError,OSError,ValueError,
            TypeError,KeyError,UnicodeError) as exc:
        print("M44_MODEL_ORIGIN_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
