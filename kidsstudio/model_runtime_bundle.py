"""M40 pinned local model bundle and opt-in M34/M37 execution router.

One private, immutable manifest binds installed FFmpeg/FFprobe, whisper.cpp,
two independent WAV reviewers and two independent synchronized MP4+WAV
reviewers. This is a connection to REAL installed adapters when present,
NOT a model download, quality certificate, automatic execution, Pi import
or owner review. CLI defaults to inspect-only, and never publishes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from .episode_assembly import digest, _ensure_private
from .model_package import verify_checkpoint, checkpoint_digest, ModelPackageError
from .real_media_evidence import private_file, _binary, EvidenceCaptureError
from .local_audio_review import AudioRunner, AudioModelError, review_voice
from .voice_qa import VoiceQAError
from .scene_ai_qa import SceneError
from .audio_continuity import AudioContinuityError
from .synchronized_av_review import AVRunner, AVReviewError, review_synchronized

SHA=re.compile(r"^[a-f0-9]{64}$")
PROVIDER=re.compile(r"^[a-z][a-z0-9_-]{2,63}$")
MODEL_ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")
ROLES=("asr_whispercpp","audio_pronunciation","audio_child_safety",
       "av_motion_sync","av_visual_child_safety")
REVIEWER_ROLES=ROLES[1:]
MAX_MODEL_BYTES=7*1024**3


class ModelBundleError(ValueError):
    pass


def _inside(path:Path,root:Path)->bool:
    return path.is_relative_to(root)


def _exact_file(file:str,expected:str,root:Path,*,executable:bool,
                model:bool=False,allow_directory:bool=True)->Path:
    if (not isinstance(file,str) or not file.startswith("/") or
        not isinstance(expected,str) or not SHA.fullmatch(expected)):
        raise ModelBundleError("Explicit absolute file SHA256 is required.")
    source=Path(file).expanduser()
    if source.is_symlink():
        raise ModelBundleError("Symlinked model or executable denied.")
    if model:
        return verify_checkpoint(source,expected,private_root=root,
                                 allow_directory=allow_directory)
    if not source.is_file():
        raise ModelBundleError("Executable must be a regular file.")
    real=Path(_binary(str(source)))
    if digest(real)!=expected:
        raise ModelBundleError("Executable bytes differ from pinned digest.")
    return real


class LocalModelBundle:
    def __init__(self,manifest:str|Path,expected_sha256:str):
        path=Path(manifest).expanduser()
        if (not path.is_absolute() or path.is_symlink()
            or not isinstance(expected_sha256,str)
            or not SHA.fullmatch(expected_sha256)):
            raise ModelBundleError("Private absolute manifest and owner-pinned SHA required.")
        path=path.resolve()
        _ensure_private(path.parent)
        if not path.is_file() or not 100<=path.stat().st_size<=50000:
            raise ModelBundleError("Private model manifest missing or oversized.")
        if digest(path)!=expected_sha256:
            raise ModelBundleError("Model bundle changed from owner-pinned manifest.")
        try:obj=json.loads(path.read_text(encoding="utf-8"))
        except (ValueError,UnicodeError,OSError) as exc:
            raise ModelBundleError("Malformed model bundle JSON.") from exc
        if (not isinstance(obj,dict) or set(obj)!={"schema_version",
              "deployment","private_root","network_required","tools",
              "reviewers","model_quality_qualified","execution_authorized",
              "public_release_authorized"} or
            obj["schema_version"]!=1 or obj["deployment"]!="local_offline" or
            obj["network_required"] is not False or
            obj["model_quality_qualified"] is not False or
            obj["execution_authorized"] is not False or
            obj["public_release_authorized"] is not False):
            raise ModelBundleError("Only unqualified offline private bundle allowed.")
        rawroot=Path(obj["private_root"]).expanduser()
        if not rawroot.is_absolute() or rawroot.is_symlink():
            raise ModelBundleError("Private model root must be an absolute directory.")
        root=_ensure_private(rawroot)
        if (not root.is_dir() or not path.is_relative_to(root) or
            (root.stat().st_mode & 0o022)):
            raise ModelBundleError("Owner model bundle must be inside a non-shared private root.")
        self.root=root
        tools=obj["tools"]
        if not isinstance(tools,dict) or set(tools)!={"ffmpeg","ffprobe"}:
            raise ModelBundleError("Both FFmpeg and FFprobe are required.")
        self.tools={}
        seen_files=set()
        for name in ("ffmpeg","ffprobe"):
            record=tools[name]
            if not isinstance(record,dict) or set(record)!={"binary","sha256"}:
                raise ModelBundleError("Media tool requires executable and digest.")
            p=_exact_file(record["binary"],record["sha256"],root,executable=True)
            if record["sha256"] in seen_files or p in seen_files:
                raise ModelBundleError("FFmpeg and FFprobe must be distinct binaries.")
            seen_files.update((p,record["sha256"]))
            self.tools[name]=str(p)
        entries=obj["reviewers"]
        if not isinstance(entries,dict) or set(entries)!=set(ROLES):
            raise ModelBundleError("Whisper and four explicit independent reviewer roles required.")
        self.reviewers={}
        providers=set()
        models=set()
        binaries=set()
        for role in ROLES:
            row=entries[role]
            if (not isinstance(row,dict) or
                set(row)!={"binary","binary_sha256","model","model_sha256",
                           "provider_id","model_id"} or
                not isinstance(row["provider_id"],str) or
                not PROVIDER.fullmatch(row["provider_id"]) or
                not isinstance(row["model_id"],str) or
                not MODEL_ID.fullmatch(row["model_id"])):
                raise ModelBundleError("Role-specific provider, model and binary required.")
            provider=row["provider_id"]
            if ((role=="asr_whispercpp" and provider!="asr_whispercpp") or
                (role!="asr_whispercpp" and provider=="asr_whispercpp") or
                provider in providers or row["model_id"] in models or
                row["model_sha256"] in models or
                row["binary_sha256"] in binaries):
                raise ModelBundleError("Reviewer providers, checkpoints and executables must be distinct.")
            binary=_exact_file(row["binary"],row["binary_sha256"],root,
                               executable=True)
            model=_exact_file(row["model"],row["model_sha256"],root,
                              executable=False,model=True,
                              allow_directory=role!="asr_whispercpp")
            if (binary in binaries or model in models or
                binary in seen_files or model in seen_files):
                raise ModelBundleError("Cannot reuse binary or checkpoint across roles.")
            providers.add(provider)
            models.update((row["model_id"],row["model_sha256"],model))
            binaries.update((row["binary_sha256"],binary))
            self.reviewers[role]=dict(row,binary=str(binary),model=str(model))
        self.manifest_sha256=expected_sha256
        self.path=path

    def public_status(self)->dict:
        return {
            "schema_version":1,
            "status":"M40_LOCAL_MODEL_BYTES_PINNED_NOT_QUALIFIED",
            "manifest_sha256":self.manifest_sha256,
            "roles":[{"role":role,
                      "provider_id":self.reviewers[role]["provider_id"],
                      "model_id":self.reviewers[role]["model_id"],
                      "checkpoint_sha256":self.reviewers[role]["model_sha256"]}
                     for role in ROLES],
            "tools_verified":True,"reviewer_role_count":5,
            "real_model_inference_tested":False,
            "model_capabilities_verified":False,
            "mac_pi_hardware_qualified":False,
            "write_performed":False,"network_used":False,
            "model_download_performed":False,
            "pi_scene_approved":False,"public_release_authorized":False,
        }

    def audio_runners(self)->tuple[AudioRunner,AudioRunner]:
        result=[]
        for role in ("audio_pronunciation","audio_child_safety"):
            row=self.reviewers[role]
            result.append(AudioRunner(binary=row["binary"],
                expected_binary_sha=row["binary_sha256"],
                model=row["model"],expected_model_sha=row["model_sha256"],
                provider_id=row["provider_id"],model_id=row["model_id"]))
        return tuple(result)

    def av_runners(self)->tuple[AVRunner,AVRunner]:
        result=[]
        for role in ("av_motion_sync","av_visual_child_safety"):
            row=self.reviewers[role]
            result.append(AVRunner(binary=row["binary"],
                binary_sha=row["binary_sha256"],model=row["model"],
                model_sha=row["model_sha256"],provider_id=row["provider_id"],
                model_id=row["model_id"]))
        return tuple(result)

    def execute_review(self,*,kind:str,series_id:str,episode:int,scene:int,
                       job_id:str,wav:str|Path,wav_sha:str,
                       script:str|Path,script_sha:str,
                       rights_file:str|Path,out_dir:str|Path,
                       runner_key:bytes,language:str="ar",
                       mp4:str|Path|None=None,mp4_sha:str|None=None,
                       m10_report:str|Path|None=None)->dict:
        # Explicit opt-in happens in the CLI below. The library method
        # requires an exact current scene job and private HMAC signer key.
        if kind=="voice_synthesize":
            first,second=self.audio_runners()
            whisper=self.reviewers["asr_whispercpp"]
            result=review_voice(series_id=series_id,episode=episode,
                scene=scene,job_id=job_id,wav=wav,wav_sha=wav_sha,
                script=script,script_sha=script_sha,language=language,
                rights_file=rights_file,
                whisper_binary=whisper["binary"],
                whisper_model=whisper["model"],
                whisper_model_sha=whisper["model_sha256"],
                ffmpeg=self.tools["ffmpeg"],ffprobe=self.tools["ffprobe"],
                first=first,second=second,runner_key=runner_key,
                out_dir=out_dir)
        elif kind=="ltx_animate":
            if mp4 is None or mp4_sha is None or m10_report is None:
                raise ModelBundleError("LTX requires current MP4, SHA and real M10 receipt.")
            first,second=self.av_runners()
            result=review_synchronized(series_id=series_id,
                episode=episode,scene=scene,job_id=job_id,
                wav=wav,wav_sha=wav_sha,mp4=mp4,mp4_sha=mp4_sha,
                script=script,script_sha=script_sha,
                rights_file=rights_file,m10_report=m10_report,
                ffmpeg=self.tools["ffmpeg"],ffprobe=self.tools["ffprobe"],
                first=first,second=second,runner_key=runner_key,
                out_dir=out_dir)
        else:
            raise ModelBundleError("Only original voice/LTX reviewers are eligible.")
        return {**result,"m40_manifest_sha256":self.manifest_sha256,
                "private_upload_permitted":False,
                "real_model_competence_proven_by_m40":False,
                "public_release_authorized":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-model-bundle")
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--manifest-sha256",required=True)
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("inspect")
    for name in ("voice","video"):
        q=sub.add_parser(name)
        q.add_argument("--series",required=True)
        q.add_argument("--episode",type=int,required=True)
        q.add_argument("--scene",type=int,required=True)
        q.add_argument("--job-id",required=True)
        q.add_argument("--wav",required=True,type=Path)
        q.add_argument("--wav-sha256",required=True)
        q.add_argument("--script",required=True,type=Path)
        q.add_argument("--script-sha256",required=True)
        q.add_argument("--rights",required=True,type=Path)
        q.add_argument("--out",required=True,type=Path)
        if name=="voice":
            q.add_argument("--language",choices=("ar","en"),required=True)
        else:
            q.add_argument("--mp4",required=True,type=Path)
            q.add_argument("--mp4-sha256",required=True)
            q.add_argument("--m10-report",required=True,type=Path)
        q.add_argument("--execute",action="store_true")
    x=p.parse_args(argv)
    try:
        bundle=LocalModelBundle(x.manifest,x.manifest_sha256)
        if x.action=="inspect" or not x.execute:
            status=bundle.public_status()
            if x.action!="inspect":
                status={**status,"requested_stage":x.action,
                        "status":"M40_EXPLICIT_EXECUTION_REQUIRED_NO_MODEL_RUN"}
            print(json.dumps(status,ensure_ascii=False,indent=2))
            return 0
        result=bundle.execute_review(kind=("voice_synthesize"
            if x.action=="voice" else "ltx_animate"),
            series_id=x.series,episode=x.episode,scene=x.scene,
            job_id=x.job_id,wav=x.wav,wav_sha=x.wav_sha256,
            script=x.script,script_sha=x.script_sha256,
            rights_file=x.rights,out_dir=x.out,
            language=x.language if x.action=="voice" else "ar",
            mp4=getattr(x,"mp4",None),mp4_sha=getattr(x,"mp4_sha256",None),
            m10_report=getattr(x,"m10_report",None),
            runner_key=os.environ.get("KIDS_STUDIO_SCENE_QA_RUNNER_KEY","").encode())
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ModelBundleError,ModelPackageError,AudioModelError,AVReviewError,EvidenceCaptureError,
            VoiceQAError,SceneError,AudioContinuityError,
            OSError,ValueError,TypeError,KeyError) as exc:
        print("M40_MODEL_BUNDLE_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
