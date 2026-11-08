"""Real private PCM WAV verification for Mac's installed-voice alternative.

No model, Mac, network, voice rendering, Pi, Google or publication.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from kidsstudio.mac_colors_preflight import (
    inspect_mac_colors_preflight, main,
)


class SuppliedWavPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.narration = self.base / "narration"
        self.ready = self.base / "ready"
        for p in (self.narration, self.ready):
            p.mkdir(mode=0o700)
        self.wav = self.narration / "colors_original.wav"
        self.write_wav()
        self.sha = hashlib.sha256(self.wav.read_bytes()).hexdigest()

    def write_wav(self, *, silent_beat=None, channels=1, seconds=24):
        with wave.open(str(self.wav), "wb") as stream:
            stream.setnchannels(channels)
            stream.setsampwidth(2)
            stream.setframerate(16000)
            for i in range(seconds):
                value = 0 if silent_beat is not None and i // 4 == silent_beat else 6000
                stream.writeframesraw(
                    (value.to_bytes(2, byteorder="little", signed=True)
                     * channels) * 16000)
        self.wav.chmod(0o600)

    def check(self, **updates):
        args = dict(
            artifact_root=str(self.ready),
            voice_mode="supplied_wav",
            narration_root=str(self.narration),
            narration_name=self.wav.name,
            narration_sha256=self.sha,
        )
        args.update(updates)
        with patch("kidsstudio.mac_colors_preflight.platform.system",
                   return_value="Darwin"), patch(
                       "kidsstudio.mac_colors_preflight.inspect_host",
                       return_value={
                           "ready_for_supervised_tests": True,
                           "host_system": "Darwin", "machine": "arm64",
                       }), patch(
                           "kidsstudio.mac_colors_preflight._source_checkout",
                           return_value=("a" * 40, True)), patch(
                               "kidsstudio.mac_colors_preflight.shutil.which",
                               side_effect=lambda executable:
                               None if executable == "say" else "/usr/bin/" + executable
                           ), patch(
                               "kidsstudio.mac_colors_preflight._arabic_voice",
                               side_effect=AssertionError(
                                   "Supplied original WAV must never invoke Apple TTS")):
            return inspect_mac_colors_preflight(**args)

    def test_real_mono_wav_and_6_beats_pass_without_apple_say(self):
        report = self.check()
        self.assertEqual(report["status"], "MAC_COLORS_PREFLIGHT_READY")
        self.assertEqual(report["voice_mode"], "supplied_wav")
        self.assertTrue(report["supplied_wav_six_beats_sha_verified"])
        self.assertFalse(report["local_arabic_voice_available"])
        self.assertFalse(report["video_render_executed"])
        self.assertFalse(report["speech_generated"])
        self.assertFalse(report["youtube_upload_performed"])

    def test_wrong_sha_blocks_before_render(self):
        result = self.check(narration_sha256="0" * 64)
        self.assertIn("supplied_wav_missing_unverified_or_silent",
                      result["blockers"])
        self.assertFalse(result["supplied_wav_six_beats_sha_verified"])

    def test_one_silent_four_second_beat_is_blocked(self):
        self.write_wav(silent_beat=4)
        self.sha = hashlib.sha256(self.wav.read_bytes()).hexdigest()
        report = self.check()
        self.assertIn("supplied_wav_missing_unverified_or_silent",
                      report["blockers"])

    def test_stereo_and_short_wav_are_blocked_for_six_beat_pilot(self):
        for channels, length in ((2, 24), (1, 23), (1, 25)):
            with self.subTest(channels=channels, length=length):
                self.write_wav(channels=channels, seconds=length)
                self.sha = hashlib.sha256(self.wav.read_bytes()).hexdigest()
                self.assertEqual(self.check()["status"],
                                 "MAC_COLORS_PREFLIGHT_BLOCKED")

    def test_public_or_symlink_wav_is_blocked(self):
        self.wav.chmod(0o644)
        self.assertEqual(self.check()["status"], "MAC_COLORS_PREFLIGHT_BLOCKED")
        self.wav.chmod(0o600)
        original = self.narration / "original.wav"
        self.wav.rename(original)
        self.wav.symlink_to(original)
        self.assertEqual(self.check()["status"], "MAC_COLORS_PREFLIGHT_BLOCKED")

    def test_missing_partial_narration_and_path_traversal_are_blocked(self):
        for bad in (
            {"narration_name": None},
            {"narration_sha256": None},
            {"narration_root": None},
            {"narration_name": "../escape.wav"},
            {"narration_name": "wrong.mp4"},
        ):
            with self.subTest(bad=bad):
                self.assertEqual(self.check(**bad)["status"],
                                 "MAC_COLORS_PREFLIGHT_BLOCKED")

    def test_mixed_native_mac_voice_in_supplied_mode_is_blocked(self):
        self.assertIn("unexpected_macos_voice_argument",
                      self.check(mac_voice="Voice")["blockers"])

    def test_native_mode_refuses_supplied_wav_args(self):
        report = self.check(voice_mode="macos")
        self.assertIn("unexpected_supplied_wav_arguments", report["blockers"])

    def test_cli_blocks_bad_sha_without_leaking_source_path(self):
        output = io.StringIO()
        with patch("kidsstudio.mac_colors_preflight.platform.system",
                   return_value="Darwin"), patch(
                       "kidsstudio.mac_colors_preflight.inspect_host",
                       return_value={"ready_for_supervised_tests": True,
                                     "host_system": "Darwin", "machine": "arm64"}
                   ), patch("kidsstudio.mac_colors_preflight._source_checkout",
                            return_value=("a" * 40, True)), patch(
                                "kidsstudio.mac_colors_preflight.shutil.which",
                                return_value="/usr/bin/bin"), patch(
                                    "kidsstudio.mac_colors_preflight._arabic_voice",
                                    side_effect=AssertionError("No say call")
                                ), contextlib.redirect_stdout(output):
            code = main([
                "--artifact-root", str(self.ready),
                "--voice-mode", "supplied_wav",
                "--narration-root", str(self.narration),
                "--narration-name", self.wav.name,
                "--narration-sha256", "0"*64,
            ])
        self.assertEqual(code, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "MAC_COLORS_PREFLIGHT_BLOCKED")
        self.assertNotIn(str(self.narration), output.getvalue())


if __name__ == "__main__":
    unittest.main()
