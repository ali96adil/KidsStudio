"""M29 local LTX multimodal review runner: two genuine Ollama calls.

The caller supplies an MP4 and exact SHA, a scene script, source voice SHA,
independent local Ollama processes/models, and a separate, pre-existing
rights catalogue. This worker captures actual FFmpeg PNGs, sends the exact
observed frames (plus script) to the two local vision models, validates both
JSON judgments and signs the resulting M28 report. It never invents
a 'PASS': a malformed/uncertain response fails closed.

This is still NOT children's-content certification, model provenance from
a hardware TEE, proof of legal rights, or PUBLIC release permission.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
from urllib import request, error
from urllib.parse import urlsplit

from .real_media_evidence import (
    capture_frames,digest,private_file,private_dir,
    EvidenceCaptureError
)
from .scene_ai_qa import ROLE_CHECKS, SceneError, _private

SHA=re.compile(r"^[0-9a-f]{64}$")
JOB=re.compile(r"^[0-9a-f]{32}$")
PROVIDER=re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
MODEL=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")
FRAME_BUDGET=8_000_000


class LocalVisionError(ValueError):
    pass


def _endpoint(url:str)->str:
    if not isinstance(url,str):
        raise LocalVisionError("Model service endpoint required.")
    p=urlsplit(url)
    try:port=p.port
    except ValueError as exc:
        raise LocalVisionError("Invalid local model port.") from exc
    if (p.scheme!="http" or p.hostname!="127.0.0.1" or
        port is None or not 1<=port<=65535 or p.username or p.password
        or p.query or p.fragment or p.path!="/api/chat"):
        raise LocalVisionError("Only explicit 127.0.0.1 Ollama /api/chat accepted.")
    return url


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


class OllamaVision:
    def __init__(self,endpoint:str,model:str,provider_id:str,*,opener=None):
        self.endpoint=_endpoint(endpoint)
        if not isinstance(model,str) or not MODEL.fullmatch(model):
            raise LocalVisionError("Explicit approved local model id required.")
        if not isinstance(provider_id,str) or not PROVIDER.fullmatch(provider_id):
            raise LocalVisionError("Independent local provider identifier required.")
        self.model=model
        self.provider_id=provider_id
        self.opener=opener if opener is not None else request.build_opener(
            request.ProxyHandler({}),_NoRedirect())

    def run(self,*,role:str,script:str,images:list[bytes],objective:str)->tuple[dict,str]:
        if role not in ROLE_CHECKS["ltx_animate"]:
            raise LocalVisionError("No approved vision review role.")
        if (not 1<=len(script)<=8000 or not 3<=len(images)<=12 or
            not 10<=len(objective)<=500 or
            sum(map(len,images))>FRAME_BUDGET):
            raise LocalVisionError("Actual frame/script review input unavailable/too large.")
        criteria=sorted(ROLE_CHECKS["ltx_animate"][role])
        prompt=(
            "You are a conservative independent educational video reviewer. "
            "Inspect ACTUAL frames from the current video, their order, and the "
            "supplied approved scene script. Do not assume ability to hear audio: "
            "for lip-sync/voice-continuity if not observable from silent frames "
            "return UNSURE. No invented observations. Return ONLY a JSON object "
            "with exactly keys 'checks' and 'summary'. Each required check must "
            "be an object with exactly 'decision' (PASS, UNSURE or NEEDS_FIX) "
            "and 'evidence' (25-800 chars, specific to observed frames). "
            "A check is PASS only when supported by evidence. Child safety "
            "must be considered carefully. If an important property cannot "
            "be checked using still frames, use UNSURE. Never authorize publishing. "
            "Required checks: "+", ".join(criteria)+"."
        )
        user=("Objective: "+objective+"\nApproved script: "+script)
        payload={
            "model":self.model,
            "messages":[
                {"role":"system","content":prompt},
                {"role":"user","content":user,
                 "images":[base64.b64encode(data).decode("ascii")
                           for data in images]}
            ],
            "stream":False,"format":"json",
            "options":{"temperature":0,"num_predict":1600}
        }
        body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        if len(body)>11_000_000:
            raise LocalVisionError("Review payload exceeds safe size limit.")
        req=request.Request(self.endpoint,data=body,method="POST",
                            headers={"Content-Type":"application/json"})
        try:
            with self.opener.open(req,timeout=180) as response:
                data=response.read(200_001)
        except (OSError,TimeoutError,error.URLError,error.HTTPError) as exc:
            raise LocalVisionError("Trusted local vision request failed.") from exc
        if len(data)>200_000:
            raise LocalVisionError("Model response exceeds safety budget.")
        try:
            response=json.loads(data)
            if response.get("done") is not True:
                raise LocalVisionError("Local vision model did not finish.")
            content=response["message"]["content"]
            answer=json.loads(content)
        except (KeyError,TypeError,UnicodeError,ValueError) as exc:
            raise LocalVisionError("Malformed local multimodal response.") from exc
        if (not isinstance(answer,dict) or set(answer)!={"checks","summary"}
            or not isinstance(answer["checks"],dict) or
            set(answer["checks"])!=set(criteria) or
            not isinstance(answer["summary"],str) or
            not 25<=len(answer["summary"].strip())<=1500):
            raise LocalVisionError("Incomplete model evidence response.")
        for name in criteria:
            row=answer["checks"][name]
            if (not isinstance(row,dict) or set(row)!={"decision","evidence"}
                or row["decision"] not in ("PASS","UNSURE","NEEDS_FIX")
                or not isinstance(row["evidence"],str)
                or not 25<=len(row["evidence"].strip())<=800):
                raise LocalVisionError("Invalid model criterion evidence.")
        return answer,hashlib.sha256(data).hexdigest()


def review_ltx(*,series_id:str,episode:int,scene:int,job_id:str,
               mp4:str|Path,mp4_sha:str,
               script:str|Path,script_sha:str,voice_sha:str,
               rights_file:str|Path,ffmpeg:str,ffprobe:str,
               objective:str,first:OllamaVision,second:OllamaVision,
               runner_key:bytes,out_dir:str|Path,frames:int=5)->dict:
    if (not isinstance(series_id,str) or not PROVIDER.fullmatch(series_id)
        or type(episode) is not int or not 1<=episode<=120
        or type(scene) is not int or not 1<=scene<=120
        or not isinstance(job_id,str) or not JOB.fullmatch(job_id)
        or any(not isinstance(x,str) or not SHA.fullmatch(x)
               for x in (mp4_sha,script_sha,voice_sha))
        or not isinstance(runner_key,bytes) or len(runner_key)<32):
        raise LocalVisionError("Pinned scene/master IDs and private runner key required.")
    if (first.provider_id==second.provider_id or
        first.model==second.model or first.endpoint==second.endpoint):
        raise LocalVisionError("Two different provider instances and models required.")
    mp4=private_file(mp4,".mp4")
    script=private_file(script,".txt",max_bytes=12000)
    if digest(mp4)!=mp4_sha or digest(script)!=script_sha:
        raise LocalVisionError("Model request media/script SHA differs.")
    rights_raw,rights_sha=_private(rights_file,100000,".json")
    try:rights=json.loads(rights_raw.decode("utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise LocalVisionError("Invalid owner-provided rights provenance.") from exc
    if (not isinstance(rights,dict) or
        rights.get("artifact_sha256")!=mp4_sha or
        rights.get("usage_scope")!="commercial_youtube_kids" or
        rights.get("documented") is not True):
        raise LocalVisionError("Source-specific media rights receipt missing.")
    out=private_dir(out_dir)
    frames_result=capture_frames(mp4=mp4,expected_mp4_sha=mp4_sha,
                    ffmpeg_binary=ffmpeg,ffprobe_binary=ffprobe,
                    out_dir=out/"frames",frames=frames)
    frames_manifest=Path(frames_result["frames_manifest_file"])
    samples=json.loads(frames_manifest.read_text(encoding="utf-8"))["frames"]
    images=[Path(item["file"]).read_bytes() for item in samples]
    if not 3<=len(images)<=12 or sum(map(len,images))>FRAME_BUDGET:
        raise LocalVisionError("Frames cannot safely be sent to vision model.")
    plain=script.read_text(encoding="utf-8")
    reviewers=[]
    for role,client in zip(("motion_sync","visual_child_safety"),(first,second)):
        answer,response_sha=client.run(role=role,script=plain,images=images,
                                       objective=objective)
        if digest(mp4)!=mp4_sha or digest(script)!=script_sha:
            raise LocalVisionError("Media changed during local vision inference.")
        reviewers.append({
            "role":role,"provider_id":client.provider_id,
            "model_id":client.model,"evidence_sha256":None,
            "checks":answer["checks"],"summary":answer["summary"],
            "publication_approved":False
        })
    observation={
        "schema_version":1,"stage":"ltx_animate",
        "artifact_sha256":mp4_sha,"script_sha256":script_sha,
        "source_voice_sha256":voice_sha,
        "frame_manifest_sha256":digest(frames_manifest),
        "frame_manifest_file":str(frames_manifest),
        "frame_count":len(samples),
        "visual_review_model_id":second.model,
        "model_execution_verified":True,
        "publishing_approved":False
    }
    obs_file=out/"observations.json"
    obs_file.write_text(json.dumps(observation,sort_keys=True,
                                  ensure_ascii=False,indent=2))
    obs_sha=digest(obs_file)
    for item in reviewers:item["evidence_sha256"]=obs_sha
    # Technical M10 digest must be entered later from actual Pi-approved
    # continuity report. Do not invent one or fake complete M28 signature.
    # Produce unsigned signed-report CANDIDATE until a separate trusted
    # stage coordinator supplies current M10 technical evidence.
    out_result={
        "schema_version":1,"status":"REAL_LOCAL_VISUAL_MODEL_REPORTS_PENDING_M10_BIND",
        "series_id":series_id,"episode_number":episode,"scene":scene,
        "stage":"ltx_animate","job_id":job_id,
        "script_sha256":script_sha,"artifact_sha256":mp4_sha,
        "observations_sha256":obs_sha,"rights_sha256":rights_sha,
        "reviewers":reviewers,
        "frame_capture_report_sha256":digest(out/"frames"/"evidence.json"),
        "runner_models_executed":True,
        "m28_stage_approved":False,"public_release_authorized":False,
        "needs_fix_or_unsure":any(
            c["decision"]!="PASS" for item in reviewers
            for c in item["checks"].values())
    }
    (out/"model_report_pending_m10.json").write_text(
        json.dumps(out_result,ensure_ascii=False,indent=2))
    return out_result


def sign_after_m10(*,pending_report:str|Path,
                   m10_report:str|Path,expected_m10_sha:str,
                   rights_file:str|Path,observation_file:str|Path,
                   attestation_key:bytes,out_file:str|Path)->dict:
    """Bind actually recorded M10 source/voice/media data to live vision run.

    Must be invoked ONLY inside the trusted model-worker process. The
    resulting M28 bundle still needs Pi SceneAIGate.register, which
    compares the M10 digest against the current immutable Pi receipt.
    """
    if (not isinstance(attestation_key,bytes) or len(attestation_key)<32
        or not isinstance(expected_m10_sha,str) or
        not SHA.fullmatch(expected_m10_sha)):
        raise LocalVisionError("Private trusted model-runner key and pinned M10 required.")
    raw,pending_sha=_private(pending_report,100000,".json")
    m10_raw,real_m10_sha=_private(m10_report,40000,".json")
    observation_raw,obs_sha=_private(observation_file,100000,".json")
    rights_raw,rights_sha=_private(rights_file,100000,".json")
    if real_m10_sha!=expected_m10_sha:
        raise LocalVisionError("M10 report changed before signing.")
    try:
        pending=json.loads(raw); m10=json.loads(m10_raw)
        obs=json.loads(observation_raw)
    except (TypeError,ValueError,UnicodeError) as exc:
        raise LocalVisionError("Malformed evidence before signing.") from exc
    if (not isinstance(pending,dict) or
        pending.get("status")!="REAL_LOCAL_VISUAL_MODEL_REPORTS_PENDING_M10_BIND" or
        pending.get("runner_models_executed") is not True or
        pending.get("m28_stage_approved") is not False or
        pending.get("public_release_authorized") is not False or
        pending.get("observations_sha256")!=obs_sha or
        pending.get("rights_sha256")!=rights_sha or
        pending.get("stage")!="ltx_animate" or
        pending.get("artifact_sha256")!=obs.get("artifact_sha256") or
        pending.get("script_sha256")!=obs.get("script_sha256") or
        not isinstance(pending.get("reviewers"),list) or
        len(pending["reviewers"])!=2 or
        not isinstance(m10,dict) or
        m10.get("status")!="AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED" or
        m10.get("voice_sha256")!=obs.get("source_voice_sha256") or
        m10.get("a2v_sha256")!=pending.get("artifact_sha256") or
        m10.get("duration_close") is not True or
        m10.get("energy_present") is not True or
        type(m10.get("envelope_correlation")) not in (int,float) or
        not .82<=m10["envelope_correlation"]<=1 or
        type(m10.get("estimated_lag_seconds")) not in (int,float) or
        abs(m10["estimated_lag_seconds"])>.6):
        raise LocalVisionError("Current source voice and signed-review M10 mismatch.")
    reviewers=pending["reviewers"]
    # The M29 runner receives sampled silent PNG frames, not synchronized
    # audio. Even when a model confidently asserts PASS, that cannot verify
    # lip movements or audible voice continuity. An audio/video-capable
    # follow-on reviewer must supply that evidence separately.
    motion_checks=reviewers[0].get("checks",{}) if isinstance(reviewers[0],dict) else {}
    if any(isinstance(motion_checks.get(name),dict) and
           motion_checks[name].get("decision")=="PASS"
           for name in ("lip_sync","voice_continuity")):
        raise LocalVisionError(
            "Silent frame-only review cannot certify lip-sync or voice continuity.")
    if (reviewers[0].get("role")!="motion_sync" or
        reviewers[1].get("role")!="visual_child_safety" or
        reviewers[0].get("provider_id")==reviewers[1].get("provider_id") or
        any(item.get("evidence_sha256")!=obs_sha for item in reviewers)):
        raise LocalVisionError("Independent model output source differs.")
    bundle={
        "schema_version":1,"series_id":pending["series_id"],
        "episode_number":pending["episode_number"],
        "scene":pending["scene"],
        "stage":"ltx_animate","job_id":pending["job_id"],
        "script_sha256":pending["script_sha256"],
        "artifact_sha256":pending["artifact_sha256"],
        "observations_sha256":obs_sha,
        "rights_sha256":rights_sha,
        "technical_sha256":real_m10_sha,
        "reviewers":reviewers,"publication_approved":False
    }
    canonical=json.dumps(bundle,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")
    bundle["runner_attestation"]={
        "runner_id":"m29_local_multimodal_worker",
        "runtime_status":"REVIEW_MODELS_EXECUTED",
        "hmac_sha256":hmac.new(attestation_key,canonical,
                               hashlib.sha256).hexdigest()
    }
    out=Path(out_file).expanduser()
    if (not out.is_absolute() or out.is_symlink() or out.suffix!=".json" or
        out.exists() or
        out.resolve().parent!=Path(pending_report).resolve().parent):
        raise LocalVisionError("Signed bundle must be new private sibling JSON.")
    blob=json.dumps(bundle,ensure_ascii=False,indent=2,
                    allow_nan=False).encode("utf-8")
    fd=os.open(str(out),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as file:
        file.write(blob);file.flush();os.fsync(file.fileno())
    return {"status":"SIGNED_M28_VISUAL_REVIEW_READY_FOR_PI_IMPORT",
            "bundle_sha256":digest(out),
            "technical_sha256":real_m10_sha,
            "m28_scene_approved":False,
            "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-real-vision-review")
    p.add_argument("--series",required=True)
    p.add_argument("--episode",type=int,required=True)
    p.add_argument("--scene",type=int,required=True)
    p.add_argument("--job-id",required=True)
    p.add_argument("--mp4",type=Path,required=True)
    p.add_argument("--mp4-sha256",required=True)
    p.add_argument("--script",type=Path,required=True)
    p.add_argument("--script-sha256",required=True)
    p.add_argument("--source-voice-sha256",required=True)
    p.add_argument("--rights",type=Path,required=True)
    p.add_argument("--ffmpeg",required=True)
    p.add_argument("--ffprobe",required=True)
    p.add_argument("--objective",required=True)
    p.add_argument("--first-endpoint",required=True)
    p.add_argument("--first-model",required=True)
    p.add_argument("--first-provider",required=True)
    p.add_argument("--second-endpoint",required=True)
    p.add_argument("--second-model",required=True)
    p.add_argument("--second-provider",required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    try:
        first=OllamaVision(args.first_endpoint,args.first_model,args.first_provider)
        second=OllamaVision(args.second_endpoint,args.second_model,args.second_provider)
        if not args.execute:
            print(json.dumps({"status":"PREFLIGHT_ONLY_NO_MODEL_CALLED",
                "models_executed":False,"public_release_authorized":False}))
            return 0
        key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode("utf-8")
        result=review_ltx(series_id=args.series,episode=args.episode,
                scene=args.scene,job_id=args.job_id,mp4=args.mp4,
                mp4_sha=args.mp4_sha256,script=args.script,
                script_sha=args.script_sha256,voice_sha=args.source_voice_sha256,
                rights_file=args.rights,ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,
                objective=args.objective,first=first,second=second,
                runner_key=key,out_dir=args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (LocalVisionError,EvidenceCaptureError,SceneError,OSError,
            ValueError,TypeError) as exc:
        print("VISION_REVIEW_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2

def main_sign(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-bind-vision-m10")
    p.add_argument("--pending-report",type=Path,required=True)
    p.add_argument("--m10-report",type=Path,required=True)
    p.add_argument("--m10-sha256",required=True)
    p.add_argument("--rights",type=Path,required=True)
    p.add_argument("--observations",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--execute",action="store_true")
    args=p.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"NO_SIGNING_OR_QA_WITHOUT_EXECUTE",
                          "m28_stage_approved":False,
                          "public_release_authorized":False}))
        return 0
    try:
        key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode("utf-8")
        result=sign_after_m10(pending_report=args.pending_report,
            m10_report=args.m10_report,
            expected_m10_sha=args.m10_sha256,
            rights_file=args.rights,observation_file=args.observations,
            attestation_key=key,out_file=args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (LocalVisionError,EvidenceCaptureError,SceneError,OSError,
            ValueError,TypeError) as exc:
        print("VISION_M10_BIND_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
