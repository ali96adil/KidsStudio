"""GitHub-hosted macOS: exercise native-voice-mode MP4 pipeline using TONES.

THIS DOES NOT SYNTHESIZE ARABIC WORDS. An in-process, CI-only intercept of
the macOS say command returns six synthetic FFmpeg AIFF sine tones, one per
original cue. Every later stage (AIFF probe, PCM assembly, energy gate, real
picture encode, mux, SHA, MP4 decoder, final AAC six-beat decode) is real.

No installed voice, network, user media, Pi or YouTube. Files are ephemeral.
"""
from __future__ import annotations

from array import array
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

from kidsstudio import first_colors_episode as colors
from kidsstudio.audio_pcm_energy import check_six_beat_pcm_energy
from kidsstudio.mac_episode_audio import _check_video, _probe
from kidsstudio.mp4_playback_preflight import inspect_mp4_playback

_FAKE_VOICE = "CIVoice"
_AUDIO_THRESHOLD = 196
_STAGE_STEM = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,158}\Z")


def _resolve_voice_workspace(root: Path, output_stem: str) -> Path:
    """Resolve the one private per-attempt staging directory, never guess."""
    if not isinstance(output_stem, str) or not _STAGE_STEM.fullmatch(output_stem):
        raise AssertionError("Invalid synthetic output stem.")
    matches = list(root.glob(f"{output_stem}-pilot-sources-*"))
    if (len(matches) != 1 or matches[0].is_symlink()
            or not matches[0].is_dir() or matches[0].stat().st_mode & 0o077):
        raise AssertionError("Expected exactly one private render-attempt workspace.")
    return matches[0]


def _ci_say_interceptor(original, calls: list[int]):
    """Use real FFmpeg to make tones; keep all non-say commands untouched."""
    def fake_run(command, *, timeout=480, text=False):
        if command[:3] == ["say", "-v", "?"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=_FAKE_VOICE + " ar_SA # CI TONES ONLY\n")
        if command and command[0] == "say":
            if (command.count("-o") != 1 or command.count("-v") != 1
                    or command[command.index("-v") + 1] != _FAKE_VOICE
                    or command[-1] not in [speech for _, speech in colors.CUES]):
                raise AssertionError("Unexpected native-voice command.")
            index = len(calls)
            if not 0 <= index < 6:
                raise AssertionError("Unexpected synthetic speech beat.")
            calls.append(index)
            path = Path(command[command.index("-o") + 1])
            if path.exists() or path.suffix != ".aiff":
                raise AssertionError("Expected new private AIFF stage file.")
            tone = subprocess.run(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i",
                 f"sine=frequency={440 + index * 80}:sample_rate=48000:duration=1.20",
                 "-c:a", "pcm_s16be", "-f", "aiff", str(path)],
                capture_output=True, check=False, timeout=45)
            if tone.returncode != 0 or not path.is_file():
                raise AssertionError("Synthetic AIFF creation failed.")
            path.chmod(0o600)
            return subprocess.CompletedProcess(command, 0)
        return original(command, timeout=timeout, text=text)
    return fake_run


def _decode_sound_in_beat(movie: Path, beat: int) -> bool:
    """Confirm actual AAC from completed MP4 has energy in this beat."""
    decoded = subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
         "-ss", f"{beat * 4 + 0.15:.3f}", "-i", str(movie),
         "-map", "0:a:0", "-t", "0.5", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", "-f", "s16le", "pipe:1"],
        capture_output=True, check=False, timeout=45)
    if decoded.returncode != 0 or len(decoded.stdout) < 1600:
        return False
    samples = array("h")
    samples.frombytes(decoded.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    return sum(abs(value) >= _AUDIO_THRESHOLD for value in samples) >= 400


def run_ci_native_voice_mode_synthetic() -> dict:
    if platform.system() != "Darwin":
        raise ValueError("Full native-mode synthetic integration requires hosted macOS.")
    with tempfile.TemporaryDirectory(prefix="kidsstudio-native-tones-") as tmp:
        # /var can be a symlink on macOS; private guard needs /private/var.
        base = Path(tmp).resolve(strict=True)
        base.chmod(0o700)
        ready = base / "ready"
        ready.mkdir(mode=0o700)
        calls: list[int] = []
        original = colors._run
        with patch("kidsstudio.first_colors_episode._run",
                   side_effect=_ci_say_interceptor(original, calls)):
            rendered = colors.run_first_colors_episode(
                output_root=str(ready), output_name="synthetic_native_tones.mp4",
                voice_mode="macos", execute=True)
        if (rendered["status"] != "COLORS_EPISODE_PRIVATE_FILE_UNREVIEWED"
                or calls != list(range(6))
                or rendered["publication_approved"] is not False
                or rendered["pi_transfer_performed"] is not False
                or rendered["youtube_upload_performed"] is not False):
            raise AssertionError("Native voice-mode synthetic pipeline did not finish.")
        voice = (_resolve_voice_workspace(ready, "synthetic_native_tones") /
                 "arabic_voice.wav")
        gate = check_six_beat_pcm_energy(
            root=str(voice.parent), relative_path=voice.name)
        if gate["status"] != "SIX_BEAT_PCM_ENERGY_PRESENT_UNREVIEWED":
            raise AssertionError("Assembled PCM narration failed beat gate.")
        movie = ready / "synthetic_native_tones.mp4"
        if (not movie.is_file() or movie.stat().st_mode & 0o077
                or hashlib.sha256(movie.read_bytes()).hexdigest()
                != rendered["final_mp4_sha256"]):
            raise AssertionError("Synthetic final MP4 has wrong privacy/hash.")
        playback = inspect_mp4_playback(
            root=str(ready), relative_path=movie.name,
            expected_sha256=rendered["final_mp4_sha256"])
        if playback["status"] != "MP4_PLAYBACK_PREFLIGHT_PASSED_UNREVIEWED":
            raise AssertionError("Full synthetic native-mode MP4 preflight failed.")
        duration = _check_video(_probe(movie), with_audio=True)
        if abs(duration - colors.DURATION) > 0.2:
            raise AssertionError("Wrong encoded synthetic MP4 duration.")
        # Decode ACTUAL final AAC from all six beats; source PCM alone
        # does not certify final mux timing or preserved sound.
        for beat in range(6):
            if not _decode_sound_in_beat(movie, beat):
                raise AssertionError("Synthetic AAC beat missing in final MP4.")
        return {
            "schema_version": 1,
            "status": "MACOS_CI_NATIVE_MODE_WITH_SYNTHETIC_TONES_PASSED",
            "native_voice_mode_orchestration_tested": True,
            "synthetic_aiff_generated": 6,
            "pcm_beats_with_measurable_energy": 6,
            "final_aac_beats_with_measurable_energy": 6,
            "video_seconds": round(duration, 3),
            "mp4_sha256_verified": True,
            "synthetic_tones_not_arabic_speech": True,
            "actual_mac_say_voice_tested": False,
            "operator_mac_tested": False,
            "arabic_pronunciation_reviewed": False,
            "pi_transfer_performed": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }


def main() -> int:
    try:
        result = run_ci_native_voice_mode_synthetic()
    except (ValueError, OSError, AssertionError,
            subprocess.TimeoutExpired):
        result = {
            "status": "MACOS_CI_NATIVE_MODE_SYNTHETIC_TONES_FAILED",
            "actual_mac_say_voice_tested": False,
            "operator_mac_tested": False,
            "youtube_upload_performed": False,
            "publication_approved": False,
        }
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
