"""M43 one-shot, offline Mac multimodal inference pilot: bounded, never approval.

Owner can inspect pinned M41 model and original M34/M37 sources without
running a model. Only --execute launches a SHA-pinned local M42 adapter
under a deadline, records observed wall time/child high-water RSS and
verifies UNSURE-only results. No Pi, training, model download, YouTube
upload, automatic retry, or quality/publication authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import resource
import subprocess
import sys
import time
from typing import Callable

from .episode_assembly import _ensure_private, digest
from .model_package import verify_checkpoint, checkpoint_digest, ModelPackageError
from .qwen_omni_local import inspect_local, _video, _wav, OmniAdapterError
from .real_media_evidence import (
    private_file, private_dir, _binary, media_subprocess_env, EvidenceCaptureError
)
from .scene_ai_qa import ROLE_CHECKS

SHA=re.compile(r"^[a-f0-9]{64}$")
ALL_ROLES={**ROLE_CHECKS["voice_synthesize"],**ROLE_CHECKS["ltx_animate"]}
VOICE_ROLES=ROLE_CHECKS["voice_synthesize"]
VIDEO_ROLES=ROLE_CHECKS["ltx_animate"]
MAX_SECONDS=900
MAX_STDOUT=32768
MAX_STDERR=32768


class PilotProbeError(ValueError):
    pass


def _pinned(source:str|Path,expected:str,ext:str,max_bytes:int)->Path:
    if not isinstance(expected,str) or not SHA.fullmatch(expected):
        raise PilotProbeError("Actual source SHA256 required.")
    p=private_file(source,ext,max_bytes=max_bytes)
    if digest(p)!=expected:
        raise PilotProbeError("Original media source differs from pinned SHA.")
    return p


def _verify_result(path:Path,*,role:str,source:dict[str,str])->str:
    if (not path.is_file() or path.is_symlink() or
        not 250<=path.stat().st_size<=20000):
        raise PilotProbeError("M42 diagnostic failed to produce bounded private JSON.")
    raw=path.read_bytes()
    try:doc=json.loads(raw)
    except (ValueError,UnicodeError) as exc:
        raise PilotProbeError("Malformed Qwen diagnostic JSON.") from exc
    fixed={"role","model_sha256","checks","summary","script_sha256"}
    extras=({"audio_sha256","transcript_sha256"} if role in VOICE_ROLES
            else {"mp4_sha256","wav_sha256","frames_manifest_sha256"})
    if (not isinstance(doc,dict) or set(doc)!=fixed|extras or
        doc["role"]!=role or
        any(doc.get(field)!=expected for field,expected in source.items()) or
        not isinstance(doc["summary"],str) or
        not 25<=len(doc["summary"])<=1500 or
        not isinstance(doc["checks"],dict) or
        set(doc["checks"])!=ALL_ROLES[role]):
        raise PilotProbeError("Diagnostic was not bound to exact current scene bytes.")
    for item in doc["checks"].values():
        if (not isinstance(item,dict) or
            set(item)!={"decision","evidence"} or
            item["decision"]!="UNSURE" or
            not isinstance(item["evidence"],str) or
            not 25<=len(item["evidence"].strip())<=800):
            raise PilotProbeError("Unqualified model reported a forbidden quality PASS.")
    return hashlib.sha256(raw).hexdigest()


def run_probe(*,adapter:str,adapter_sha256:str,
              model:str|Path,model_sha256:str,variant:str,
              role:str,wav:str|Path,wav_sha256:str,
              script:str|Path,script_sha256:str,
              out_dir:str|Path,execute:bool=False,
              timeout_seconds:int=MAX_SECONDS,
              transcript:str|Path|None=None,
              transcript_sha256:str|None=None,
              mp4:str|Path|None=None,
              mp4_sha256:str|None=None,
              frames_manifest:str|Path|None=None,
              frames_sha256:str|None=None,
              ffprobe:str|None=None,
              ffprobe_sha256:str|None=None,
              resource_screen:Callable=inspect_local,
              launcher:Callable=subprocess.run)->dict:
    if (type(execute) is not bool or role not in ALL_ROLES or
        variant not in ("3b","7b") or
        type(timeout_seconds) is not int or
        not 1<=timeout_seconds<=MAX_SECONDS):
        raise PilotProbeError("One bounded, explicit private role/timeout required.")
    if not isinstance(adapter_sha256,str) or not SHA.fullmatch(adapter_sha256):
        raise PilotProbeError("Owner SHA256 pin for local adapter missing.")
    runner=_binary(adapter)
    if digest(Path(runner))!=adapter_sha256:
        raise PilotProbeError("Adapter executable content changed.")
    model_dir=verify_checkpoint(model,model_sha256,allow_directory=True)
    if not model_dir.is_dir():
        raise PilotProbeError("M43 requires a full frozen local Omni directory.")
    audio=_pinned(wav,wav_sha256,".wav",400_000_000)
    scene=_pinned(script,script_sha256,".txt",12000)
    _wav(audio)
    bound={"model_sha256":model_sha256,"script_sha256":script_sha256}
    command=[runner,"--model",str(model_dir),
        "--model-sha256",model_sha256,"--variant",variant,
        "--role",role,"--wav",str(audio),"--script",str(scene)]
    extra_files={}
    if role in VOICE_ROLES:
        if (transcript is None or mp4 is not None or
            frames_manifest is not None or
            transcript_sha256 is None or
            mp4_sha256 is not None or frames_sha256 is not None):
            raise PilotProbeError("Original voice review needs only exact ASR transcript.")
        t=_pinned(transcript,transcript_sha256,".txt",12000)
        bound.update({"audio_sha256":wav_sha256,
                      "transcript_sha256":transcript_sha256})
        command.extend(("--transcript",str(t)))
        extra_files["transcript"]=t
    else:
        if (mp4 is None or mp4_sha256 is None or
            frames_manifest is None or frames_sha256 is None or
            ffprobe is None or ffprobe_sha256 is None or
            transcript is not None or transcript_sha256 is not None):
            raise PilotProbeError("Synchronized reviewer needs MP4/frames and pinned FFprobe.")
        movie=_pinned(mp4,mp4_sha256,".mp4",2_000_000_000)
        frames=_pinned(frames_manifest,frames_sha256,".json",50000)
        probe=_binary(ffprobe)
        if (not isinstance(ffprobe_sha256,str) or
            not SHA.fullmatch(ffprobe_sha256) or
            digest(Path(probe))!=ffprobe_sha256):
            raise PilotProbeError("FFprobe executable changed.")
        _video(movie,probe)
        try:frames_doc=json.loads(frames.read_text("utf-8"))
        except (UnicodeError,ValueError) as exc:
            raise PilotProbeError("Invalid original frame evidence.") from exc
        if (not isinstance(frames_doc,dict) or
            not isinstance(frames_doc.get("frames"),list) or
            not 3<=len(frames_doc["frames"])<=12):
            raise PilotProbeError("Scene frame evidence must be bounded.")
        bound.update({"mp4_sha256":mp4_sha256,"wav_sha256":wav_sha256,
                      "frames_manifest_sha256":frames_sha256})
        command.extend(("--mp4",str(movie),
            "--frames-manifest",str(frames),"--ffprobe",probe))
        extra_files.update({"mp4":movie,"frames":frames,
                            "ffprobe":Path(probe)})
    # No source paths, transcript text, model prompts, keys or stdout
    # are included in these public diagnostic results.
    screen=resource_screen(model=model_dir,
        expected_model_sha=model_sha256,variant=variant)
    if (not isinstance(screen,dict) or screen.get("model_package_sha256")
        !=model_sha256 or
        screen.get("status") not in (
            "M42_RESOURCE_SCREEN_PASSED_MODEL_NOT_RUN",
            "M42_RESOURCE_SCREEN_BLOCKED") or
        screen.get("model_inference_tested") is not False or
        screen.get("model_quality_qualified") is not False):
        raise PilotProbeError("Untrusted model resource-screen evidence.")
    if not execute:
        return {"schema_version":1,
            "status":"M43_READ_ONLY_MODEL_PILOT_PREFLIGHT",
            "role":role,"model_package_sha256":model_sha256,
            "adapter_sha256":adapter_sha256,"source_sha256":bound,
            "resource_screen":screen,
            "model_calls":0,"elapsed_seconds":None,
            "observed_child_max_rss_bytes":None,
            "model_inference_proven":False,
            "model_quality_qualified":False,"owner_canary_approved":False,
            "child_safety_certified":False,
            "mac_pi_hardware_qualified":False,
            "files_written":False,"network_isolation_verified":False,
            "private_upload_permitted":False,
            "public_release_authorized":False}
    if screen["status"]!="M42_RESOURCE_SCREEN_PASSED_MODEL_NOT_RUN":
        raise PilotProbeError("Real Mac local resource screen blocks model launch.")
    root=Path(out_dir).expanduser()
    if (not root.is_absolute() or root.is_symlink() or root.exists() or
        not root.parent.is_dir() or
        (root.parent.stat().st_mode & 0o022)):
        raise PilotProbeError("New isolated private probe output directory required.")
    _ensure_private(root.parent)
    # All source SHA checks happen before the isolated destination is created.
    folder=private_dir(root)
    answer_file=folder/"m42_diagnostic.json"
    command.extend(("--output",str(answer_file),"--execute"))
    env=media_subprocess_env()
    env.update({"HF_HUB_OFFLINE":"1","TRANSFORMERS_OFFLINE":"1",
                "HF_DATASETS_OFFLINE":"1"})
    begin=time.perf_counter()
    try:
        p=launcher(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE,timeout=timeout_seconds,
                   env=env,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise PilotProbeError("Local model pilot unavailable/timed out; review discarded.") from exc
    elapsed=round(time.perf_counter()-begin,3)
    if (p.returncode!=0 or len(p.stdout)>MAX_STDOUT or
        len(p.stderr)>MAX_STDERR):
        raise PilotProbeError("Local model adapter failed or emitted unbounded output.")
    report_sha=_verify_result(answer_file,role=role,source=bound)
    if (checkpoint_digest(model_dir)!=model_sha256 or
        digest(Path(runner))!=adapter_sha256 or
        digest(audio)!=wav_sha256 or digest(scene)!=script_sha256 or
        any(digest(file)!=bound[{"transcript":"transcript_sha256",
                                "mp4":"mp4_sha256",
                                "frames":"frames_manifest_sha256",
                                "ffprobe":"ffprobe_sha256"}[name]]
            for name,file in extra_files.items()
            if name!="ffprobe") or
        ("ffprobe" in extra_files and
         digest(extra_files["ffprobe"])!=ffprobe_sha256)):
        raise PilotProbeError("Pinned scene/model/adapter mutated during runtime.")
    # macOS ru_maxrss uses bytes; Linux uses KiB. A snapshot is an
    # observational high-water mark and may include earlier child calls
    # in the same host process. It is NOT measured GPU/unified-memory use.
    rss=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    unit=1 if platform.system()=="Darwin" else 1024
    observed=int(rss*unit) if rss>0 else None
    receipt={"schema_version":1,
        "status":"M43_OBSERVATION_ONLY_NOT_AI_QUALIFIED",
        "role":role,"model_package_sha256":model_sha256,
        "adapter_sha256":adapter_sha256,"source_sha256":bound,
        "diagnostic_sha256":report_sha,
        "resource_screen":screen,
        "model_calls":1,"elapsed_seconds":elapsed,
        "observed_child_max_rss_bytes":observed,
        "rss_measurement_is_total_mac_gpu_usage":False,
        "model_inference_proven":False,
        "model_quality_qualified":False,"owner_canary_approved":False,
        "child_safety_certified":False,
        "mac_pi_hardware_qualified":False,
        "network_isolation_verified":False,
        "private_upload_permitted":False,"public_release_authorized":False}
    data=(json.dumps(receipt,sort_keys=True,ensure_ascii=False,
        indent=2,allow_nan=False)+"\n").encode()
    file=folder/"pilot_metrics.json"
    fd=os.open(str(file),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    return {**receipt,"metrics_sha256":hashlib.sha256(data).hexdigest(),
            "files_written":True}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-model-pilot")
    for field in ("adapter","adapter-sha256","model","model-sha256",
                  "variant","role","wav","wav-sha256","script",
                  "script-sha256","out"):
        p.add_argument("--"+field,required=True)
    p.add_argument("--transcript")
    p.add_argument("--transcript-sha256")
    p.add_argument("--mp4")
    p.add_argument("--mp4-sha256")
    p.add_argument("--frames-manifest")
    p.add_argument("--frames-sha256")
    p.add_argument("--ffprobe")
    p.add_argument("--ffprobe-sha256")
    p.add_argument("--timeout-seconds",type=int,default=MAX_SECONDS)
    p.add_argument("--execute",action="store_true")
    x=p.parse_args(argv)
    try:
        result=run_probe(adapter=x.adapter,adapter_sha256=x.adapter_sha256,
            model=x.model,model_sha256=x.model_sha256,variant=x.variant,
            role=x.role,wav=x.wav,wav_sha256=x.wav_sha256,
            script=x.script,script_sha256=x.script_sha256,out_dir=x.out,
            execute=x.execute,timeout_seconds=x.timeout_seconds,
            transcript=x.transcript,transcript_sha256=x.transcript_sha256,
            mp4=x.mp4,mp4_sha256=x.mp4_sha256,
            frames_manifest=x.frames_manifest,frames_sha256=x.frames_sha256,
            ffprobe=x.ffprobe,ffprobe_sha256=x.ffprobe_sha256)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (PilotProbeError,OmniAdapterError,ModelPackageError,
            EvidenceCaptureError,OSError,ValueError,TypeError,KeyError) as exc:
        print("M43_MODEL_PILOT_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
