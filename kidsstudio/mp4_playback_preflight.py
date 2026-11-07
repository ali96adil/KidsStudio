"""Read-only, SHA-pinned playback compatibility preflight for the Mac pilot.

Checks the actual private MP4 container, codecs and a few decoded samples.
No writes, network, transfers, uploads, authentication or publication.
Passing is NOT a human playback, sound-quality or pedagogical review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from .mac_episode_audio import _check_video, _probe
from .optional_tool_evidence import private_evidence_file
from .transfer_verify import verify_staged_file

_MAX_VIDEO_BYTES = 20 * 1024**3
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")
_FRAME_ROW = re.compile(rb"(?m)^0,\s*[-0-9]+,\s*[-0-9]+,")


class PlaybackPreflightError(ValueError):
    """A private MP4 failed the conservative local preview checks."""


def _faststart_atoms(file: Path) -> bool:
    """Parse only ISO BMFF top-level headers, never load or trust box payloads.

    A valid ftyp followed by a completed moov before mdat helps progressive
    playback, but does not guarantee that an arbitrary media player opens it.
    """
    total = file.stat().st_size
    offset = 0
    types: list[bytes] = []
    with file.open("rb") as stream:
        for _ in range(256):
            if offset == total:
                break
            if total - offset < 8:
                raise PlaybackPreflightError("Truncated MP4 box header.")
            stream.seek(offset)
            header = stream.read(8)
            if len(header) != 8:
                raise PlaybackPreflightError("Unreadable MP4 box header.")
            size = int.from_bytes(header[:4], "big")
            kind = header[4:8]
            box_header = 8
            if size == 1:
                if total - offset < 16:
                    raise PlaybackPreflightError("Truncated extended box header.")
                extended = stream.read(8)
                if len(extended) != 8:
                    raise PlaybackPreflightError("Unreadable extended box header.")
                size = int.from_bytes(extended, "big")
                box_header = 16
            elif size == 0:
                size = total - offset
                if kind != b"mdat":
                    raise PlaybackPreflightError("Unsupported unbounded MP4 box.")
            if size < box_header or size > total - offset:
                raise PlaybackPreflightError("Invalid MP4 box size.")
            types.append(kind)
            offset += size
        else:
            raise PlaybackPreflightError("Too many MP4 boxes.")
    if offset != total:
        raise PlaybackPreflightError("Incomplete MP4 box chain.")
    if not types or types[0] != b"ftyp":
        raise PlaybackPreflightError("Expected MP4 file-type header.")
    if types.count(b"moov") != 1 or types.count(b"mdat") != 1:
        raise PlaybackPreflightError("Expected one movie and media-data box.")
    if types.index(b"moov") >= types.index(b"mdat"):
        raise PlaybackPreflightError("MP4 moov is not before mdat.")
    return True


def _codec_profiles(file: Path) -> None:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,profile,level", "-of", "json", str(file),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, check=False, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PlaybackPreflightError("Cannot inspect local codec profiles.") from exc
    if result.returncode != 0 or len(result.stdout) > 65536:
        raise PlaybackPreflightError("Codec profile probe failed.")
    try:
        obj = json.loads(result.stdout)
        streams = obj["streams"]
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise PlaybackPreflightError("Invalid codec profile response.") from exc
    if not isinstance(streams, list) or len(streams) != 2 or not all(
        isinstance(s, dict) for s in streams
    ):
        raise PlaybackPreflightError("Unexpected codec profile streams.")
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if (len(videos) != 1 or len(audios) != 1
            or videos[0].get("profile") not in ("Baseline", "Constrained Baseline")
            or type(videos[0].get("level")) is not int
            or videos[0]["level"] > 31 or videos[0]["level"] < 10
            or audios[0].get("profile") != "LC"):
        raise PlaybackPreflightError("Unsupported H.264/AAC playback profiles.")


def _decode_sample(file: Path, *, kind: str, second: float) -> None:
    if kind not in ("video", "audio") or not 0 <= second <= 600:
        raise PlaybackPreflightError("Invalid sample request.")
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", f"{second:.3f}", "-i", str(file),
        "-map", "0:v:0" if kind == "video" else "0:a:0",
    ]
    if kind == "video":
        cmd.extend(["-frames:v", "1"])
    else:
        cmd.extend(["-t", "0.5"])
    cmd.extend(["-f", "framemd5", "pipe:1"])
    try:
        result = subprocess.run(cmd, capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PlaybackPreflightError("Local sample decode unavailable.") from exc
    if (result.returncode != 0 or len(result.stdout) > 65536
            or _FRAME_ROW.search(result.stdout) is None):
        raise PlaybackPreflightError("MP4 sample could not be decoded.")


def inspect_mp4_playback(*, root: str, relative_path: str,
                         expected_sha256: str) -> dict:
    """Read-only qualification of actual bytes; never a future-file guarantee."""
    if (not isinstance(expected_sha256, str) or not _SHA.fullmatch(expected_sha256)
            or not isinstance(relative_path, str)
            or not relative_path.endswith(".mp4")):
        raise PlaybackPreflightError("A private SHA-pinned MP4 is required.")
    file = private_evidence_file(root, relative_path, max_bytes=_MAX_VIDEO_BYTES)
    evidence = verify_staged_file(
        root=root, relative_path=relative_path, expected_sha256=expected_sha256)
    if evidence["status"] != "VERIFIED":
        raise PlaybackPreflightError("MP4 SHA256 mismatch.")
    _faststart_atoms(file)
    duration = _check_video(_probe(file), with_audio=True)
    _codec_profiles(file)
    for second in (0.0, duration / 2, max(0.0, duration - 0.75)):
        _decode_sample(file, kind="video", second=second)
    for second in (0.0, duration / 2):
        _decode_sample(file, kind="audio", second=second)
    # Catch ordinary edits during probing; not a TOCTOU/identity guarantee.
    after = verify_staged_file(
        root=root, relative_path=relative_path, expected_sha256=expected_sha256)
    if after["status"] != "VERIFIED" or after["bytes"] != evidence["bytes"]:
        raise PlaybackPreflightError("MP4 changed during preflight.")
    return {
        "schema_version": 1,
        "status": "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED",
        "video_sha256": expected_sha256.lower(),
        "video_bytes": after["bytes"],
        "duration_seconds": round(duration, 3),
        "faststart_moov_before_mdat": True,
        "h264_baseline_level_31_or_lower": True,
        "aac_lc_stereo_48000": True,
        "video_samples_decoded": 3,
        "audio_samples_decoded": 2,
        "entire_video_decoded": False,
        "owner_playback_reviewed": False,
        "arabic_voice_reviewed": False,
        "mac_hardware_tested": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline SHA-pinned H.264/AAC faststart MP4 check")
    parser.add_argument("--root", required=True)
    parser.add_argument("--relative-path", required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_mp4_playback(
            root=args.root, relative_path=args.relative_path,
            expected_sha256=args.expected_sha256)
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({
            "status": "MP4_PLAYBACK_PREFLIGHT_BLOCKED",
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
