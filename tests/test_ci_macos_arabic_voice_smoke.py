"""Mock-only CI runner capability tests; never synthesize actual voice."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from kidsstudio.first_colors_episode import EpisodeMuxError
from scripts.ci_macos_arabic_voice_smoke import (
    main, run_macos_arabic_voice_smoke,
)


class MacOSVoiceSmokeTests(unittest.TestCase):
    def test_linux_runner_cannot_claim_mac(self):
        with patch("scripts.ci_macos_arabic_voice_smoke.platform.system",
                   return_value="Linux"), patch(
                       "scripts.ci_macos_arabic_voice_smoke._arabic_voice"
                   ) as voice:
            with self.assertRaises(ValueError):
                run_macos_arabic_voice_smoke()
        voice.assert_not_called()

    def test_uninstalled_arabic_voice_is_explicitly_not_tested(self):
        with patch("scripts.ci_macos_arabic_voice_smoke.platform.system",
                   return_value="Darwin"), patch(
                       "scripts.ci_macos_arabic_voice_smoke._arabic_voice",
                       side_effect=EpisodeMuxError("not installed")), patch(
                       "scripts.ci_macos_arabic_voice_smoke._synthesize_wav"
                   ) as synth:
            report = run_macos_arabic_voice_smoke()
        self.assertEqual(report["status"],
                         "MACOS_CI_ARABIC_VOICE_NOT_INSTALLED_NOT_TESTED")
        self.assertFalse(report["arabic_voice_render_tested"])
        self.assertFalse(report["operator_mac_tested"])
        self.assertFalse(report["publication_approved"])
        synth.assert_not_called()

    def test_installed_voice_temp_wav_deleted_after_pass(self):
        generated = []
        def fake_speech(root, *, voice):
            self.assertEqual(voice, "OriginalArabic")
            file = Path(root) / "voice.wav"
            file.write_bytes(b"synthetic mock bytes " * 10)
            generated.append(file)
            return file
        with patch("scripts.ci_macos_arabic_voice_smoke.platform.system",
                   return_value="Darwin"), patch(
                       "scripts.ci_macos_arabic_voice_smoke._arabic_voice",
                       return_value="OriginalArabic"), patch(
                       "scripts.ci_macos_arabic_voice_smoke._synthesize_wav",
                       side_effect=fake_speech), patch(
                       "scripts.ci_macos_arabic_voice_smoke._wav_duration",
                       return_value=24.0):
            result = run_macos_arabic_voice_smoke()
        self.assertEqual(result["status"],
                         "MACOS_CI_ARABIC_VOICE_SYNTHETIC_SMOKE_PASSED")
        self.assertTrue(result["arabic_voice_render_tested"])
        self.assertFalse(result["arabic_pronunciation_human_reviewed"])
        self.assertFalse(result["operator_mac_tested"])
        self.assertFalse(result["publication_approved"])
        self.assertEqual(len(generated), 1)
        self.assertFalse(generated[0].exists())

    def test_wrong_speech_duration_fails_closed(self):
        def fake_speech(root, *, voice):
            file = Path(root) / "voice.wav"
            file.write_bytes(b"p" * 64)
            return file
        with patch("scripts.ci_macos_arabic_voice_smoke.platform.system",
                   return_value="Darwin"), patch(
                       "scripts.ci_macos_arabic_voice_smoke._arabic_voice",
                       return_value="OriginalArabic"), patch(
                       "scripts.ci_macos_arabic_voice_smoke._synthesize_wav",
                       side_effect=fake_speech), patch(
                       "scripts.ci_macos_arabic_voice_smoke._wav_duration",
                       return_value=23.0):
            with self.assertRaises(AssertionError):
                run_macos_arabic_voice_smoke()

    def test_main_redacts_local_error_and_rejects(self):
        output = io.StringIO()
        with patch("scripts.ci_macos_arabic_voice_smoke.run_macos_arabic_voice_smoke",
                   side_effect=ValueError("/private/secret/voicefile")):
            with contextlib.redirect_stdout(output):
                code = main()
        self.assertEqual(code, 1)
        data = json.loads(output.getvalue())
        self.assertEqual(data["status"], "MACOS_CI_ARABIC_VOICE_SMOKE_FAILED")
        self.assertFalse(data["publication_approved"])
        self.assertNotIn("secret", output.getvalue())


if __name__ == "__main__":
    unittest.main()
