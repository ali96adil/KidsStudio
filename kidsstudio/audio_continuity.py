"""M10 local A2V narration continuity analysis (NOT lip-sync verification).

Decodes the approved WAV and embedded A2V MP4 audio to a bounded mono PCM
envelope, estimates best energy-profile correlation and lag. This can detect
grossly wrong or silent narration, but energy similarity DOES NOT prove speaker
identity, literal spoken words, safe content or correct Bunny mouth movements.
"""
from __future__ import annotations

import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys
from typing import Callable, Any

from .episode_assembly import digest, _ensure_private
from .episode_quality import save_report

RATE=8000
WINDOW=160  # 20ms
MAX_SAMPLES=RATE*180
MAX_LAG=30   # 600ms
MIN_ENERGY=0.004


class AudioContinuityError(ValueError):
    """Media may be missing, changed, undecodable or outside approved scope."""


def decode_pcm(path: Path, ffmpeg: str) -> array:
    try:
        result=subprocess.run([
            ffmpeg,"-nostdin","-hide_banner","-v","error","-xerror",
            "-i",str(path),"-map","0:a:0","-vn","-ac","1",
            "-ar",str(RATE),"-t","180","-f","s16le","pipe:1"],
            check=True,timeout=180,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    except (OSError,subprocess.SubprocessError) as exc:
        raise AudioContinuityError("Local FFmpeg audio stream cannot be decoded.") from exc
    raw=result.stdout
    if not raw or len(raw)>MAX_SAMPLES*2 or len(raw)%2:
        raise AudioContinuityError("Decoded PCM is empty, oversized or malformed.")
    samples=array("h")
    samples.frombytes(raw)
    if sys.byteorder!="little":
        samples.byteswap()
    return samples


def _energy(samples: array) -> list[float]:
    if len(samples)<2*RATE or len(samples)>MAX_SAMPLES:
        raise AudioContinuityError("Expected 2..180 seconds of decoded audio.")
    num=len(samples)//WINDOW
    energy=[]
    for i in range(num):
        frame=samples[i*WINDOW:(i+1)*WINDOW]
        mean=sum(float(v)*v for v in frame)/len(frame)
        energy.append(math.sqrt(mean)/32768.0)
    return energy


def _pearson(x: list[float], y: list[float], lag: int) -> float:
    if lag >= 0:
        a,b=x[lag:],y[:len(x)-lag]
    else:
        a,b=x[:len(x)+lag],y[-lag:]
    n=min(len(a),len(b))
    if n<70:
        return -1.0
    a=a[:n];b=b[:n]
    ma=sum(a)/n;mb=sum(b)/n
    numerator=sum((u-ma)*(v-mb) for u,v in zip(a,b))
    da=sum((u-ma)**2 for u in a)
    db=sum((v-mb)**2 for v in b)
    if da<1e-4 or db<1e-4:
        return -1.0
    return numerator/math.sqrt(da*db)


def compare_voice_to_a2v(
    voice: str | Path, a2v: str | Path,
    *, voice_sha256: str, a2v_sha256: str, ffmpeg: str,
    decoder: Callable[[Path,str],array] = decode_pcm,
) -> dict[str,Any]:
    from re import fullmatch
    if not isinstance(voice_sha256,str) or not fullmatch("[a-f0-9]{64}",voice_sha256):
        raise AudioContinuityError("Approved voice SHA256 is missing.")
    if not isinstance(a2v_sha256,str) or not fullmatch("[a-f0-9]{64}",a2v_sha256):
        raise AudioContinuityError("Approved A2V SHA256 is missing.")
    originals=[]
    for candidate,suffix,expected in [
        (voice,".wav",voice_sha256),(a2v,".mp4",a2v_sha256)]:
        raw=Path(candidate).expanduser()
        if not raw.is_absolute() or raw.is_symlink():
            raise AudioContinuityError("Sources must be private absolute non-symlink files.")
        raw=raw.resolve()
        _ensure_private(raw.parent)
        if not raw.is_file() or raw.suffix.lower()!=suffix or not 0<raw.stat().st_size<=2_000_000_000:
            raise AudioContinuityError("Expected approved private WAV and A2V MP4.")
        if digest(raw)!=expected:
            raise AudioContinuityError("Source SHA256 differs from owner approval.")
        originals.append(raw)
    if not isinstance(ffmpeg,str) or not ffmpeg.startswith("/") or not Path(ffmpeg).is_file():
        raise AudioContinuityError("Pinned absolute local FFmpeg binary path required.")
    expected_voice=decoder(originals[0],ffmpeg)
    actual_a2v=decoder(originals[1],ffmpeg)
    # Revalidate after decoding so a concurrent source rewrite cannot pass.
    if digest(originals[0])!=voice_sha256 or digest(originals[1])!=a2v_sha256:
        raise AudioContinuityError("Source changed during PCM comparison.")
    if not isinstance(expected_voice,array) or not isinstance(actual_a2v,array):
        raise AudioContinuityError("PCM decoder contract requires array('h').")
    x=_energy(expected_voice);y=_energy(actual_a2v)
    voice_duration=len(expected_voice)/RATE
    video_audio_duration=len(actual_a2v)/RATE
    max_x=max(x); max_y=max(y)
    profile_distinctive=(max_x>=MIN_ENERGY and max_y>=MIN_ENERGY)
    duration_close=abs(voice_duration-video_audio_duration)<=1.2
    scores=[(lag,_pearson(x,y,lag)) for lag in range(-MAX_LAG,MAX_LAG+1)]
    lag,score=max(scores,key=lambda pair:pair[1])
    # A loudness-energy envelope is just a technical clue. 0.82 is a
    # conservative threshold, NOT a validated speech-identity classifier.
    compatible=profile_distinctive and duration_close and score>=0.82
    return {
        "schema_version":1,
        "status":("AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED"
                  if compatible else "AUDIO_CONTINUITY_UNVERIFIED"),
        "voice_sha256":voice_sha256,
        "a2v_sha256":a2v_sha256,
        "voice_seconds":round(voice_duration,3),
        "a2v_audio_seconds":round(video_audio_duration,3),
        "duration_close":duration_close,
        "envelope_correlation":round(score,4),
        "estimated_lag_seconds":round(lag*WINDOW/RATE,3),
        "energy_present":profile_distinctive,
        "audio_content_identity_proven":False,
        "speaker_identity_proven":False,
        "lip_sync_verified":False,
        "owner_audiovisual_review_required":True,
        "publishing_approved":False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(prog="studio-audio-continuity")
    p.add_argument("--voice",required=True,type=Path)
    p.add_argument("--voice-sha256",required=True)
    p.add_argument("--a2v",required=True,type=Path)
    p.add_argument("--a2v-sha256",required=True)
    p.add_argument("--ffmpeg",required=True)
    p.add_argument("--report",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        result=compare_voice_to_a2v(
            args.voice,args.a2v,voice_sha256=args.voice_sha256,
            a2v_sha256=args.a2v_sha256,ffmpeg=args.ffmpeg)
        checksum=save_report(result,args.report)
        print(json.dumps({**result,"report_sha256":checksum},indent=2,ensure_ascii=False))
        return 0 if result["status"]=="AUDIO_ENVELOPE_COMPATIBLE_HUMAN_QA_REQUIRED" else 1
    except (AudioContinuityError,OSError,ValueError) as exc:
        print("AUDIO_CONTINUITY_ERROR: "+str(exc),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
