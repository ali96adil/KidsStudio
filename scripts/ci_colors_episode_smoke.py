"""Real offline FFmpeg/Pillow end-to-end integration test for first colors pilot.

Designed for CI: original generated illustrations + synthetic tone-only 24s WAV.
No voice synthesis, private child media, Mac hardware, network, Pi, or YouTube.
Output stays inside an ephemeral private directory and is not uploaded.
"""
from __future__ import annotations

import hashlib
from array import array
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

from PIL import Image

from kidsstudio.first_colors_episode import DURATION, run_first_colors_episode
from kidsstudio.audio_pcm_energy import check_six_beat_pcm_energy
from kidsstudio.mac_episode_audio import _check_video, _probe
from kidsstudio.mp4_playback_preflight import inspect_mp4_playback
from ci_full_private_chain_smoke import check_offline_full_private_chain


def _wav_synthetic_tone(path: Path) -> str:
    rate = 16000
    # Codec and presence-gate fixture only: a steady tone is not speech.
    samples = array("h", (int(5000 * math.sin(2 * math.pi * 440 * i / rate))
                          for i in range(rate * DURATION)))
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(samples.tobytes())
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
        # macOS often exposes /var as a symlink to /private/var.
        # The private-evidence path guard correctly rejects symlink ancestors;
        # resolve this runner-created temporary directory to its real path.
        base = Path(working).resolve(strict=True)
        base.chmod(0o700)
        audio = base / "audio"
        ready = base / "ready"
        audio.mkdir(mode=0o700)
        ready.mkdir(mode=0o700)
        wav = audio / "synthetic_tone_24s.wav"
        digest = _wav_synthetic_tone(wav)
        energy = check_six_beat_pcm_energy(
            root=str(audio), relative_path=wav.name)
        assert energy["status"] == "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED"
        assert energy["speech_words_verified"] is False
        report = run_first_colors_episode(
            output_root=str(ready), output_name="ci_colors_tone_test.mp4",
            voice_mode="supplied_wav",
            narration_root=str(audio), narration_name=wav.name,
            narration_sha256=digest, execute=True)
        assert report["status"] == "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED"
        assert report["publication_approved"] is False
        assert report["pi_transfer_performed"] is False
        assert report["youtube_upload_performed"] is False
        movie = ready / "ci_colors_tone_test.mp4"
        assert movie.is_file() and movie.stat().st_size > 0
        assert movie.stat().st_mode & 0o077 == 0
        assert hashlib.sha256(movie.read_bytes()).hexdigest() == report["final_mp4_sha256"]
        duration = _check_video(_probe(movie), with_audio=True)
        profile_probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,profile", "-of", "json", str(movie)
        ], capture_output=True, check=False, timeout=30)
        assert profile_probe.returncode == 0
        stream_info = json.loads(profile_probe.stdout)["streams"]
        video_streams = [s for s in stream_info if s.get("codec_type") == "video"]
        assert len(video_streams) == 1
        assert video_streams[0].get("profile") in ("Baseline", "Constrained Baseline")
        assert abs(duration - DURATION) <= 0.2
        # This parses the ACTUAL MP4 headers and decodes samples; no mock,
        # owner voice, Pi, YouTube or publication is involved.
        playback = inspect_mp4_playback(
            root=str(ready), relative_path=movie.name,
            expected_sha256=report["final_mp4_sha256"])
        assert playback["status"] == "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED"
        assert playback["faststart_moov_before_mdat"] is True
        assert playback["video_samples_decoded"] == 3
        assert playback["audio_samples_decoded"] == 2
        assert playback["owner_playback_reviewed"] is False
        # Decode pixels from the actual encoded result: don't rely on the
        # source PNGs or mocked FFmpeg to assert color correctness.
        red = _frame_color(movie, second=10, x=640, y=400)
        yellow = _frame_color(movie, second=14, x=640, y=365)
        blue = _frame_color(movie, second=18, x=640, y=420)
        assert red[0] > 170 and red[0] > red[1] * 2
        assert yellow[0] > 200 and yellow[1] > 140 and yellow[2] < 110
        assert blue[2] > 160 and blue[2] > blue[0] * 2
        # Reuse the ACTUAL encoded MP4 for a full offline simulated chain;
        # real owner review, SSH and Google credentials are never present.
        chain = check_offline_full_private_chain(
            base=base, ready=ready, video_name=movie.name,
            expected_sha256=report["final_mp4_sha256"])
        assert (chain["status"]
                == "OFFLINE_REAL_MP4_TO_FAKE_PI_TO_FAKE_YOUTUBE_PRIVATE_PASSED")
        assert chain["actual_youtube_upload_performed"] is False
        return {
            "status": "REAL_FFMPEG_COLORS_SMOKE_PASSED_NO_HUMAN_VOICE",
            "video_seconds": round(duration, 3),
            "resolution": [1280, 720],
            "fps": 24,
            "h264_aac_stereo": True,
            "faststart_sample_playback_preflight": True,
            "decoded_color_checks": {"red_apple": True, "yellow_sun": True,
                                     "blue_sky": True},
            "sha256_verified": True,
            "synthetic_tone_audio_only": True,
            "synthetic_tone_is_not_speech_or_arabic_voice": True,
            "real_mp4_to_fake_pi_to_fake_private_youtube_chain": chain["status"],
            "ci_owner_review_only_simulated": True,
            "ci_ssh_and_google_network_calls": False,
            "mac_hardware_tested": False,
            "arabic_voice_tested": False,
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }


if __name__ == "__main__":
    try:
        result = run_real_colors_smoke()
    except (AssertionError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        if __import__("os").environ.get("GITHUB_ACTIONS") == "true":
            print("CI colors smoke failed in synthetic runner:",
                  type(exc).__name__, file=sys.stderr)
        print(json.dumps({"status": "REAL_FFMPEG_COLORS_SMOKE_FAILED",
                          "mac_hardware_tested": False,
                          "youtube_upload_performed": False,
                          "publication_approved": False}))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
