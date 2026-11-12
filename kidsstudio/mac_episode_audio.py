"""Opt-in Mac pilot: mux an existing verified Godot preview and original WAV.

No network, TTS model, cloud service, queue, Pi transfer or YouTube activity.
Requires a user-supplied rights-cleared PCM WAV and a silent H.264 MP4.
Preview is read-only; --execute-mux is the only path that launches ffmpeg.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import wave

from .optional_tool_evidence import ToolEvidenceError, private_evidence_file
from .transfer_verify import verify_staged_file

SHA = re.compile(r"[a-fA-F0-9]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,158}\.mp4\Z")
FPS = {Fraction(24), Fraction(25), Fraction(30), Fraction(30000, 1001)}
MAX_BYTES = 20 * 1024**3


class EpisodeMuxError(ValueError):
    """The pilot output is unsafe, invalid or unqualified."""


def _private_root(root: str | Path) -> Path:
    path = Path(os.path.abspath(os.path.expanduser(str(root))))
    if (any(part.is_symlink() for part in (path, *path.parents))
            or not path.is_dir()
            or any((p / ".git").exists() for p in (path, *path.parents))):
        raise EpisodeMuxError("Existing private directory outside Git required.")
    info = path.stat()
    if (info.st_mode & 0o077 or
            (os.name == "posix" and info.st_uid != os.getuid())):
        raise EpisodeMuxError("Owner-controlled 0700 directory required.")
    return path


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while piece := stream.read(1024 * 1024):
            digest.update(piece)
    return digest.hexdigest()


def _probe(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,"
        "avg_frame_rate,sample_rate,channels", "-of", "json", str(path),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EpisodeMuxError("Local ffprobe could not inspect media.") from exc
    if (completed.returncode != 0 or len(completed.stdout) > 64 * 1024):
        raise EpisodeMuxError("Local ffprobe rejected media.")
    try:
        data = json.loads(completed.stdout)
    except (ValueError, UnicodeError) as exc:
        raise EpisodeMuxError("Local ffprobe metadata malformed.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("streams"), list):
        raise EpisodeMuxError("Local media streams missing.")
    if len(data["streams"]) > 8:
        raise EpisodeMuxError("Too many media streams.")
    return data


def _duration(data: dict) -> float:
    try:
        value = float(data["format"]["duration"])
    except (ValueError, TypeError, KeyError) as exc:
        raise EpisodeMuxError("Video duration missing.") from exc
    if not 4 <= value <= 600:
        raise EpisodeMuxError("Video duration must be 4–600 seconds.")
    return value


def _check_video(info: dict, *, with_audio: bool) -> float:
    streams = info["streams"]
    videos = [s for s in streams if isinstance(s, dict)
              and s.get("codec_type") == "video"]
    audios = [s for s in streams if isinstance(s, dict)
              and s.get("codec_type") == "audio"]
    if len(videos) != 1 or len(audios) != int(with_audio) or len(streams) != 1 + int(with_audio):
        raise EpisodeMuxError("Expected one video and required number of audio tracks.")
    video = videos[0]
    try:
        fps = Fraction(str(video["avg_frame_rate"]))
    except (KeyError, ValueError, ZeroDivisionError, TypeError) as exc:
        raise EpisodeMuxError("Video frame rate is invalid.") from exc
    if (video.get("codec_name") != "h264"
            or video.get("pix_fmt") != "yuv420p"
            or (video.get("width"), video.get("height")) != (1280, 720)
            or fps not in FPS):
        raise EpisodeMuxError("Video profile is not KidsStudio 720p H.264.")
    if with_audio:
        audio = audios[0]
        if (audio.get("codec_name") != "aac"
                or str(audio.get("sample_rate")) != "48000"
                or audio.get("channels") != 2):
            raise EpisodeMuxError("Output audio must be stereo AAC 48kHz.")
    return _duration(info)


def _wav_duration(file: Path) -> float:
    try:
        with wave.open(str(file), "rb") as audio:
            channels, width, sample_rate = (
                audio.getnchannels(), audio.getsampwidth(), audio.getframerate())
            seconds = audio.getnframes() / sample_rate if sample_rate else 0
            if (audio.getcomptype() != "NONE" or channels not in (1, 2)
                    or width != 2 or not 16000 <= sample_rate <= 96000
                    or not 3 <= seconds <= 600):
                raise EpisodeMuxError("Narration must be uncompressed 16-bit PCM WAV.")
            return seconds
    except (wave.Error, EOFError, OSError) as exc:
        raise EpisodeMuxError("Narration WAV is unreadable.") from exc


def mux_episode_pilot(
    *, video_root: str, video_name: str, video_sha256: str,
    narration_root: str, narration_name: str, narration_sha256: str,
    output_root: str, output_name: str,
    execute: bool = False,
) -> dict:
    if not all(isinstance(s, str) and SHA.fullmatch(s)
               for s in (video_sha256, narration_sha256)):
        raise EpisodeMuxError("Both independent input SHA256 values are required.")
    if not isinstance(output_name, str) or not NAME.fullmatch(output_name):
        raise EpisodeMuxError("Unsafe output MP4 name.")
    if not isinstance(video_name, str) or not video_name.endswith(".mp4"):
        raise EpisodeMuxError("Silent Godot input must be an MP4.")
    if not isinstance(narration_name, str) or not narration_name.endswith(".wav"):
        raise EpisodeMuxError("Narration input must be a WAV.")
    video = private_evidence_file(video_root, video_name, max_bytes=MAX_BYTES)
    narration = private_evidence_file(narration_root, narration_name, max_bytes=1024**3)
    if any(verify_staged_file(root=root, relative_path=name,
                              expected_sha256=sha)["status"] != "VERIFIED"
           for root, name, sha in (
               (video_root, video_name, video_sha256),
               (narration_root, narration_name, narration_sha256))):
        raise EpisodeMuxError("Input checksum mismatch.")
    dest_root = _private_root(output_root)
    if dest_root in (video.parent, narration.parent) and output_name in (
            video.name, narration.name):
        raise EpisodeMuxError("Cannot overwrite input media.")
    target = dest_root / output_name
    if target.exists() or target.is_symlink():
        raise FileExistsError("Private output already exists; never overwrite.")
    video_duration = _check_video(_probe(video), with_audio=False)
    narration_duration = _wav_duration(narration)
    if abs(video_duration - narration_duration) > 0.75:
        raise EpisodeMuxError("Narration length differs from animation by more than 750ms.")
    report = {
        "schema_version": 1,
        "status": "MAC_EPISODE_PREVIEW_READY" if not execute else "MAC_EPISODE_MUX_PENDING",
        "video_sha256": video_sha256.lower(),
        "narration_sha256": narration_sha256.lower(),
        "video_duration_seconds": round(video_duration, 3),
        "narration_duration_seconds": round(narration_duration, 3),
        "ffmpeg_executed": False,
        "real_arabic_voice_quality_reviewed": False,
        "local_audio_visual_review_required": True,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }
    if not execute:
        return report
    temp = dest_root / (".episode-pending-" + secrets.token_hex(12) + ".mp4")
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-n", "-i", str(video), "-i", str(narration),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-ar", "48000", "-ac", "2",
        "-af", "apad", "-t", f"{video_duration:.3f}",
        "-map_metadata", "-1", "-movflags", "+faststart",
        "-f", "mp4", str(temp),
    ]
    try:
        try:
            done = subprocess.run(command, capture_output=True,
                                  timeout=1800, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EpisodeMuxError("Local FFmpeg mux process failed.") from exc
        if done.returncode != 0:
            raise EpisodeMuxError("Local FFmpeg mux rejected the inputs.")
        if not temp.is_file() or not 1 <= temp.stat().st_size <= MAX_BYTES:
            raise EpisodeMuxError("Muxed MP4 was not created correctly.")
        os.chmod(temp, 0o600)
        final_duration = _check_video(_probe(temp), with_audio=True)
        if abs(final_duration - video_duration) > 0.75:
            raise EpisodeMuxError("Muxed video duration deviates from source.")
        if _hash(video) != video_sha256.lower() or _hash(narration) != narration_sha256.lower():
            raise EpisodeMuxError("Source bytes changed while muxing.")
        with temp.open("rb") as inp:
            final_bytes = os.fstat(inp.fileno()).st_size
            final_sha256 = hashlib.file_digest(inp, "sha256").hexdigest()
            os.fsync(inp.fileno())
        # Publish by hard-link only after complete checks; never replace.
        os.link(temp, target, follow_symlinks=False)
        dirfd = os.open(dest_root, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
        report["status"] = "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED"
        report["ffmpeg_executed"] = True
        report["final_mp4_sha256"] = final_sha256
        report["final_mp4_bytes"] = final_bytes
    finally:
        temp.unlink(missing_ok=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mac silent Godot + Arabic PCM narration pilot")
    for arg in ("video-root", "video-name", "video-sha256",
                "narration-root", "narration-name", "narration-sha256",
                "output-root", "output-name"):
        parser.add_argument("--" + arg, required=True)
    parser.add_argument("--execute-mux", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = mux_episode_pilot(
            video_root=args.video_root, video_name=args.video_name,
            video_sha256=args.video_sha256,
            narration_root=args.narration_root,
            narration_name=args.narration_name,
            narration_sha256=args.narration_sha256,
            output_root=args.output_root, output_name=args.output_name,
            execute=args.execute_mux,
        )
    except (EpisodeMuxError, ToolEvidenceError, OSError, ValueError):
        print(json.dumps({"status": "MAC_EPISODE_MUX_REJECTED",
                          "youtube_upload_performed": False,
                          "publication_approved": False}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
