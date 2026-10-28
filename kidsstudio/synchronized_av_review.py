"""M37 pinned synchronized MP4+WAV local reviewer -> M28 signed candidate.

Both independent reviewer adapters MUST actually observe MP4 video AND its audio
and the original WAV, not sampled silent PNGs or transcripts alone. Real
FFmpeg verifies an audible track and M10 continuity; model competence, lip
accuracy, rights and child suitability require genuine qualified checkpoints.
CI fake executables do not establish that competence. No PUBLIC permission.
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

from .audio_continuity import compare_voice_to_a2v, AudioContinuityError
from .local_audio_review import _write
from .real_media_evidence import (
    _binary, capture_frames, digest, private_file, private_dir,
    media_subprocess_env, EvidenceCaptureError,
)
from .scene_ai_qa import _private, ROLE_CHECKS
from .studio_scenes import SHA

JOB=re.compile(r"^[a-f0-9]{32}$")
PROVIDER=re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
MODEL_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")
ROLES=("motion_sync","visual_child_safety")


class AVReviewError(ValueError):
    pass


def _read_json(path: str|Path,limit:int=100000)->tuple[dict,str]:
    raw,sha=_private(path,limit,".json")
    try:doc=json.loads(raw)
    except (ValueError,UnicodeError) as exc:
        raise AVReviewError("Malformed private AV evidence.") from exc
    if not isinstance(doc,dict):
        raise AVReviewError("AV evidence must be an object.")
    return doc,sha


class AVRunner:
    """Explicit locally installed AV-capable CLI; model quality NOT verified."""
    def __init__(self,*,binary:str,binary_sha:str,model:str|Path,
                 model_sha:str,provider_id:str,model_id:str):
        if (not isinstance(provider_id,str) or not PROVIDER.fullmatch(provider_id)
            or not isinstance(model_id,str) or not MODEL_ID.fullmatch(model_id)
            or any(not isinstance(v,str) or not SHA.fullmatch(v)
                   for v in (binary_sha,model_sha))):
            raise AVReviewError("Pinned distinct AV executable and checkpoint required.")
        self.binary=_binary(binary)
        ext=Path(model).suffix.lower()
        if ext not in (".bin",".gguf",".safetensors"):
            raise AVReviewError("Pinned AV checkpoint file extension required.")
        self.model=private_file(model,ext,max_bytes=7*1024**3)
        if digest(Path(self.binary))!=binary_sha or digest(self.model)!=model_sha:
            raise AVReviewError("AV runner or checkpoint SHA mismatch.")
        self.binary_sha=binary_sha;self.model_sha=model_sha
        self.provider_id=provider_id;self.model_id=model_id

    def evaluate(self,*,role:str,mp4:Path,wav:Path,script:Path,
                 frames_manifest:Path,out_dir:Path)->dict:
        if role not in ROLES:
            raise AVReviewError("Unrecognized synchronized media review role.")
        target=out_dir/("review_"+role+".json")
        args=[self.binary,"--mp4",str(mp4),"--wav",str(wav),
              "--script",str(script),"--frames-manifest",str(frames_manifest),
              "--model",str(self.model),"--role",role,"--output",str(target)]
        try:
            proc=subprocess.run(args,stdin=subprocess.DEVNULL,
                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                 timeout=300,check=False,env=media_subprocess_env())
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise AVReviewError("Pinned AV model did not complete.") from exc
        if (proc.returncode!=0 or len(proc.stdout)>100000 or
            len(proc.stderr)>100000 or target.is_symlink() or
            not target.is_file() or not 20<=target.stat().st_size<=16000):
            raise AVReviewError("AV adapter failed to produce bounded judgment.")
        answer,_=_read_json(target,16000)
        required={"role","mp4_sha256","wav_sha256","script_sha256",
                  "frames_manifest_sha256","model_sha256","checks","summary"}
        if (set(answer)!=required or answer["role"]!=role or
            answer["mp4_sha256"]!=digest(mp4) or
            answer["wav_sha256"]!=digest(wav) or
            answer["script_sha256"]!=digest(script) or
            answer["frames_manifest_sha256"]!=digest(frames_manifest) or
            answer["model_sha256"]!=self.model_sha or
            not isinstance(answer["checks"],dict) or
            set(answer["checks"])!=ROLE_CHECKS["ltx_animate"][role] or
            not isinstance(answer["summary"],str) or
            not 25<=len(answer["summary"].strip())<=1500):
            raise AVReviewError("Model reply missing exact synchronized source proof.")
        for decision in answer["checks"].values():
            if (not isinstance(decision,dict) or
                set(decision)!={"decision","evidence"} or
                decision["decision"] not in ("PASS","UNSURE","NEEDS_FIX") or
                not isinstance(decision["evidence"],str) or
                not 25<=len(decision["evidence"].strip())<=800):
                raise AVReviewError("Incomplete role-specific AV observation.")
        return answer


def review_synchronized(*,series_id:str,episode:int,scene:int,
                        job_id:str,mp4:str|Path,mp4_sha:str,
                        wav:str|Path,wav_sha:str,script:str|Path,script_sha:str,
                        m10_report:str|Path,rights_file:str|Path,ffmpeg:str,
                        ffprobe:str,first:AVRunner,second:AVRunner,
                        runner_key:bytes,out_dir:str|Path,frames:int=5)->dict:
    if (not isinstance(series_id,str) or not re.fullmatch(
            r"[a-z][a-z0-9_-]{1,47}",series_id)
        or type(episode) is not int or not 1<=episode<=120
        or type(scene) is not int or not 1<=scene<=40
        or not isinstance(job_id,str) or not JOB.fullmatch(job_id)
        or any(not isinstance(s,str) or not SHA.fullmatch(s)
               for s in (mp4_sha,wav_sha,script_sha))
        or not isinstance(runner_key,bytes) or len(runner_key)<32):
        raise AVReviewError("Current Pi scene identity and trusted worker key required.")
    if (first.provider_id==second.provider_id or
        first.model_id==second.model_id or
        first.model_sha==second.model_sha or
        first.binary_sha==second.binary_sha):
        raise AVReviewError("Two different AV executables/providers/models required.")
    video=private_file(mp4,".mp4")
    voice=private_file(wav,".wav",max_bytes=400_000_000)
    source=private_file(script,".txt",max_bytes=12000)
    if any(digest(file)!=expected for file,expected in
           ((video,mp4_sha),(voice,wav_sha),(source,script_sha))):
        raise AVReviewError("Video, voice or script SHA differs.")
    ffmpeg=_binary(ffmpeg);ffprobe=_binary(ffprobe)
    m10,m10_sha=_read_json(m10_report,40000)
    # Recompute from ACTUAL ORIGINAL BYTES: a supplied plausible M10 JSON
    # is insufficient. Technical envelopes do not establish lip sync.
    actual=compare_voice_to_a2v(
        voice,video,voice_sha256=wav_sha,a2v_sha256=mp4_sha,ffmpeg=ffmpeg)
    if (actual["status"]!="AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED" or
        set(actual)!=set(m10) or any(m10[key]!=value
                    for key,value in actual.items())):
        raise AVReviewError("Real decoded PCM disagrees with pinned M10 receipt.")
    rights,rights_sha=_read_json(rights_file)
    if (set(rights)!={"schema_version","artifact_sha256","source_kind",
            "source_proof_sha256","source_proof_file","usage_scope",
            "documented","rights_adjudicated","publication_approved"} or
        rights["schema_version"]!=1 or rights["artifact_sha256"]!=mp4_sha or
        rights["source_kind"] not in (
            "original_created","licensed","public_domain_verified") or
        rights["usage_scope"]!="commercial_youtube_kids" or
        rights["documented"] is not True or
        rights["rights_adjudicated"] is not False or
        rights["publication_approved"] is not False):
        raise AVReviewError("Source-specific original media rights record missing.")
    proof,proof_sha=_private(rights["source_proof_file"],100000,".txt")
    if proof_sha!=rights["source_proof_sha256"] or len(proof.strip())<30:
        raise AVReviewError("Exact source-rights proof changed.")
    out=private_dir(out_dir)
    frames_result=capture_frames(mp4=video,expected_mp4_sha=mp4_sha,
        ffmpeg_binary=ffmpeg,ffprobe_binary=ffprobe,
        out_dir=out/"frames",frames=frames)
    manifest=Path(frames_result["frames_manifest_file"])
    observations={
        "schema_version":1,"stage":"ltx_animate",
        "artifact_sha256":mp4_sha,"script_sha256":script_sha,
        "source_voice_sha256":wav_sha,
        "frame_manifest_sha256":digest(manifest),
        "frame_manifest_file":str(manifest),
        "frame_count":frames,
        "visual_review_model_id":second.model_id,
        "model_execution_verified":True,"publishing_approved":False
    }
    obs_sha=_write(out/"observations.json",observations)
    reviews=[]
    for role,runner in zip(ROLES,(first,second)):
        answer=runner.evaluate(role=role,mp4=video,wav=voice,
                    script=source,frames_manifest=manifest,out_dir=out)
        if (digest(video)!=mp4_sha or digest(voice)!=wav_sha or
            digest(source)!=script_sha or digest(manifest)!=observations["frame_manifest_sha256"]
            or digest(Path(runner.binary))!=runner.binary_sha or
            digest(runner.model)!=runner.model_sha):
            raise AVReviewError("Media/model/frame evidence changed during reviewer run.")
        reviews.append({
            "role":role,"provider_id":runner.provider_id,
            "model_id":runner.model_id,"evidence_sha256":obs_sha,
            "checks":answer["checks"],"summary":answer["summary"],
            "publication_approved":False})
    # An immutable subordinate receipt records exact model checkpoints
    # beyond the legacy M28 import schema.
    lineage={
        "schema_version":1,"mp4_sha256":mp4_sha,"wav_sha256":wav_sha,
        "script_sha256":script_sha,"m10_sha256":m10_sha,
        "frame_manifest_sha256":digest(manifest),
        "reviewers":[{"role":role,"provider_id":r.provider_id,
            "model_id":r.model_id,"binary_sha256":r.binary_sha,
            "model_sha256":r.model_sha}
            for role,r in zip(ROLES,(first,second))],
        "actual_audio_video_models_qualified_by_ci":False,
        "public_release_authorized":False
    }
    lineage_sha=_write(out/"av_runner_lineage.json",lineage)
    # The M28 report itself remains schema-compatible with the Pi importer.
    unsigned={
        "schema_version":1,"series_id":series_id,"episode_number":episode,
        "scene":scene,"stage":"ltx_animate","job_id":job_id,
        "script_sha256":script_sha,"artifact_sha256":mp4_sha,
        "observations_sha256":obs_sha,"rights_sha256":rights_sha,
        "technical_sha256":m10_sha,"reviewers":reviews,
        "publication_approved":False
    }
    serialized=json.dumps(unsigned,sort_keys=True,ensure_ascii=False,
         separators=(",",":"),allow_nan=False).encode("utf-8")
    unsigned["runner_attestation"]={
        "runner_id":"m37_synchronized_av_worker",
        "runtime_status":"REVIEW_MODELS_EXECUTED",
        "hmac_sha256":hmac.new(runner_key,serialized,hashlib.sha256).hexdigest()}
    signed_sha=_write(out/"signed_av_m28.json",unsigned)
    return {
        "status":"M37_SIGNED_AV_CANDIDATE_FOR_CURRENT_PI_IMPORT",
        "signed_report_sha256":signed_sha,
        "signed_report_file":str(out/"signed_av_m28.json"),
        "m10_sha256":m10_sha,"model_lineage_sha256":lineage_sha,
        "all_model_checks_pass":all(check["decision"]=="PASS"
            for r in reviews for check in r["checks"].values()),
        "models_qualified_for_real_child_qa_by_this_test":False,
        "pi_scene_approved":False,"public_release_authorized":False,
        "owner_post_private_review_required":True,
    }


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-synchronized-av-review")
    for key in ("series","job-id","mp4","mp4-sha256","wav","wav-sha256",
                "script","script-sha256","m10-report","rights","ffmpeg",
                "ffprobe","first-binary","first-binary-sha256",
                "first-model","first-model-sha256","first-provider",
                "first-model-id","second-binary","second-binary-sha256",
                "second-model","second-model-sha256","second-provider",
                "second-model-id","out"):
        p.add_argument("--"+key,required=True)
    p.add_argument("--episode",type=int,required=True)
    p.add_argument("--scene",type=int,required=True)
    p.add_argument("--frames",type=int,default=5)
    p.add_argument("--execute",action="store_true")
    x=p.parse_args(argv)
    if not x.execute:
        print(json.dumps({"status":"M37_DRY_RUN_NO_MEDIA_OR_MODELS_EXECUTED",
                          "public_release_authorized":False}))
        return 0
    try:
        runners={}
        for key in ("first","second"):
            runners[key]=AVRunner(binary=getattr(x,key+"_binary"),
                binary_sha=getattr(x,key+"_binary_sha256"),
                model=getattr(x,key+"_model"),
                model_sha=getattr(x,key+"_model_sha256"),
                provider_id=getattr(x,key+"_provider"),
                model_id=getattr(x,key+"_model_id"))
        result=review_synchronized(series_id=x.series,episode=x.episode,
            scene=x.scene,job_id=x.job_id,mp4=x.mp4,mp4_sha=x.mp4_sha256,
            wav=x.wav,wav_sha=x.wav_sha256,script=x.script,
            script_sha=x.script_sha256,m10_report=x.m10_report,
            rights_file=x.rights,ffmpeg=x.ffmpeg,ffprobe=x.ffprobe,
            first=runners["first"],second=runners["second"],
            runner_key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode(),
            out_dir=x.out,frames=x.frames)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (AVReviewError,AudioContinuityError,EvidenceCaptureError,
            OSError,ValueError,TypeError,KeyError) as exc:
        print("M37_AV_REVIEW_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
