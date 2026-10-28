"""M34: local independent audio-model execution + M23/M28 evidence bridge.

Runs pinned FFmpeg/FFprobe, local whisper.cpp and TWO separate audio-capable
model adapters over the actual private WAV. Only the exact M28 schema is
signed; Pi must independently check source/job/tech/rights before admitting it.
An adapter is an operator-installed executable that MUST actually listen to
the supplied --wav, not a text-only chat model. CI adapters are explicit mocks.
No PUBLIC or YouTube action, and no claim of legal rights adjudication.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

from .real_media_evidence import (
    capture_asr,private_file,private_dir,digest,_binary,EvidenceCaptureError,
    media_subprocess_env
)
from .voice_qa import inspect_voice,VoiceQAError
from .scene_ai_qa import ROLE_CHECKS,_private,SceneError,PROVIDER

HEX=re.compile(r"^[a-f0-9]{64}$")
JOB=re.compile(r"^[a-f0-9]{32}$")
MODEL=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")

class AudioModelError(ValueError):
    pass

def _write(path:Path,data:dict)->str:
    if path.exists() or path.is_symlink():
        raise AudioModelError("Private report must not be overwritten.")
    raw=json.dumps(data,sort_keys=True,ensure_ascii=False,
                   indent=2,allow_nan=False).encode("utf-8")
    fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()

class AudioRunner:
    """Explicit local CLI adapter contract; NOT a proof of model quality."""
    def __init__(self,*,binary:str,expected_binary_sha:str,
                 model:str|Path,expected_model_sha:str,
                 provider_id:str,model_id:str):
        if (not isinstance(provider_id,str) or
            not PROVIDER.fullmatch(provider_id) or
            not isinstance(model_id,str) or not MODEL.fullmatch(model_id)
            or any(not isinstance(x,str) or not HEX.fullmatch(x)
                   for x in (expected_binary_sha,expected_model_sha))):
            raise AudioModelError("Provider, model and exact executable hashes required.")
        self.binary=_binary(binary)
        self.model=private_file(model,".bin",max_bytes=7*1024**3)
        if (digest(Path(self.binary))!=expected_binary_sha or
            digest(self.model)!=expected_model_sha):
            raise AudioModelError("Local model runner or checkpoint digest differs.")
        self.binary_sha=expected_binary_sha
        self.model_sha=expected_model_sha
        self.provider_id=provider_id
        self.model_id=model_id

    def evaluate(self,*,role:str,wav:Path,script:Path,
                 transcript:Path,language:str,out_dir:Path)->dict:
        if role not in ROLE_CHECKS["voice_synthesize"]:
            raise AudioModelError("Unapproved audio review role.")
        # The adapter must read actual audio bytes. A text-only reviewer
        # cannot establish emotional tone or pronunciation; if unsupported,
        # it MUST return UNSURE for those criteria.
        path=out_dir/("review_"+role+".json")
        argv=[self.binary,
              "--wav",str(wav),"--script",str(script),
              "--transcript",str(transcript),
              "--model",str(self.model),"--language",language,
              "--role",role,"--output",str(path)]
        try:
            proc=subprocess.run(argv,stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                timeout=300,check=False,env=media_subprocess_env())
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise AudioModelError("Local independent audio model unavailable or timed out.") from exc
        if (proc.returncode!=0 or len(proc.stdout)>100000 or
            len(proc.stderr)>100000 or
            not path.is_file() or path.is_symlink() or
            not 20<=path.stat().st_size<=15000):
            raise AudioModelError("Local audio model did not produce bounded evidence.")
        try:answer=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,UnicodeError,ValueError) as exc:
            raise AudioModelError("Audio model returned malformed JSON.") from exc
        required={"role","audio_sha256","script_sha256",
                  "transcript_sha256","model_sha256","checks","summary"}
        if (not isinstance(answer,dict) or set(answer)!=required or
            answer["role"]!=role or
            answer["audio_sha256"]!=digest(wav) or
            answer["script_sha256"]!=digest(script) or
            answer["transcript_sha256"]!=digest(transcript) or
            answer["model_sha256"]!=self.model_sha or
            not isinstance(answer["checks"],dict) or
            set(answer["checks"])!=ROLE_CHECKS["voice_synthesize"][role] or
            not isinstance(answer["summary"],str) or
            not 25<=len(answer["summary"].strip())<=1500):
            raise AudioModelError("Model did not bind its observations to all source bytes.")
        for criterion,item in answer["checks"].items():
            if (not isinstance(item,dict) or set(item)!={"decision","evidence"}
                or item["decision"] not in ("PASS","UNSURE","NEEDS_FIX")
                or not isinstance(item["evidence"],str)
                or not 25<=len(item["evidence"].strip())<=800):
                raise AudioModelError("Unsupported or unsubstantiated audio decision.")
        return answer

def review_voice(*,series_id:str,episode:int,scene:int,job_id:str,
                 wav:str|Path,wav_sha:str,script:str|Path,script_sha:str,
                 language:str,rights_file:str|Path,
                 whisper_binary:str,whisper_model:str|Path,
                 whisper_model_sha:str,ffmpeg:str,ffprobe:str,
                 first:AudioRunner,second:AudioRunner,
                 runner_key:bytes,out_dir:str|Path)->dict:
    if (not isinstance(series_id,str) or
        not re.fullmatch(r"[a-z][a-z0-9_-]{1,47}",series_id)
        or type(episode) is not int or not 1<=episode<=120
        or type(scene) is not int or not 1<=scene<=40
        or not isinstance(job_id,str) or not JOB.fullmatch(job_id)
        or language not in ("ar","en")
        or any(not isinstance(x,str) or not HEX.fullmatch(x)
               for x in (wav_sha,script_sha,whisper_model_sha))
        or not isinstance(runner_key,bytes) or len(runner_key)<32):
        raise AudioModelError("Exact current media identity and trusted worker key required.")
    if (first.provider_id==second.provider_id or
        first.model_id==second.model_id or
        first.model_sha==second.model_sha or
        first.binary_sha==second.binary_sha or
        first.provider_id=="asr_whispercpp" or
        second.provider_id=="asr_whispercpp"):
        raise AudioModelError("Two truly distinct audio runner/model identities required.")
    wav=private_file(wav,".wav",max_bytes=400_000_000)
    script=private_file(script,".txt",max_bytes=12000)
    if digest(wav)!=wav_sha or digest(script)!=script_sha:
        raise AudioModelError("Private narration or scene text changed.")
    ffmpeg=_binary(ffmpeg);ffprobe=_binary(ffprobe)
    rights_raw,rights_sha=_private(rights_file,100000,".json")
    try:rights=json.loads(rights_raw)
    except (TypeError,ValueError) as exc:
        raise AudioModelError("Invalid private rights receipt.") from exc
    if (not isinstance(rights,dict) or set(rights)!={
            "schema_version","artifact_sha256","source_kind",
            "source_proof_sha256","source_proof_file",
            "usage_scope","documented","rights_adjudicated",
            "publication_approved"}
        or rights.get("schema_version")!=1 or
        rights.get("artifact_sha256")!=wav_sha or
        rights.get("source_kind") not in (
             "original_created","licensed","public_domain_verified") or
        rights.get("usage_scope")!="commercial_youtube_kids" or
        rights.get("documented") is not True or
        rights.get("rights_adjudicated") is not False or
        rights.get("publication_approved") is not False):
        raise AudioModelError("Original narration needs documented rights source.")
    proof,proof_sha=_private(rights["source_proof_file"],100000,".txt")
    if proof_sha!=rights["source_proof_sha256"] or len(proof.strip())<30:
        raise AudioModelError("Voice source-rights proof differs or is missing.")
    tech=inspect_voice(wav,wav_sha,job_id,script_sha,
                      ffmpeg=ffmpeg,ffprobe=ffprobe)
    if tech["status"]!="VOICE_TECH_PASS_OWNER_LISTENING_PENDING":
        raise AudioModelError("Actual WAV failed M23 technical checks.")
    out=private_dir(out_dir)
    tech_sha=_write(out/"voice_technical.json",tech)
    asr=capture_asr(wav=wav,script=script,
        expected_wav_sha=wav_sha,expected_script_sha=script_sha,
        whisper_binary=whisper_binary,
        model=whisper_model,expected_model_sha=whisper_model_sha,
        ffmpeg_binary=ffmpeg,out_dir=out/"asr",language=language)
    transcript=Path(asr["transcript_file"])
    reviewers=[]
    for role,runner in (("pronunciation",first),
                        ("child_audio_safety",second)):
        answer=runner.evaluate(role=role,wav=wav,script=script,
                   transcript=transcript,language=language,out_dir=out)
        if (digest(wav)!=wav_sha or digest(script)!=script_sha or
            digest(Path(runner.binary))!=runner.binary_sha or
            digest(runner.model)!=runner.model_sha):
            raise AudioModelError("Source or approved model changed during inference.")
        reviewers.append({
            "role":role,"provider_id":runner.provider_id,
            "model_id":runner.model_id,
            "evidence_sha256":None,
            "checks":answer["checks"],"summary":answer["summary"],
            "publication_approved":False})
    observation={
        "schema_version":1,"stage":"voice_synthesize",
        "artifact_sha256":wav_sha,"script_sha256":script_sha,
        "script_file":str(script),"asr_file":str(transcript),
        "asr_model_id":"whispercpp_"+whisper_model_sha[:16],
        "asr_provider_id":"asr_whispercpp","asr_job_id":uuid4().hex,
        "model_execution_verified":True,"publishing_approved":False}
    obs_sha=_write(out/"observations.json",observation)
    for review in reviewers:review["evidence_sha256"]=obs_sha
    unsigned={
        "schema_version":1,"series_id":series_id,
        "episode_number":episode,"scene":scene,
        "stage":"voice_synthesize","job_id":job_id,
        "script_sha256":script_sha,"artifact_sha256":wav_sha,
        "observations_sha256":obs_sha,"rights_sha256":rights_sha,
        "technical_sha256":tech_sha,"reviewers":reviewers,
        "publication_approved":False}
    canonical=json.dumps(unsigned,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")
    unsigned["runner_attestation"]={
        "runner_id":"m34_local_audio_runner",
        "runtime_status":"REVIEW_MODELS_EXECUTED",
        "hmac_sha256":hmac.new(runner_key,canonical,hashlib.sha256).hexdigest()}
    report_sha=_write(out/"signed_voice_m28.json",unsigned)
    return {
        "status":"M34_AUDIO_MODEL_REPORT_READY_FOR_PI_M28_IMPORT",
        "model_runner_calls":2,
        "wav_sha256":wav_sha,"technical_sha256":tech_sha,
        "observations_sha256":obs_sha,
        "signed_report_sha256":report_sha,
        "signed_report_file":str(out/"signed_voice_m28.json"),
        "rights_sha256":rights_sha,
        "all_audio_model_checks_pass":all(
            c["decision"]=="PASS" for r in reviewers
            for c in r["checks"].values()),
        "pi_scene_approved":False,
        "owner_post_private_review_required":True,
        "public_release_authorized":False}

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="studio-real-audio-review")
    for name in ("series","job-id","wav","wav-sha256","script",
                 "script-sha256","language","rights","whisper",
                 "whisper-model","whisper-model-sha256","ffmpeg",
                 "ffprobe","first-binary","first-binary-sha256",
                 "first-model","first-model-sha256","first-provider",
                 "first-model-id","second-binary","second-binary-sha256",
                 "second-model","second-model-sha256",
                 "second-provider","second-model-id","out"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--episode",type=int,required=True)
    parser.add_argument("--scene",type=int,required=True)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"status":"M34_PREFLIGHT_NO_MODELS_EXECUTED",
            "public_release_authorized":False}))
        return 0
    try:
        key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode("utf-8")
        runners={}
        for ordinal in ("first","second"):
            runners[ordinal]=AudioRunner(
                binary=getattr(args,ordinal+"_binary"),
                expected_binary_sha=getattr(args,ordinal+"_binary_sha256"),
                model=getattr(args,ordinal+"_model"),
                expected_model_sha=getattr(args,ordinal+"_model_sha256"),
                provider_id=getattr(args,ordinal+"_provider"),
                model_id=getattr(args,ordinal+"_model_id"))
        result=review_voice(series_id=args.series,episode=args.episode,
            scene=args.scene,job_id=args.job_id,wav=args.wav,
            wav_sha=args.wav_sha256,script=args.script,
            script_sha=args.script_sha256,language=args.language,
            rights_file=args.rights,whisper_binary=args.whisper,
            whisper_model=args.whisper_model,
            whisper_model_sha=args.whisper_model_sha256,
            ffmpeg=args.ffmpeg,ffprobe=args.ffprobe,
            first=runners["first"],second=runners["second"],
            runner_key=key,out_dir=args.out)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (AudioModelError,EvidenceCaptureError,VoiceQAError,SceneError,
            OSError,ValueError,TypeError,KeyError) as exc:
        print("M34_AUDIO_REVIEW_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
