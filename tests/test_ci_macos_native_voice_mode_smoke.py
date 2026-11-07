"""Tests of CI-only Mac native-voice-mode synthetic tone harness."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.ci_macos_native_voice_mode_smoke import (
    _ci_say_interceptor, _decode_sound_in_beat, main,
    run_ci_native_voice_mode_synthetic,
)


class MacNativeModeSyntheticTests(unittest.TestCase):
    def test_synthetic_voice_list_has_explicit_ci_only_name(self):
        def original(*args, **kwargs):
            raise AssertionError("Real say must never run.")
        fake = _ci_say_interceptor(original, [])
        result = fake(["say", "-v", "?"], timeout=15, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("CIVoice ar_SA", result.stdout)

    def test_reject_unexpected_native_say_command(self):
        fake = _ci_say_interceptor(lambda *a, **kw: None, [])
        with self.assertRaises(AssertionError):
            fake(["say", "-v", "English", "-o", "out.aiff",
                  "أهلاً يا أصدقائي!"])
        with self.assertRaises(AssertionError):
            fake(["say", "-v", "CIVoice", "-o", "out.aiff",
                  "unexpected/unsafe input"])

    def test_non_say_uses_real_original_dispatcher(self):
        history = []
        def original(cmd, *, timeout, text):
            history.append((cmd, timeout, text))
            return subprocess.CompletedProcess(cmd, 0)
        fake = _ci_say_interceptor(original, [])
        fake(["ffmpeg", "-version"], timeout=20, text=True)
        self.assertEqual(history, [(["ffmpeg", "-version"], 20, True)])

    def test_fake_say_writes_private_aiff_via_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "tone.aiff"
            synth = _ci_say_interceptor(lambda *a, **kw: None, [])
            cmd = ["say", "-v", "CIVoice", "-r", "185", "-o",
                   str(target), "أهلاً يا أصدقائي!"]
            with patch("scripts.ci_macos_native_voice_mode_smoke.subprocess.run",
                       return_value=subprocess.CompletedProcess([], 0)) as run:
                # Simulate actual FFmpeg output path; this is a pure unit test.
                def make_file(*args, **kwargs):
                    target.write_bytes(b"fictional aiff")
                    return subprocess.CompletedProcess([], 0)
                run.side_effect = make_file
                response = synth(cmd)
            self.assertEqual(response.returncode, 0)
            self.assertEqual(target.stat().st_mode & 0o077, 0)
            self.assertEqual(run.call_args.args[0][0], "ffmpeg")
            self.assertNotIn("أهلاً", " ".join(run.call_args.args[0]))

    def test_linux_cannot_claim_mac_native_mode(self):
        with patch("scripts.ci_macos_native_voice_mode_smoke.platform.system",
                   return_value="Linux"), patch(
                       "scripts.ci_macos_native_voice_mode_smoke.tempfile.TemporaryDirectory"
                   ) as directory:
            with self.assertRaises(ValueError):
                run_ci_native_voice_mode_synthetic()
        directory.assert_not_called()

    def test_silent_decoded_aac_beat_rejected(self):
        with patch("scripts.ci_macos_native_voice_mode_smoke.subprocess.run",
                   return_value=subprocess.CompletedProcess(
                       [], 0, stdout=b"\0" * 16000)):
            self.assertFalse(_decode_sound_in_beat(Path("/synthetic.mp4"), 0))

    def test_real_amplitude_detected_in_decoded_synthetic_audio(self):
        payload = (500).to_bytes(2, "little", signed=True) * 8000
        with patch("scripts.ci_macos_native_voice_mode_smoke.subprocess.run",
                   return_value=subprocess.CompletedProcess(
                       [], 0, stdout=payload)):
            self.assertTrue(_decode_sound_in_beat(Path("/synthetic.mp4"), 5))

    def test_cli_redacts_exception_and_never_claims_upload(self):
        stdout = io.StringIO()
        with patch("scripts.ci_macos_native_voice_mode_smoke.run_ci_native_voice_mode_synthetic",
                   side_effect=AssertionError("/private/secret.mp4")), \
             contextlib.redirect_stdout(stdout):
            code = main()
        self.assertEqual(code, 1)
        result = json.loads(stdout.getvalue())
        self.assertEqual(result["status"],
                         "MACOS_CI_NATIVE_MODE_SYNTHETIC_TONES_FAILED")
        self.assertNotIn("secret", stdout.getvalue())
        self.assertFalse(result["publication_approved"])
        self.assertFalse(result["youtube_upload_performed"])


if __name__ == "__main__":
    unittest.main()
