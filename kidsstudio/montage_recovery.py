"""M55 PRIVATE-only, read-only inspection of a quarantined Mac montage.

This module never queues, resumes, acknowledges, repairs, deletes, moves or
publishes a media job. Evidence is bound to the original Mac STARTED journal
request hash and pinned local recipe/scene sources. Even valid-looking media
is ONLY a candidate for fresh QA in a separately authorized new workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Callable
from dataclasses import dataclass
from urllib.parse import quote

from .episode_assembly import (
    EpisodeAssembler, EpisodeAssemblyError, MAX_CLIP_BYTES, digest, probe_video
)
from .media_worker import MediaJournal, MediaRecipes, MediaError

JOB = re.compile(r"^[a-f0-9]{32}$")
NORMALIZED = re.compile(r"^([0-9]{3})_normalized\.mp4$")
INTERMEDIATE = re.compile(r"^([0-9]{3})_(v06|v07)\.mp4$")
MAX_REPORT_BYTES = 120_000
MAX_FILES = 126
MAX_PAYLOAD_BYTES = 4096
MANIFEST_STATES = frozenset({
    "STARTED", "READY_FOR_LOCAL_ASSEMBLY",
    "FAILED_REQUIRES_MANUAL_RECONCILIATION",
    "RENDERED_PENDING_HUMAN_AV_QA",
})


class RecoveryError(ValueError):
    """Untrusted, missing or inconsistent private evidence."""


@dataclass(frozen=True)
class RecoveryJournal:
    """Read-only journal locator: inspection must not initialize SQLite."""
    path: Path


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _journal_started(journal: MediaJournal | RecoveryJournal, job_id: str,
                     request_sha: str, recipe_id: str) -> None:
    if not journal.path.is_file() or journal.path.is_symlink():
        raise RecoveryError("M55 journal missing or symlinked; fail closed.")
    uri="file:"+quote(str(journal.path),safe="/")+"?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            row=db.execute("""SELECT request_sha,kind,recipe_id,state,result
                FROM attempts WHERE job_id=?""",(job_id,)).fetchone()
    except sqlite3.Error as exc:
        raise RecoveryError("M55 journal cannot be read safely.") from exc
    if (not row or row[0]!=request_sha or row[1]!="episode_assemble"
        or row[2]!=recipe_id or row[3]!="STARTED" or row[4] is not None):
        raise RecoveryError("M55 exact original STARTED montage attempt required.")


def inspect_quarantined_montage(
    recipes: MediaRecipes, journal: MediaJournal | RecoveryJournal, *,
    job_id: str, payload: dict[str, Any],
    prober: Callable[[Path, str], dict[str, Any]] = probe_video,
) -> dict[str, Any]:
    """Inspect current sources and bounded private outputs; do NOT change them.

    Never infer safe replay or reuse from file existence, probe success,
    synthetic receipts or an interrupted manifest.
    """
    if not isinstance(job_id,str) or not JOB.fullmatch(job_id):
        raise RecoveryError("M55 requires exact 32-hex original job ID.")
    if (not isinstance(payload,dict) or
        set(payload) not in ({"recipe_id","script_sha256"},
                             {"recipe_id","script_sha256","catalogue_sha256"}) or
        not isinstance(payload["recipe_id"],str) or
        not isinstance(payload["script_sha256"],str) or
        not re.fullmatch(r"[a-f0-9]{64}",payload["script_sha256"])):
        raise RecoveryError("M55 requires the exact original montage payload.")
    from .media_worker import HEX
    if "catalogue_sha256" in payload and (
        not isinstance(payload["catalogue_sha256"],str) or
        not HEX.fullmatch(payload["catalogue_sha256"])):
        raise RecoveryError("M55 catalogue SHA is invalid.")
    request_sha=hashlib.sha256(json.dumps(
        {"kind":"episode_assemble","payload":payload},
        sort_keys=True).encode("utf-8")).hexdigest()
    _journal_started(journal,job_id,request_sha,payload["recipe_id"])
    try:
        recipe=recipes.resolve("episode_assemble",payload["recipe_id"])
        has_evidence="scene_evidence" in recipe["inputs"]
        if has_evidence != ("catalogue_sha256" in payload):
            raise RecoveryError("M55 Pi/Mac catalogue policy disagrees.")
        if has_evidence and recipes.catalogue_sha256!=payload["catalogue_sha256"]:
            raise RecoveryError("M55 Mac catalogue differs from job SHA.")
        assembler=EpisodeAssembler(recipe["inputs"]["episode_recipe"],
                                   prober=prober)
        if assembler.output_root!=Path(recipe["output_root"]).resolve():
            raise RecoveryError("M55 recipe output directory changed.")
        if assembler.recipe["script"]["sha256"]!=payload["script_sha256"]:
            raise RecoveryError("M55 original episode script changed.")
        # This includes real FFprobe but NO rendering or data modifications.
        evidence=assembler.preflight()
    except (MediaError,EpisodeAssemblyError,OSError,ValueError,KeyError) as exc:
        raise RecoveryError("M55 pinned input or local media preflight failed.") from exc

    root=assembler.output_root
    run_dir=root/job_id
    if (run_dir.is_symlink() or not run_dir.is_dir() or
        run_dir.resolve()!=run_dir):
        raise RecoveryError("M55 original private run directory unavailable/unsafe.")
    manifest=run_dir/"qa_report.json"
    if (manifest.is_symlink() or not manifest.is_file() or
        not 0<manifest.stat().st_size<=MAX_REPORT_BYTES):
        raise RecoveryError("M55 original run report missing, linked or oversized.")
    try:
        record=json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,ValueError) as exc:
        raise RecoveryError("M55 run report cannot be decoded.") from exc
    if (not isinstance(record,dict) or record.get("run_id")!=job_id or
        record.get("status") not in MANIFEST_STATES or
        record.get("recipe_sha256")!=assembler.recipe_sha256 or
        record.get("script_sha256")!=evidence["script_sha256"] or
        record.get("clips")!=evidence["clips"] or
        record.get("publication_approved") is not False):
        raise RecoveryError("M55 failed run report disagrees with original pins.")
    # Read only recognized artifacts, never recursively follow a link.
    try:
        entries=sorted(run_dir.iterdir(),key=lambda item:item.name)
    except OSError as exc:
        raise RecoveryError("M55 cannot inspect private run folder.") from exc
    if len(entries)>MAX_FILES:
        raise RecoveryError("M55 unexpected number of private render files.")
    artifacts=[]
    warnings=[]
    expected_count=len(assembler.clips)
    normalized_count=0
    master_seen=False
    for item in entries:
        if item.is_symlink() or not item.is_file():
            raise RecoveryError("M55 untrusted symlink/directory in render folder.")
        name=item.name
        if name in {"qa_report.json","concat.ffconcat"}:
            continue
        match=NORMALIZED.fullmatch(name)
        intermediate=INTERMEDIATE.fullmatch(name)
        if not match and not intermediate and name!="episode_qa_master.mp4":
            warnings.append("UNEXPECTED_FILE_REQUIRES_REVIEW")
            continue
        if item.stat().st_size<=0 or item.stat().st_size>MAX_CLIP_BYTES:
            warnings.append("EMPTY_OR_OVERSIZED_RENDER_ARTIFACT")
            artifacts.append({"name":name,"status":"INVALID_SIZE"})
            continue
        if match or intermediate:
            ordinal=int((match or intermediate).group(1))
            if ordinal<1 or ordinal>expected_count:
                warnings.append("OUT_OF_RANGE_SCENE_OUTPUT")
                artifacts.append({"name":name,"status":"INVALID_SCENE_NUMBER"})
                continue
        # Inspect every eligible artifact against its original source
        # duration. Probe validates one video and one audio stream.
        checksum=digest(item)
        entry={"name":name,"sha256":checksum,"bytes":item.stat().st_size}
        try:
            info=prober(item,assembler.ffprobe)
            entry["duration_seconds"]=round(info["duration"],3)
            if name=="episode_qa_master.mp4":
                master_seen=True
                valid=(info["width"]==1280 and info["height"]==720 and
                    info["audio_streams"]==1 and
                    abs(info["duration"]-evidence["source_duration_seconds"])
                    <=max(0.75,0.25*expected_count))
                entry["status"]=("MASTER_CANDIDATE_M7_FULL_DECODE_REQUIRED"
                                 if valid else "INVALID_MEDIA")
            elif match:
                valid=(info["width"]==1280 and info["height"]==720 and
                    info["audio_streams"]==1 and
                    abs(info["duration"]-evidence["clips"][ordinal-1]["duration"])
                    <=0.60)
                entry["status"]=("NORMALIZED_CANDIDATE_NOT_APPROVED_FOR_REUSE"
                                 if valid else "INVALID_MEDIA")
                normalized_count+=int(valid)
            else:
                # Intermediate face-cleanup outputs never pass as normalized.
                entry["status"]="INTERMEDIATE_UNVERIFIED"
        except (EpisodeAssemblyError,OSError,ValueError,KeyError,TypeError):
            entry["status"]="UNPROBEABLE_NOT_REUSABLE"
            warnings.append("FAILED_TO_PROBE_OUTPUT")
        artifacts.append(entry)

    if warnings:
        recommendation="REVIEW_OR_REBUILD_WITH_NEW_OWNER_AUTHORIZED_JOB"
    elif master_seen:
        recommendation="REVIEW_MASTER_WITH_M7_AND_FINAL_QA_BEFORE_ANY_REUSE"
    elif normalized_count:
        recommendation="REVIEW_NORMALIZED_CANDIDATES_FOR_SEPARATE_NEW_RUN"
    else:
        recommendation="NO_RECOVERABLE_MEDIA_FOUND"
    return {
        "schema_version":1,
        "status":"M55_QUARANTINED_INSPECTION_ONLY",
        "job_id":job_id,
        "series_id":assembler.recipe["series_id"],
        "episode_number":assembler.recipe["episode_number"],
        "recipe_id":payload["recipe_id"],
        "request_sha256":request_sha,
        "recipe_sha256":assembler.recipe_sha256,
        "manifest_sha256":digest(manifest),
        "manifest_state":record["status"],
        "original_script_sha256":payload["script_sha256"],
        "catalogue_sha256":payload.get("catalogue_sha256"),
        "scene_count":expected_count,
        "normalized_candidate_count":normalized_count,
        "artifacts":artifacts,
        "warnings":sorted(set(warnings)),
        "recommendation":recommendation,
        "auto_retry_allowed":False,
        "auto_reuse_allowed":False,
        "public_release_authorized":False,
        "owner_preview_approved":False,
    }


def freeze_recovery_inspection(
    recipes: MediaRecipes, journal: MediaJournal | RecoveryJournal, *,
    job_id: str, payload: dict[str, Any],
    prober: Callable[[Path, str], dict[str, Any]] = probe_video,
) -> dict[str, Any]:
    """Freeze one immutable inspection snapshot under private output root.

    Never overwrite an earlier snapshot or write into the partial run dir.
    """
    report=inspect_quarantined_montage(
        recipes,journal,job_id=job_id,payload=payload,prober=prober)
    recipe=recipes.resolve("episode_assemble",payload["recipe_id"])
    output=Path(recipe["output_root"]).resolve()
    folder=output/"_recovery_evidence"
    if folder.is_symlink():
        raise RecoveryError("M55 recovery folder must not be symlinked.")
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    if folder.resolve()!=folder:
        raise RecoveryError("M55 recovery folder escaped private output root.")
    target=folder/(job_id+".json")
    envelope={"schema_version":1,"report":report,
              "report_sha256":hashlib.sha256(_canonical(report)).hexdigest()}
    encoded=json.dumps(envelope,ensure_ascii=False,sort_keys=True,
                       indent=2,allow_nan=False).encode("utf-8")+b"\n"
    # O_EXCL is a one-way, intentional freeze. A later source mutation is
    # detected by re-inspection, never by overwriting a frozen report.
    try:
        fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc:
        raise RecoveryError("M55 evidence already frozen; no replacement.") from exc
    with os.fdopen(fd,"wb") as sink:
        sink.write(encoded)
        sink.flush()
        os.fsync(sink.fileno())
    return {"status":"M55_INSPECTION_EVIDENCE_FROZEN_NO_ACTUATION",
            "job_id":job_id,"report_sha256":envelope["report_sha256"],
            "auto_retry_allowed":False,
            "auto_reuse_allowed":False,
            "public_release_authorized":False}


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(prog="studio-montage-recovery")
    parser.add_argument("--recipes",required=True)
    parser.add_argument("--journal",required=True)
    parser.add_argument("--job-id",required=True)
    parser.add_argument("--payload-json",type=Path,required=True,
                        help="private exact render payload; not a job control script")
    parser.add_argument("--freeze-evidence",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.payload_json.is_symlink() or not args.payload_json.is_file():
            raise RecoveryError("Private job payload file unavailable.")
        if not 0<args.payload_json.stat().st_size<=MAX_PAYLOAD_BYTES:
            raise RecoveryError("M55 payload file oversized or empty.")
        payload=json.loads(args.payload_json.read_text(encoding="utf-8"))
        recipes=MediaRecipes(args.recipes)
        journal_path=Path(args.journal).expanduser()
        if journal_path.is_symlink() or not journal_path.is_file():
            raise RecoveryError("M55 existing Mac journal required.")
        journal=RecoveryJournal(journal_path.resolve())
        report=(freeze_recovery_inspection(recipes,journal,job_id=args.job_id,
            payload=payload) if args.freeze_evidence else
            inspect_quarantined_montage(recipes,journal,job_id=args.job_id,
            payload=payload))
        print(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2))
        return 0
    except (RecoveryError,MediaError,OSError,ValueError,TypeError,
            sqlite3.Error) as exc:
        print("MONTAGE_RECOVERY_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
