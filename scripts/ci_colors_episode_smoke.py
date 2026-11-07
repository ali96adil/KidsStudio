"""Real offline FFmpeg/Pillow end-to-end integration test for first colors pilot.

Designed for CI: original generated illustrations + synthetic silent 24s WAV.
No voice synthesis, private child media, Mac hardware, network, Pi, or YouTube.
Output stays inside an ephemeral private directory and is not uploaded.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

from PIL import Image

from kidsstudio.first_colors_episode import DURATION, run_first_colors_episode
from kidsstudio.mac_episode_audio import _check_video, _probe


def _wav_silence(path: Path) -> str:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        for _ in range(DURATION):
            audio.writeframes(b"\0\0" * 16000)
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame_color(file: Path, *, second: int, x: int, y: int) -> tuple[int, int, int]:
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-ss", str(second), "-i", str(file), "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    decoded = subprocess.run(command, capture_output=True,
                             check=False, timeout=40)
    if decoded.returncode != 0 or len(decoded.stdout) > 10_000_000:
        raise AssertionError("Real FFmpeg frame decode failed.")
    with Image.open(BytesIO(decoded.stdout)) as image:
        image.load()
        if image.size != (1280, 720):
            raise AssertionError("Decoded video must have 1280x720 pixels.")
        return image.convert("RGB").getpixel((x, y))


def run_real_colors_smoke() -> dict:
    with tempfile.TemporaryDirectory(prefix="kidsstudio-colors-real-") as working:
        base = Path(working)
        base.chmod(0o700)
        audio = base / "audio"
        ready = base / "ready"
        audio.mkdir(mode=0o700)
        ready.mkdir(mode=0o700)
        wav = audio / "synthetic_silent_24s.wav"
        digest = _wav_silence(wav)
        report = run_first_colors_episode(
            output_root=str(ready), output_name="ci_colors_silent_test.mp4",
            voice_mode="supplied_wav",
            narration_root=str(audio), narration_name=wav.name,
            narration_sha256=digest, execute=True)
        assert report["status"] == "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED"
        assert report["publication_approved"] is False
        assert report["pi_transfer_performed"] is False
        assert report["youtube_upload_performed"] is False
        movie = ready / "ci_colors_silent_test.mp4"
        assert movie.is_file() and movie.stat().st_size > 0
        assert movie.stat().st_mode & 0o077 == 0
        assert hashlib.sha256(movie.read_bytes()).hexdigest() == report["final_mp4_sha256"]
        duration = _check_video(_probe(movie), with_audio=True)
        assert abs(duration - DURATION) <= 0.2
        # Decode pixels from the actual encoded result: don't rely on the
        # source PNGs or mocked FFmpeg to assert color correctness.
        red = _frame_color(movie, second=10, x=640, y=400)
        yellow = _frame_color(movie, second=14, x=640, y=365)
        blue = _frame_color(movie, second=18, x=640, y=420)
        assert red[0] > 170 and red[0] > red[1] * 2
        assert yellow[0] > 200 and yellow[1] > 140 and yellow[2] < 110
        assert blue[2] > 160 and blue[2] > blue[0] * 2
        return {
            "status": "REAL_FFMPEG_COLORS_SMOKE_PASSED_NO_HUMAN_VOICE",
            "video_seconds": round(duration, 3),
            "resolution": [1280, 720],
            "fps": 24,
            "h264_aac_stereo": True,
            "decoded_color_checks": {"red_apple": True, "yellow_sun": True,
                                     "blue_sky": True},
            "sha256_verified": True,
            "synthetic_silent_audio_only": True,
            "mac_hardware_tested": False,
            "arabic_voice_tested": False,
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }


if __name__ == "__main__":
    try:
        result = run_real_colors_smoke()
    except (AssertionError, OSError, ValueError, subprocess.TimeoutExpired):
        print(json.dumps({"status": "REAL_FFMPEG_COLORS_SMOKE_FAILED",
                          "mac_hardware_tested": False,
                          "youtube_upload_performed": False,
                          "publication_approved": False}))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
