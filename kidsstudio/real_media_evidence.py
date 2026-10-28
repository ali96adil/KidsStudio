"""M29: local, actual-media evidence capture for future trusted AI reviewers.

This module executes *real* local FFmpeg/FFprobe and an owner-installed
whisper.cpp `whisper-cli` binary. It NEVER calls an LLM to write a verdict,
does not produce a signed M28 PASS, and does not upload anything.

One optical evidence receipt pins the exact decoded source MP4 plus sampled
frame file hashes. One ASR receipt pins the actual WAV, actual separately
installed Whisper model, run exit status and transcript bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import wave

SHA=re.compile(r"^[a-f0-9]{64}$")
SAFE_NAME=re.compile(r"^[a-z][a-z0-9_-]{2,47}$")
PNG=bytes.fromhex("89504e470d0a1a0a")
MAX_MEDIA=10*1024**3


class EvidenceCaptureError(ValueError):
    pass


def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()


def private_file(path:str|Path,ext:str,*,max_bytes:int=MAX_MEDIA)->Path:
    raw=Path(path).expanduser()
    if not raw.is_absolute() or raw.is_symlink() or raw.suffix.lower()!=ext:
        raise EvidenceCaptureError("Absolute non-symlink media path required.")
    file=raw.resolve()
    minimum=1 if ext==".txt" else 100
    if not file.is_file() or not minimum<=file.stat().st_size<=max_bytes:
        raise EvidenceCaptureError("Missing or oversized private source file.")
    if any((p/".git").exists() for p in (file,*file.parents)):
        raise EvidenceCaptureError("Private source media must not be inside Git.")
    return file


def private_dir(path:str|Path)->Path:
    raw=Path(path).expanduser()
    if not raw.is_absolute() or raw.is_symlink() or raw.exists():
        raise EvidenceCaptureError("New absolute non-symlink output folder required.")
    if any((p/".git").exists() for p in (raw,*raw.parents)):
        raise EvidenceCaptureError("Do not store model/media output inside Git.")
    raw.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    out=raw.resolve()
    out.mkdir(mode=0o700)
    return out


def _binary(binary:str)->str:
    path=Path(binary).expanduser()
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise EvidenceCaptureError("Explicit absolute local executable required.")
    if not os.access(path,os.X_OK):
        raise EvidenceCaptureError("Executable cannot be launched.")
    return str(path.resolve())


def _exec(args:list[str],timeout:int,*,capture_limit:int=4096)->str:
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,timeout=timeout,check=False,
            stdin=subprocess.DEVNULL)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise EvidenceCaptureError("Local media/model execution unavailable or timed out.") from exc
    if p.returncode!=0 or len(p.stdout)>2_000_000 or len(p.stderr)>2_000_000:
        raise EvidenceCaptureError("Media/model command returned failure.")
    try:return p.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise EvidenceCaptureError("Invalid local tool output.") from exc


def _atomic_json(out:Path,object:dict)->Path:
    raw=json.dumps(object,sort_keys=True,ensure_ascii=False,
                   indent=2,allow_nan=False).encode("utf-8")
    target=out/"evidence.json"
    fd=os.open(str(target),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as f:
        f.write(raw)
        f.flush();os.fsync(f.fileno())
    return target


def capture_asr(*,wav:str|Path,script:str|Path,
                expected_wav_sha:str,expected_script_sha:str,
                whisper_binary:str,model:str|Path,
                expected_model_sha:str,
                out_dir:str|Path,language:str="ar",
                ffmpeg_binary:str|None=None)->dict:
    if language not in ("ar","en"):
        raise EvidenceCaptureError("Only explicit Arabic or English transcription.")
    if any(not isinstance(x,str) or not SHA.fullmatch(x) for x in (
        expected_wav_sha,expected_script_sha,expected_model_sha)):
        raise EvidenceCaptureError("All source/model SHA pins required.")
    wav=private_file(wav,".wav")
    script=private_file(script,".txt",max_bytes=12000)
    model_file=private_file(model,".bin",max_bytes=7*1024**3)
    if (digest(wav)!=expected_wav_sha or digest(script)!=expected_script_sha or
        digest(model_file)!=expected_model_sha):
        raise EvidenceCaptureError("WAV/source script/Whisper model differs from pinned bytes.")
    cmd=_binary(whisper_binary)
    out=private_dir(out_dir)
    # whisper.cpp reference CLI expects 16-kHz mono signed 16-bit WAV.
    # Preserve the originally SHA-pinned narration while converting the
    # private inference copy only when an explicit local FFmpeg is supplied.
    with wave.open(str(wav),"rb") as src:
        compatible=(src.getnchannels()==1 and src.getsampwidth()==2
                    and src.getframerate()==16000 and src.getcomptype()=="NONE")
    input_wav=wav
    if not compatible:
        if ffmpeg_binary is None:
            raise EvidenceCaptureError("whisper-cli needs 16-kHz mono PCM16 WAV; explicit FFmpeg conversion required.")
        convert=_binary(ffmpeg_binary)
        input_wav=out/"whisper_input_pcm16.wav"
        _exec([convert,"-hide_banner","-loglevel","error",
               "-nostdin","-n","-i",str(wav),
               "-vn","-ar","16000","-ac","1",
               "-c:a","pcm_s16le",str(input_wav)],timeout=120)
        with wave.open(str(input_wav),"rb") as fp:
            if not (fp.getnchannels()==1 and fp.getsampwidth()==2
                    and fp.getframerate()==16000 and fp.getcomptype()=="NONE"
                    and fp.getnframes()>=1600):
                raise EvidenceCaptureError("Converted Whisper audio is not valid PCM16 16k.")
    prefix=out/"transcription"
    # whisper.cpp CLI creates transcription.txt, from the actual WAV.
    # A different/invalid executable will fail unless it produces genuine
    # expected output; model provenance still needs runtime qualification.
    _exec([cmd,"-m",str(model_file),"-f",str(input_wav),"-l",language,
           "-otxt","-of",str(prefix),"-nt","-np"],timeout=900)
    transcription=out/"transcription.txt"
    if transcription.is_symlink() or not transcription.is_file():
        raise EvidenceCaptureError("Whisper CLI did not produce a transcript.")
    if not 2<=transcription.stat().st_size<=12000:
        raise EvidenceCaptureError("Transcript empty or too large.")
    raw=transcription.read_bytes()
    try:content=raw.decode("utf-8").strip()
    except UnicodeError as exc:
        raise EvidenceCaptureError("Non-UTF8 ASR transcript.") from exc
    if len(content)<2 or not any(c.isalpha() for c in content):
        raise EvidenceCaptureError("ASR gave no meaningful transcription.")
    if digest(wav)!=expected_wav_sha or digest(script)!=expected_script_sha:
        raise EvidenceCaptureError("Source mutated during ASR execution.")
    output={
        "schema_version":1,"status":"REAL_LOCAL_ASR_EXECUTED_NOT_QA_APPROVED",
        "language":language,
        "wav_sha256":expected_wav_sha,
        "whisper_input_sha256":digest(input_wav),
        "whisper_input_converted":input_wav!=wav,
        "script_sha256":expected_script_sha,
        "model_sha256":expected_model_sha,
        "transcript_sha256":hashlib.sha256(raw).hexdigest(),
        "transcript_file":str(transcription),
        "runner_executable":cmd,
        "runner_executable_sha256":digest(Path(cmd)),
        "source_rechecked_after_run":True,
        "review_passed":False,"publication_authorized":False
    }
    _atomic_json(out,output)
    return output


def capture_frames(*,mp4:str|Path,expected_mp4_sha:str,
                   ffprobe_binary:str,ffmpeg_binary:str,
                   out_dir:str|Path,frames:int=5)->dict:
    if not isinstance(expected_mp4_sha,str) or not SHA.fullmatch(expected_mp4_sha):
        raise EvidenceCaptureError("Expected source MP4 SHA required.")
    if type(frames) is not int or not 3<=frames<=12:
        raise EvidenceCaptureError("Bounded number of actual frames required.")
    mp4=private_file(mp4,".mp4")
    if digest(mp4)!=expected_mp4_sha:
        raise EvidenceCaptureError("MP4 changed before capture.")
    probe=_binary(ffprobe_binary)
    transcode=_binary(ffmpeg_binary)
    stdout=_exec([probe,"-v","error","-select_streams","v:0",
        "-show_entries","stream=codec_type,width,height,duration",
        "-show_entries","format=duration",
        "-of","json",str(mp4)],timeout=60)
    try:info=json.loads(stdout)
    except (TypeError,ValueError) as exc:
        raise EvidenceCaptureError("FFprobe returned no valid media metadata.") from exc
    streams=info.get("streams")
    if (not isinstance(streams,list) or len(streams)!=1 or
        streams[0].get("codec_type")!="video" or
        type(streams[0].get("width")) is not int or
        type(streams[0].get("height")) is not int or
        not 128<=streams[0]["width"]<=7680 or
        not 128<=streams[0]["height"]<=4320):
        raise EvidenceCaptureError("First video stream missing/invalid dimensions.")
    try:duration=float(info["format"]["duration"])
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        raise EvidenceCaptureError("No trustworthy MP4 duration.") from exc
    if not math.isfinite(duration) or not 2<=duration<=900:
        raise EvidenceCaptureError("Unsupported MP4 duration.")
    out=private_dir(out_dir)
    manifest=[]
    # Spread frames across full episode and avoid zero/last timestamp.
    for i in range(frames):
        t=round(duration*(i+1)/(frames+1),3)
        path=out/(f"frame_{i+1:02d}.png")
        _exec([transcode,"-hide_banner","-loglevel","error",
            "-nostdin","-n","-ss",f"{t:.3f}","-i",str(mp4),
            "-map","0:v:0","-frames:v","1",
            "-vf","scale='min(960,iw)':-2","-f","image2",
            "-c:v","png",str(path)],timeout=90)
        if path.is_symlink() or not path.is_file() or not 100<=path.stat().st_size<=10_000_000:
            raise EvidenceCaptureError("Expected real decoded frame missing.")
        with path.open("rb") as fp:header=fp.read(8)
        if header!=PNG:
            raise EvidenceCaptureError("FFmpeg frame did not decode to PNG.")
        manifest.append({"timestamp_seconds":t,
                         "file":str(path),"sha256":digest(path)})
    if digest(mp4)!=expected_mp4_sha:
        raise EvidenceCaptureError("Source video mutated during frame extraction.")
    frame_doc={"schema_version":1,
               "a2v_sha256":expected_mp4_sha,"frames":manifest}
    manifest_path=out/"frames_manifest.json"
    blob=json.dumps(frame_doc,sort_keys=True,ensure_ascii=False,
                    indent=2).encode("utf-8")
    fd=os.open(str(manifest_path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as file:
        file.write(blob);file.flush();os.fsync(file.fileno())
    receipt={
        "schema_version":1,
        "status":"REAL_FFMPEG_FRAMES_CAPTURED_NOT_AI_REVIEWED",
        "a2v_sha256":expected_mp4_sha,
        "frames_manifest_sha256":hashlib.sha256(blob).hexdigest(),
        "frames_manifest_file":str(manifest_path),
        "frame_count":frames,
        "duration_seconds":duration,
        "ffmpeg_executable_sha256":digest(Path(transcode)),
        "ffprobe_executable_sha256":digest(Path(probe)),
        "source_rechecked_after_run":True,
        "review_passed":False,"publication_authorized":False
    }
    _atomic_json(out,receipt)
    return receipt


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="studio-capture-real-evidence")
    subs=p.add_subparsers(dest="action",required=True)
    a=subs.add_parser("asr")
    a.add_argument("--wav",type=Path,required=True)
    a.add_argument("--wav-sha256",required=True)
    a.add_argument("--script",type=Path,required=True)
    a.add_argument("--script-sha256",required=True)
    a.add_argument("--whisper",required=True)
    a.add_argument("--model",type=Path,required=True)
    a.add_argument("--model-sha256",required=True)
    a.add_argument("--language",choices=["ar","en"],required=True)
    a.add_argument("--ffmpeg",help="Explicit local FFmpeg for WAV-to-16k PCM conversion")
    b=subs.add_parser("frames")
    b.add_argument("--mp4",type=Path,required=True)
    b.add_argument("--mp4-sha256",required=True)
    b.add_argument("--ffmpeg",required=True)
    b.add_argument("--ffprobe",required=True)
    b.add_argument("--frames",type=int,default=5)
    for obj in (a,b):obj.add_argument("--out",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.action=="asr":
            result=capture_asr(wav=args.wav,script=args.script,
                expected_wav_sha=args.wav_sha256,
                expected_script_sha=args.script_sha256,
                whisper_binary=args.whisper,model=args.model,
                expected_model_sha=args.model_sha256,
                out_dir=args.out,language=args.language,
                ffmpeg_binary=args.ffmpeg)
        else:
            result=capture_frames(mp4=args.mp4,
                expected_mp4_sha=args.mp4_sha256,
                ffmpeg_binary=args.ffmpeg,
                ffprobe_binary=args.ffprobe,
                out_dir=args.out,frames=args.frames)
        print(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2))
        return 0
    except (EvidenceCaptureError,OSError,ValueError,TypeError) as exc:
        print("REAL_EVIDENCE_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
