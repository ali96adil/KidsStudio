"""M61 dedicated PRIVATE recovery montage renderer.

Never accepts a raw Pi recipe path or executes schema-2 via legacy assembler.
Requires live M61 Pi lease proof and a full local M60 recheck before any work.
Reuses normalized MP4 bytes by immutable private copy, never recompresses
them individually. Originals follow the existing approved face/scale pass.
All subprocesses observe the lease-abort event, and resulting master must
pass the complete M7 technical quality gate. No upload or publication.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any, Callable

from .episode_assembly import (
    _run, probe_video, digest, _ensure_private,
    EpisodeAssemblyError, MAX_CLIP_BYTES,
)
from .episode_quality import inspect_video, CHECKS
from .resource_gate import cooperative_compute_lock
from .recovery_execution_recipe import (
    prepare_private_recovery_recipe, RecoveryRecipeError,
)
from .recovery_local_gate import verify_staged_m60_recovery
from .media_worker import MediaRecipes
from .montage_recovery import RecoveryJournal

JOB=re.compile(r"^[0-9a-f]{32}$")
REUSE="REUSE_RECOVERED_NORMALIZED_WITH_FRESH_M7_TECH_PASS"
FALLBACK="USE_ORIGINAL_APPROVED_LTX_SOURCE"


class RecoveryRenderError(ValueError):
    """Cannot produce a new private QA master without current scene/lease proof."""


def _m7_success(report:Any,expected:str)->bool:
    return (isinstance(report,dict) and
        report.get("status")=="TECH_PASS_OWNER_REVIEW_PENDING" and
        report.get("media_sha256")==expected and
        report.get("expected_media_sha256")==expected and
        isinstance(report.get("checks"),dict) and
        set(report["checks"])==set(CHECKS) and
        all(report["checks"][key] is True for key in CHECKS) and
        report.get("publishing_approved") is False and
        report.get("rights_verified") is False and
        report.get("subjective_checks_performed") is False)


def render_private_recovery_master(
    recipes:MediaRecipes,journal:RecoveryJournal, *,
    original_job_id:str,payload:dict[str,Any],proposal_id:str,
    job_id:str,generation:int,
    lease_check:Callable[[],dict[str,Any]],
    abort_event:threading.Event,
    runner:Callable[...,None]=_run,
    prober:Callable[[Path,str],dict[str,Any]]=probe_video,
    full_qa:Callable[[Path,str],dict[str,Any]]|None=None,
)->dict:
    """Runs only on the Mac behind a heartbeat-driven abort event.

    lease_check MUST contact the authenticated Pi coordinator in production;
    local fake callbacks are for offline synthetic regression tests only.
    """
    if (not isinstance(job_id,str) or not JOB.fullmatch(job_id) or
        job_id in (original_job_id,proposal_id) or
        type(generation) is not int or generation!=1 or
        not callable(lease_check) or
        not isinstance(abort_event,threading.Event)):
        raise RecoveryRenderError("M61 unique one-shot lease identity required.")
    # Full SHA/full FFmpeg decode of reused selections BEFORE any run created.
    try:
        checked=verify_staged_m60_recovery(
            recipes,journal,original_job_id=original_job_id,
            payload=payload,proposal_id=proposal_id,
            prober=prober,full_qa=full_qa)
        staged,manifest=prepare_private_recovery_recipe(
            recipes,journal,original_job_id=original_job_id,
            payload=payload,proposal_id=proposal_id,
            prober=prober,full_qa=full_qa,allow_existing_stage=True)
    except (RecoveryRecipeError,ValueError,OSError,TypeError) as exc:
        raise RecoveryRenderError("M61 Mac scene preflight refused.") from exc
    if (checked["recipe_sha256"]!=manifest["derived_recipe_sha256"] or
        checked["manifest_file_sha256"]!=digest(
            Path(staged["output_root"])/"_recovery_execution_manifests"/
            (proposal_id+".json"))):
        raise RecoveryRenderError("M61 M59 staging hashes changed.")

    root=_ensure_private(Path(staged["private_root"]))
    output=_ensure_private(Path(staged["output_root"]))
    ffmpeg=staged["tools"]["ffmpeg"]
    ffprobe=staged["tools"]["ffprobe"]
    face_python=staged["tools"]["face_python"]
    run_dir=output/job_id

    def live() -> None:
        if abort_event.is_set():
            raise RecoveryRenderError("M61 Pi/network lease already lost.")
        try: proof=lease_check()
        except Exception as exc:
            abort_event.set()
            raise RecoveryRenderError("M61 Pi live lease unavailable.") from exc
        if (not isinstance(proof,dict) or
            proof.get("status")!="M61_CURRENT_PRIVATE_RECOVERY_LEASE" or
            proof.get("job_id")!=job_id or
            proof.get("generation")!=generation or
            proof.get("proposal_id")!=proposal_id or
            proof.get("original_job_id")!=original_job_id or
            proof.get("recipe_sha256")!=checked["recipe_sha256"]):
            # the M61 manifest SHA is independently checked below; the
            # media contract is a DIFFERENT digest.
            abort_event.set()
            raise RecoveryRenderError("M61 Pi current lease proof disagrees.")
        if (proof.get("manifest_sha256")!=hashlib.sha256(
                json.dumps(manifest,ensure_ascii=False,sort_keys=True,
                    separators=(",",":"),allow_nan=False).encode()).hexdigest()
            or proof.get("media_contract_sha256")!=
                manifest["source_m58_contract_sha256"] or
            proof.get("script_sha256")!=manifest["original_script_sha256"] or
            proof.get("public_release_authorized") is not False or
            proof.get("render_started") is not False):
            abort_event.set()
            raise RecoveryRenderError("M61 Pi approved recovery hash set changed.")
        if abort_event.is_set():
            raise RecoveryRenderError("M61 lease lost immediately before command.")

    def invoke(args:list[str],*,timeout:int)->None:
        live()
        runner(args,timeout=timeout,abort_event=abort_event)
        live()

    with cooperative_compute_lock(root):
        live()
        if run_dir.exists() or run_dir.is_symlink():
            raise RecoveryRenderError("M61 recovery job directory already exists.")
        run_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
        report_path=run_dir/"qa_report.json"
        report={
            "schema_version":2,"run_id":job_id,
            "proposal_id":proposal_id,"original_job_id":original_job_id,
            "recipe_sha256":checked["recipe_sha256"],
            "manifest_sha256":proof_manifest_sha(manifest),
            "status":"M61_STARTED_PRIVATE_NOT_PUBLISHABLE",
            "started_at":time.time(),
            "scene_count":len(staged["clips"]),
            "recovered_candidates":manifest["recovered_candidates"],
            "source_fallbacks":manifest["fallbacks"],
            "publication_approved":False,
        }
        def snapshot():
            report_path.write_text(json.dumps(report,sort_keys=True,
                ensure_ascii=False,indent=2,allow_nan=False)+"\n",
                encoding="utf-8")
        snapshot()
        try:
            normalized=[]
            durations=[]
            for i,(clip,scene) in enumerate(
                    zip(staged["clips"],manifest["scenes"]),1):
                live()
                src=Path(clip["video"])
                if (src.is_symlink() or not src.is_file() or
                    not src.is_relative_to(root) or
                    not 0<src.stat().st_size<=MAX_CLIP_BYTES or
                    digest(src)!=clip["sha256"]):
                    raise RecoveryRenderError("M61 selected private source SHA changed.")
                stage=run_dir/f"{i:03}_normalized.mp4"
                if scene["strategy"]==REUSE:
                    # Already H264/AAC/24fps/1280x720 and M7 full-decode
                    # verified: copy immutable bytes, do NOT re-encode.
                    live()
                    with stage.open("xb") as target,src.open("rb") as original:
                        while True:
                            chunk=original.read(1024*1024)
                            if not chunk:break
                            if abort_event.is_set():
                                raise RecoveryRenderError(
                                    "M61 lease revoked while copying recovered bytes.")
                            target.write(chunk)
                        target.flush();os.fsync(target.fileno())
                    if digest(stage)!=clip["sha256"]:
                        raise RecoveryRenderError("M61 copied normalized source changed.")
                elif scene["strategy"]==FALLBACK:
                    original=src
                    if clip["face_cleanup"]=="bunny_v07":
                        middle=run_dir/f"{i:03}_v06.mp4"
                        face=run_dir/f"{i:03}_v07.mp4"
                        invoke([face_python,staged["tools"]["face_v06"],
                            "--input",str(src),"--output",str(middle)],
                            timeout=1500)
                        prober(middle,ffprobe)
                        invoke([face_python,staged["tools"]["face_v07"],
                            "--input",str(middle),"--output",str(face)],
                            timeout=1500)
                        original=face
                    invoke([ffmpeg,"-hide_banner","-loglevel","error",
                        "-nostdin","-n","-i",str(original),
                        "-map","0:v:0","-map","0:a:0",
                        "-vf","scale=1280:720:force_original_aspect_ratio=decrease,"
                              "pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                              "fps=24,format=yuv420p",
                        "-c:v","libx264","-preset","medium","-crf","18",
                        "-c:a","aac","-ar","48000","-ac","2","-b:a","160k",
                        "-movflags","+faststart",str(stage)],timeout=1800)
                else:
                    raise RecoveryRenderError("M61 unsupported recovery strategy.")
                info=prober(stage,ffprobe)
                if ((info["width"],info["height"])!=(1280,720) or
                    not .2<=info["duration"]<=180 or
                    info["audio_streams"]!=1):
                    raise RecoveryRenderError("M61 normalized scene tech metadata invalid.")
                durations.append(info["duration"])
                normalized.append(stage)
                live()
            playlist=run_dir/"concat.ffconcat"
            playlist.write_text("ffconcat version 1.0\n"+
                "".join(f"file '{s.name}'\n" for s in normalized),
                encoding="utf-8")
            master=run_dir/"episode_qa_master.mp4"
            invoke([ffmpeg,"-hide_banner","-loglevel","error",
                "-nostdin","-n","-safe","0","-f","concat",
                "-i",str(playlist),"-map","0:v:0","-map","0:a:0",
                "-vf","fps=24,format=yuv420p",
                "-c:v","libx264","-preset","medium","-crf","18",
                "-c:a","aac","-ar","48000","-ac","2","-b:a","160k",
                "-movflags","+faststart",str(master)],timeout=1800)
            live()
            final=prober(master,ffprobe)
            if ((final["width"],final["height"])!=(1280,720) or
                abs(final["duration"]-sum(durations))>
                    max(.75,.25*len(durations))):
                raise RecoveryRenderError("M61 final master geometry/timing invalid.")
            final_sha=digest(master)
            if full_qa is None:
                def monitored_full_decode(path:Path,binary:str)->bool:
                    # M7 must be interruptible during lease/network loss;
                    # do not call its default blocking subprocess.run.
                    try:
                        _run([binary,"-nostdin","-v","error","-xerror",
                              "-i",str(path),"-map","0:v:0",
                              "-map","0:a:0","-f","null","-"],
                             timeout=1800,abort_event=abort_event)
                    except EpisodeAssemblyError:
                        return False
                    return not abort_event.is_set()
                result=inspect_video(master,final_sha,
                    ffprobe=ffprobe,ffmpeg=ffmpeg,
                    decode_fn=monitored_full_decode)
            else:
                result=full_qa(master,final_sha)
            if not _m7_success(result,final_sha):
                raise RecoveryRenderError("M61 final full M7 decode failed.")
            live()
            report.update({
                "status":"M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW",
                "final_media_sha256":final_sha,
                "final_media_path":str(master),
                "final_media_bytes":master.stat().st_size,
                "full_m7_decode_passed":True,
                "completed_at":time.time(),
            })
            snapshot()
            return {
                "status":"M61_RECOVERY_MASTER_TECH_PASS_PENDING_REVIEW",
                "artifact_sha256":final_sha,
                "artifact_bytes":master.stat().st_size,
                "final_m7_full_decode_passed":True,
                "publication_approved":False,
            }
        except Exception as exc:
            abort_event.set()
            report["status"]="M61_FAILED_REQUIRES_MANUAL_RECONCILIATION"
            report["failure_type"]=type(exc).__name__
            snapshot()
            raise


def proof_manifest_sha(manifest:dict)->str:
    return hashlib.sha256(json.dumps(manifest,
        ensure_ascii=False,sort_keys=True,separators=(",",":"),
        allow_nan=False).encode("utf-8")).hexdigest()
