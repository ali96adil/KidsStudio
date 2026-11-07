"""First playable, original Arabic colors pilot for a supervised Mac test.

Six original vector-like scenes drawn with Pillow, no copyrighted assets.
Optionally uses the user's installed offline macOS Arabic 'say' voice or an
owner-supplied SHA-pinned PCM WAV. Never connects to Pi, AI APIs or YouTube.
Default CLI is a no-write preview; --execute is required for local rendering.
This static illustrated pilot is NOT a substitute for the character-rig pipeline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import subprocess

from PIL import Image, ImageDraw

from .mac_episode_audio import (
    EpisodeMuxError, _check_video, _private_root, _probe, _wav_duration,
    mux_episode_pilot,
)
from .optional_tool_evidence import private_evidence_file
from .transfer_verify import verify_staged_file

SIZE = (1280, 720)
FPS = 24
SECONDS_PER_SCENE = 4
CUES = (
    ("hello", "أهلاً يا أصدقائي!"),
    ("palette", "هيا نتعلم الألوان."),
    ("apple", "الأحمر مثل التفاحة."),
    ("sun", "الأصفر مثل الشمس."),
    ("sky", "الأزرق مثل السماء."),
    ("recap", "رائع! تعلمنا ثلاثة ألوان."),
)
DURATION = SECONDS_PER_SCENE * len(CUES)
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,158}\.mp4\Z")
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z")
_VOICE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,39}\Z")
_BG = (251, 248, 237)
_RED = (227, 67, 69)
_YELLOW = (255, 196, 48)
_BLUE = (55, 134, 228)
_GREEN = (67, 164, 101)


def scene_image(scene: int) -> Image.Image:
    """Original visual cues; no external images, fonts, voices or logos."""
    if type(scene) is not int or not 0 <= scene < len(CUES):
        raise EpisodeMuxError("Unsupported story beat.")
    image = Image.new("RGB", SIZE, _BG)
    draw = ImageDraw.Draw(image)
    # Same soft background framing for each card.
    draw.rounded_rectangle((88, 54, 1192, 666), radius=78,
                           fill=(239, 245, 245))
    draw.rounded_rectangle((128, 92, 1152, 628), radius=58,
                           fill=(255, 253, 247))
    if scene == 0:
        # Friendly original smiling color mascot, waving its left hand.
        draw.ellipse((410, 185, 870, 595), fill=(246, 193, 112))
        draw.ellipse((523, 330, 554, 361), fill=(55, 58, 75))
        draw.ellipse((716, 330, 747, 361), fill=(55, 58, 75))
        draw.arc((558, 359, 713, 481), start=5, end=175,
                 fill=(72, 71, 78), width=10)
        draw.line([(404, 410), (306, 345), (266, 265)],
                  fill=(246, 193, 112), width=35, joint="curve")
        draw.ellipse((235, 226, 296, 289), fill=(246, 193, 112))
        draw.ellipse((998, 210, 1050, 262), fill=_BLUE)
        draw.ellipse((1040, 285, 1092, 337), fill=_RED)
        draw.ellipse((985, 370, 1037, 422), fill=_YELLOW)
    elif scene in (1, 5):
        for cx, color in ((390, _RED), (640, _YELLOW), (890, _BLUE)):
            draw.ellipse((cx-99, 258, cx+99, 456), fill=color,
                         outline=(244, 244, 238), width=8)
            draw.ellipse((cx-44, 294, cx-16, 322), fill=(255, 255, 255))
        if scene == 5:
            for cx in (390, 640, 890):
                draw.arc((cx-55, 475, cx+55, 565), 5, 175,
                         fill=(76, 87, 96), width=7)
    elif scene == 2:
        # Red apple, stem and leaves; no third-party fruit image.
        draw.ellipse((435, 240, 685, 555), fill=_RED)
        draw.ellipse((583, 240, 845, 555), fill=_RED)
        draw.ellipse((510, 238, 766, 548), fill=_RED)
        draw.line([(641, 250), (658, 174)], fill=(103, 77, 42), width=16)
        draw.ellipse((652, 174, 772, 231), fill=_GREEN)
        draw.ellipse((511, 312, 548, 369), fill=(255, 171, 153))
    elif scene == 3:
        # Yellow sun with unmistakable rays.
        for x1, y1, x2, y2 in (
            (640, 145, 640, 240), (640, 500, 640, 583),
            (405, 365, 500, 365), (780, 365, 890, 365),
            (468, 198, 534, 265), (746, 465, 815, 534),
            (466, 532, 534, 465), (748, 265, 815, 198),
        ):
            draw.line((x1, y1, x2, y2), fill=_YELLOW, width=26)
        draw.ellipse((500, 227, 780, 507), fill=_YELLOW)
        draw.ellipse((578, 339, 600, 360), fill=(91, 81, 63))
        draw.ellipse((692, 339, 714, 360), fill=(91, 81, 63))
        draw.arc((593, 356, 702, 439), 5, 175, fill=(91, 81, 63), width=7)
    elif scene == 4:
        draw.rounded_rectangle((142, 106, 1138, 616), radius=49, fill=_BLUE)
        for x, y, s in ((274, 260, 1), (677, 220, 2), (945, 355, 1)):
            draw.ellipse((x, y, x+155*s, y+78*s),
                         fill=(251, 253, 255))
            draw.ellipse((x+35*s, y-37*s, x+107*s, y+58*s),
                         fill=(251, 253, 255))
            draw.ellipse((x+80*s, y-18*s, x+147*s, y+60*s),
                         fill=(251, 253, 255))
    return image


def _sha(file: Path) -> str:
    digest = hashlib.sha256()
    with file.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _run(command: list[str], *, timeout: int = 480, text: bool = False) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, check=False,
                                timeout=timeout, text=text)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EpisodeMuxError("Required local media process unavailable or timed out.") from exc
    if result.returncode != 0:
        raise EpisodeMuxError("Local media process failed; inspect installed tools.")
    return result


def _arabic_voice(requested: str | None) -> str:
    if platform.system() != "Darwin":
        raise EpisodeMuxError("macOS Arabic system voice required for local speech.")
    voices = _run(["say", "-v", "?"], timeout=15, text=True).stdout
    if not isinstance(voices, str) or len(voices) > 500_000:
        raise EpisodeMuxError("Installed voice list unavailable.")
    # macOS say -v ? typically lists 'VoiceName ar_SA # sample text'.
    found = re.findall(r"(?m)^\s*([A-Za-z][A-Za-z0-9_-]{0,39})\s+ar[_-][A-Za-z_]+\b",
                       voices, re.IGNORECASE)
    if not found:
        raise EpisodeMuxError("No installed offline Arabic macOS voice detected.")
    if requested is not None:
        if not _VOICE.fullmatch(requested) or requested not in found:
            raise EpisodeMuxError("Requested voice is not installed as Arabic.")
        return requested
    return found[0]


def _synthesize_wav(stage: Path, *, voice: str | None) -> Path:
    picked = _arabic_voice(voice)
    inputs: list[str] = []
    filters: list[str] = []
    for i, (_, speech) in enumerate(CUES):
        aiff = stage / f"voice-{i}.aiff"
        _run(["say", "-v", picked, "-r", "185", "-o", str(aiff), speech],
             timeout=90)
        info = _probe(aiff)
        try:
            duration = float(info["format"]["duration"])
        except (TypeError, ValueError, KeyError) as exc:
            raise EpisodeMuxError("Cannot measure synthesized speech.") from exc
        if not 0 < duration < SECONDS_PER_SCENE - 0.10:
            raise EpisodeMuxError("Speech too long for beat; retime instead of truncating.")
        inputs.extend(["-i", str(aiff)])
        filters.append(
            f"[{i}:a]aresample=48000,apad,atrim=0:{SECONDS_PER_SCENE},"
            f"asetpts=PTS-STARTPTS[a{i}]")
    joins = "".join(f"[a{i}]" for i in range(len(CUES)))
    graph = ";".join(filters + [
        f"{joins}concat=n={len(CUES)}:v=0:a=1[out]"])
    voice_wav = stage / "arabic_voice.wav"
    _run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
          "-n", *inputs, "-filter_complex", graph, "-map", "[out]",
          "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", str(voice_wav)])
    os.chmod(voice_wav, 0o600)
    if abs(_wav_duration(voice_wav) - DURATION) > 0.1:
        raise EpisodeMuxError("Synthesized speech track duration incorrect.")
    return voice_wav


def _render_silent(stage: Path) -> Path:
    inputs: list[str] = []
    for i in range(len(CUES)):
        path = stage / f"scene-{i}.png"
        scene_image(i).save(path, format="PNG")
        os.chmod(path, 0o600)
        inputs.extend(["-loop", "1", "-framerate", str(FPS),
                       "-t", str(SECONDS_PER_SCENE), "-i", str(path)])
    graph = "".join(f"[{i}:v]" for i in range(len(CUES))) + (
        f"concat=n={len(CUES)}:v=1:a=0[out]")
    movie = stage / "silent.mp4"
    _run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
          "-n", *inputs, "-filter_complex", graph, "-map", "[out]",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
          "-t", str(DURATION), "-movflags", "+faststart", str(movie)],
         timeout=900)
    os.chmod(movie, 0o600)
    checked_duration = _check_video(_probe(movie), with_audio=False)
    if abs(checked_duration - DURATION) > .15:
        raise EpisodeMuxError("Illustrated pilot duration differs from storyboard.")
    return movie


def run_first_colors_episode(
    *, output_root: str, output_name: str = "colors_ar_01.mp4",
    execute: bool = False, voice_mode: str = "macos",
    mac_voice: str | None = None,
    narration_root: str | None = None,
    narration_name: str | None = None,
    narration_sha256: str | None = None,
) -> dict:
    if type(execute) is not bool or not _NAME.fullmatch(output_name):
        raise EpisodeMuxError("Unsafe pilot execution mode or destination.")
    if voice_mode not in ("macos", "supplied_wav"):
        raise EpisodeMuxError("Select offline macOS voice or supplied WAV.")
    root = _private_root(output_root)
    if (root / output_name).exists() or (root / output_name).is_symlink():
        raise FileExistsError("Pilot episode already exists; never replace.")
    checked_wav: Path | None = None
    if voice_mode == "supplied_wav":
        if (not narration_root or not isinstance(narration_name, str)
                or not narration_name.endswith(".wav")
                or not isinstance(narration_sha256, str)
                or not _SHA.fullmatch(narration_sha256)):
            raise EpisodeMuxError("Exact SHA-pinned original WAV is required.")
        checked_wav = private_evidence_file(
            narration_root, narration_name, max_bytes=1024**3)
        report = verify_staged_file(
            root=narration_root, relative_path=narration_name,
            expected_sha256=narration_sha256, max_bytes=1024**3)
        if report["status"] != "VERIFIED" or abs(_wav_duration(checked_wav)-DURATION) > .75:
            raise EpisodeMuxError("Supplied voice SHA or episode duration invalid.")
    if execute and voice_mode == "macos":
        # Detect the required installed voice before creating intermediate files.
        _arabic_voice(mac_voice)
    result = {
        "schema_version": 1,
        "status": "COLORS_EPISODE_PREVIEW_ONLY" if not execute
                  else "COLORS_EPISODE_RENDER_UNVERIFIED",
        "duration_seconds": DURATION,
        "fps": FPS, "size": list(SIZE),
        "original_scenes": [x[0] for x in CUES],
        "narration_source": voice_mode,
        "static_illustrations_only": True,
        "render_executed": False,
        "voice_pronunciation_reviewed": False,
        "full_episode_reviewed": False,
        "pi_transfer_performed": False,
        "youtube_upload_performed": False,
        "publication_approved": False,
    }
    if not execute:
        return result
    stage = root / (output_name.removesuffix(".mp4") + "-pilot-sources")
    stage.mkdir(mode=0o700)
    movie = _render_silent(stage)
    voice_path = _synthesize_wav(stage, voice=mac_voice) if checked_wav is None else checked_wav
    voice_root = str(stage) if checked_wav is None else str(Path(narration_root))
    voice_name = voice_path.name
    muxed = mux_episode_pilot(
        video_root=str(stage), video_name=movie.name, video_sha256=_sha(movie),
        narration_root=voice_root, narration_name=voice_name,
        narration_sha256=_sha(voice_path),
        output_root=str(root), output_name=output_name, execute=True)
    if muxed["status"] != "MAC_EPISODE_MUXED_PRIVATE_UNREVIEWED":
        raise EpisodeMuxError("Original colors video/audio mux did not complete.")
    result.update({
        "status": "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED",
        "render_executed": True,
        "final_mp4_sha256": muxed["final_mp4_sha256"],
        "final_mp4_bytes": muxed["final_mp4_bytes"],
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Original six-scene Arabic colors pilot (offline Mac only)")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--output-name", default="colors_ar_01.mp4")
    parser.add_argument("--voice-mode", choices=("macos", "supplied_wav"),
                        default="macos")
    parser.add_argument("--mac-voice")
    parser.add_argument("--narration-root")
    parser.add_argument("--narration-name")
    parser.add_argument("--narration-sha256")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_first_colors_episode(
            output_root=args.output_root, output_name=args.output_name,
            voice_mode=args.voice_mode, mac_voice=args.mac_voice,
            narration_root=args.narration_root,
            narration_name=args.narration_name,
            narration_sha256=args.narration_sha256, execute=args.execute)
    except (EpisodeMuxError, ValueError, OSError, KeyError):
        print(json.dumps({
            "status": "COLORS_EPISODE_BLOCKED",
            "render_executed": False,
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
