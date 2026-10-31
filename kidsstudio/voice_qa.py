"""M23 offline exact-WAV technical gate, never a voice/rights approval.

Reads locally rendered WAV bytes, probes real container/PCM metadata with
FFprobe and decodes the entire audio through FFmpeg into capped 16k mono
signed PCM. Technical gates check format, SHA, duration, measurable voice
energy and excessive clipping/silence. A passing report still requires
the owner to listen, confirm words/voice suitability and rights.
"""
from __future__ import annotations

import argparse
from array import array
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from .episode_assembly import digest, _ensure_private
from .episode_quality import save_report
from .real_media_evidence import media_subprocess_env

SHA = re.compile(r"^[0-9a-f]{64}$")
JOB = re.compile(r"^[0-9a-f]{32}$")
PCM_CODECS = frozenset({
    "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le",
})
CHECKS = (
    "media_sha256_matches", "wav_pcm_codec",
    "one_audio_stream_no_video", "sample_rate_supported",
    "channels_mono_or_stereo", "duration_bounded",
    "full_pcm_decode", "audible_energy", "not_heavily_clipped",
    "not_mostly_silent",
)
MAX_FILE_BYTES = 400_000_000


class VoiceQAError(ValueError):
    """Unsafe input or tool failure during private voice technical QA."""


def inspect_voice(
    file: str | Path, expected_sha256: str, job_id: str,
    script_sha256: str, *,
    ffprobe: str = "ffprobe", ffmpeg: str = "ffmpeg",
) -> dict[str, Any]:
    requested = Path(file).expanduser()
    if (not requested.is_absolute() or requested.is_symlink()
            or requested.suffix.lower() != ".wav"
            or not isinstance(expected_sha256, str)
            or not SHA.fullmatch(expected_sha256)
            or not isinstance(script_sha256, str)
            or not SHA.fullmatch(script_sha256)
            or not isinstance(job_id, str) or not JOB.fullmatch(job_id)):
        raise VoiceQAError("Absolute private WAV, original script SHA and job ID required.")
    path = requested.resolve()
    _ensure_private(path.parent)
    if (not path.is_file() or path.stat().st_size < 100
            or path.stat().st_size > MAX_FILE_BYTES):
        raise VoiceQAError("Private WAV missing or exceeds bounded size.")
    media_sha = digest(path)
    size = path.stat().st_size
    try:
        probe = subprocess.run([
            ffprobe, "-v", "error", "-show_entries",
            "format=format_name,duration:stream=codec_type,codec_name,"
            "sample_rate,channels", "-of", "json", str(path),
        ], capture_output=True, check=True, timeout=45,
            env=media_subprocess_env())
        data = json.loads(probe.stdout)
    except (OSError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, ValueError) as exc:
        raise VoiceQAError("FFprobe rejected private voice WAV.") from exc
    streams = data.get("streams", [])
    if not isinstance(streams, list) or not all(isinstance(x,dict) for x in streams):
        raise VoiceQAError("Malformed WAV probe streams.")
    audio = [x for x in streams if x.get("codec_type") == "audio"]
    stream = audio[0] if len(audio) == 1 else {}
    try:
        duration = float(data.get("format", {}).get("duration", "nan"))
        rate = int(stream.get("sample_rate", "0"))
        channels = int(stream.get("channels", 0))
    except (ValueError, TypeError, AttributeError):
        duration, rate, channels = float("nan"), 0, 0
    checks = {
        "media_sha256_matches": media_sha == expected_sha256,
        "wav_pcm_codec": (
            data.get("format",{}).get("format_name") == "wav" and
            stream.get("codec_name") in PCM_CODECS),
        "one_audio_stream_no_video": len(audio) == 1 and len(streams) == 1,
        "sample_rate_supported": 16_000 <= rate <= 96_000,
        "channels_mono_or_stereo": channels in (1,2),
        "duration_bounded": math.isfinite(duration) and 0.2 <= duration <= 180,
        "full_pcm_decode": False,
        "audible_energy": False,
        "not_heavily_clipped": False,
        "not_mostly_silent": False,
    }
    rms_dbfs: float | None = None
    clipped_fraction: float | None = None
    quiet_fraction: float | None = None
    # Do not read/convert a mismatched or structurally suspect asset.
    if all(checks[k] for k in CHECKS[:6]):
        try:
            result = subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-xerror", "-i", str(path),
                "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
                "-f", "s16le", "-acodec", "pcm_s16le", "-",
            ], capture_output=True, timeout=90, check=False,
                env=media_subprocess_env())
            raw = result.stdout
            expected_samples = duration * 16000
            if (result.returncode == 0 and len(raw) % 2 == 0 and
                    0.8 * expected_samples <= len(raw) // 2 <=
                    1.2 * expected_samples and len(raw) <= 5_800_000):
                checks["full_pcm_decode"] = True
                pcm = array("h")
                pcm.frombytes(raw)
                if sys.byteorder != "little":
                    pcm.byteswap()
                if pcm:
                    count = len(pcm)
                    root = math.sqrt(sum(float(n)*n for n in pcm)/count)
                    rms_dbfs = round(20*math.log10(max(root/32768.0,1e-12)),2)
                    clipped_fraction = round(sum(abs(x)>=32760 for x in pcm)/count,6)
                    quiet_fraction = round(sum(abs(x)<180 for x in pcm)/count,6)
                    checks["audible_energy"] = -48 <= rms_dbfs <= -3
                    checks["not_heavily_clipped"] = clipped_fraction <= 0.01
                    checks["not_mostly_silent"] = quiet_fraction <= 0.90
        except (OSError, subprocess.TimeoutExpired):
            pass
    passed = all(checks.values())
    return {
        "schema_version": 1,
        "status": ("VOICE_TECH_PASS_OWNER_LISTENING_PENDING" if passed
                   else "VOICE_TECH_FAILED"),
        "job_id": job_id,
        "script_sha256": script_sha256,
        "voice_sha256": media_sha,
        "expected_voice_sha256": expected_sha256,
        "voice_bytes": size,
        "duration_seconds": round(duration,3) if checks["duration_bounded"] else None,
        "sample_rate_hz": rate if checks["sample_rate_supported"] else None,
        "channels": channels if checks["channels_mono_or_stereo"] else None,
        "rms_dbfs": rms_dbfs,
        "clipped_fraction": clipped_fraction,
        "quiet_fraction": quiet_fraction,
        "checks": checks,
        "owner_listening_performed": False,
        "text_matches_audio_verified": False,
        "speaker_identity_verified": False,
        "commercial_rights_verified": False,
        "publishing_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="studio-voice-qa",
        description="Local read-only WAV content QA; report is immutable, no approval.")
    p.add_argument("--wav",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--job-id",required=True)
    p.add_argument("--script-sha256",required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--ffprobe",default="ffprobe")
    p.add_argument("--ffmpeg",default="ffmpeg")
    args=p.parse_args(argv)
    try:
        result=inspect_voice(args.wav,args.sha256,args.job_id,
                             args.script_sha256,
                             ffprobe=args.ffprobe,ffmpeg=args.ffmpeg)
        result["report_sha256"] = save_report(result,args.report)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result["status"]=="VOICE_TECH_PASS_OWNER_LISTENING_PENDING" else 1
    except (VoiceQAError,OSError,ValueError) as exc:
        print("VOICE_TECH_QA_BLOCKED: "+type(exc).__name__,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
